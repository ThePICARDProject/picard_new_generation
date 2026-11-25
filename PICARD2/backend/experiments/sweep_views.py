"""Parameter-sweep endpoints under /experiments/sweeps/.

A sweep is a thin layer over ordinary experiments: every generated run is a
SparkExperiment queued through the same Celery task as a single run.
The API lives under /experiments/ because NGINX already forwards that prefix
to Django, while /sweeps/... stays free for the React pages.
"""

from collections import Counter, defaultdict
import hashlib
import shlex

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from kombu.exceptions import OperationalError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from datasets.models import CSVDataset
from scripts.models import Script
from .models import PUBLIC, SparkExperiment, SweepBatch
from .sweep_generation import SweepDefinitionError, batch_status, iter_runs, plan_sweep
from .tasks import run_db_script
from .views import _has_experiment_result


STATUSES = ('Pending', 'Queued', 'Running', 'Success', 'Failed', 'Cancelled')
UNDISPATCHED_NOTE = 'Not dispatched: the execution service was unavailable. Run this experiment again to retry.'


def _limit():
    return settings.SWEEP_MAX_EXPERIMENTS


def _error(message, status, **extra):
    return JsonResponse({'error': message, **extra}, status=status)


def _checksum(field):
    # Recorded so a later reader can tell whether a file changed on disk.
    try:
        digest = hashlib.sha256()
        with field.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b''):
                digest.update(chunk)
        return digest.hexdigest()
    except (OSError, ValueError):
        return None


class _RequestError(Exception):
    def __init__(self, response):
        self.response = response


def _prepare(request):
    """Validate the request body and return (name, script, dataset, definition, plan)."""
    data = request.data if isinstance(request.data, dict) else {}
    script_id, dataset_id = data.get('script_id'), data.get('dataset_id')
    if not script_id or not dataset_id:
        raise _RequestError(_error('Both script_id and dataset_id are required.', 400))
    # The same ownership rule as single runs: the user's own or public.
    try:
        script = Script.objects.get(Q(id=script_id) & (Q(user=request.user) | Q(access_level=PUBLIC)))
    except (Script.DoesNotExist, ValidationError, ValueError, TypeError):
        # ValidationError: the id is not a UUID.
        raise _RequestError(_error('Script not found or access denied', 404))
    try:
        dataset = CSVDataset.objects.get(Q(id=dataset_id) & (Q(user=request.user) | Q(access_level=PUBLIC)))
    except (CSVDataset.DoesNotExist, ValidationError, ValueError, TypeError):
        raise _RequestError(_error('Dataset not found or access denied', 404))

    definition = data.get('parameters', {})
    try:
        plan = plan_sweep(script.algorithm_config, definition, _limit())
    except SweepDefinitionError as error:
        raise _RequestError(_error(str(error), 400, errors=error.errors))
    name = data.get('name', '')
    return name, script, dataset, definition, plan


def _active_conflicts(user, script, dataset, runs):
    """Runs identical to an experiment already Queued or Running for this user."""
    active = {}
    for experiment in SparkExperiment.objects.filter(
        user=user, script=script, dataset=dataset, status__in=('Queued', 'Running'),
    ).only('id', 'args'):
        try:
            active.setdefault(tuple(shlex.split(experiment.args)), experiment.id)
        except ValueError:
            continue
    conflicts = []
    for index, _, args in runs:
        match = active.get(tuple(shlex.split(args)))
        if match:
            conflicts.append({'sweep_index': index, 'experiment_id': str(match)})
    return conflicts


def _counts(batch_ids):
    counts = defaultdict(Counter)
    for row in (SparkExperiment.objects.filter(batch_id__in=batch_ids)
                .values('batch_id', 'status').annotate(n=Count('id'))):
        counts[row['batch_id']][row['status']] = row['n']
    return counts


def _summary(batch, counts):
    all_counts = {status: counts.get(status, 0) for status in STATUSES}
    # Keep any unexpected status visible rather than silently dropping it.
    all_counts.update({status: n for status, n in counts.items() if status not in all_counts})
    return {
        'id': str(batch.id),
        'name': batch.name,
        'script': {'id': str(batch.script_id), 'name': batch.script.name},
        'dataset': {'id': str(batch.dataset_id), 'name': batch.dataset.name},
        'created_at': batch.created_at,
        'cancel_requested': batch.cancel_requested,
        'total_count': batch.total_count,
        'status': batch_status(counts, batch.cancel_requested),
        'counts': all_counts,
    }


def _detail(batch):
    runs = list(batch.runs.order_by('sweep_index'))
    counts = Counter(run.status for run in runs)
    parameters = batch.parameters or {}
    return {
        **_summary(batch, counts),
        'axes': parameters.get('axes', []),
        'parameters': parameters.get('definition', {}),
        'runs': [{
            'id': str(run.id),
            'sweep_index': run.sweep_index,
            'param_values': run.param_values,
            'args': run.args,
            'status': run.status,
            'has_result': (has_result := _has_experiment_result(run)),
            'result_url': f'/experiments/{run.id}/result/' if has_result else '',
        } for run in runs],
    }


def _get_batch(request, batch_id, lock=False):
    queryset = SweepBatch.objects.select_related('script', 'dataset')
    if lock:
        queryset = queryset.select_for_update()
    # Another user's sweep is reported as missing, not forbidden.
    return queryset.get(id=batch_id, user=request.user)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def preview_sweep(request):
    """Validate a definition and list its runs and conflicts. Writes nothing."""
    try:
        _, script, dataset, _, plan = _prepare(request)
    except _RequestError as error:
        return error.response
    runs = list(iter_runs(script.algorithm_config, plan))
    return JsonResponse({
        'count': plan['count'],
        'max_experiments': _limit(),
        'parameter_order': [axis['name'] for axis in plan['axes']],
        'axes': plan['axes'],
        # Bounded by the run limit, so the full list is small enough to send.
        'combinations': [{'sweep_index': index, 'param_values': values} for index, values, _ in runs],
        'duplicate_conflicts': _active_conflicts(request.user, script, dataset, runs),
    })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def sweeps(request):
    if request.method == 'GET':
        return _list_sweeps(request)
    return _create_sweep(request)


def _list_sweeps(request):
    batches = list(SweepBatch.objects.select_related('script', 'dataset')
                   .filter(user=request.user).order_by('-created_at'))
    counts = _counts([batch.id for batch in batches])
    return JsonResponse({'sweeps': [_summary(batch, counts[batch.id]) for batch in batches]})


def _create_sweep(request):
    try:
        name, script, dataset, definition, plan = _prepare(request)
    except _RequestError as error:
        return error.response
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
        return _error('Enter a sweep name of 1-120 characters.', 400)
    runs = list(iter_runs(script.algorithm_config, plan))
    stored = {
        'definition': definition,
        'axes': plan['axes'],
        'manifest': script.algorithm_config,
        'checksums': {'script': _checksum(script.file), 'dataset': _checksum(dataset.file)},
    }

    with transaction.atomic():
        # Serialize submissions per user, as single runs do, so two requests
        # cannot both pass the duplicate check.
        User.objects.select_for_update().get(pk=request.user.pk)
        conflicts = _active_conflicts(request.user, script, dataset, runs)
        if conflicts:
            return _error(
                f'{len(conflicts)} of these runs match experiments that are already queued or running. '
                'Wait for them to finish or change the parameters.',
                409, duplicate_conflicts=conflicts,
            )
        batch = SweepBatch.objects.create(
            name=name.strip(), user=request.user, script=script, dataset=dataset,
            total_count=plan['count'], parameters=stored,
        )
        experiments = SparkExperiment.objects.bulk_create([
            SparkExperiment(
                user=request.user, script=script, dataset=dataset, args=args, status='Queued',
                batch=batch, sweep_index=index, param_values=values,
            ) for index, values, args in runs
        ])

    # Publish only after the commit, in sweep order, so the worker's
    # Queued -> Running claim always sees committed rows.
    dispatched = 0
    try:
        for experiment in experiments:
            run_db_script.delay(experiment.id)
            dispatched += 1
    except OperationalError:
        # Never leave a Queued row with no task behind it.
        for experiment in experiments[dispatched:]:
            if SparkExperiment.objects.filter(pk=experiment.pk, status='Queued').update(status='Failed'):
                experiment.output.save(f'{experiment.id}.txt', ContentFile(UNDISPATCHED_NOTE), save=False)
                SparkExperiment.objects.filter(pk=experiment.pk).update(output=experiment.output.name)
        return _error(
            f'The execution service is unavailable. {dispatched} of {len(experiments)} runs were queued; '
            'the rest were marked Failed and can be run again.',
            503, sweep_id=str(batch.id), queued=dispatched, total=len(experiments),
        )

    batch = _get_batch(request, batch.id)
    return JsonResponse(_detail(batch), status=201)


@api_view(['GET', 'DELETE'])
@permission_classes([IsAuthenticated])
def sweep_detail(request, batch_id):
    try:
        batch = _get_batch(request, batch_id)
    except SweepBatch.DoesNotExist:
        return _error('Sweep not found', 404)
    if request.method == 'GET':
        return JsonResponse(_detail(batch))

    with transaction.atomic():
        batch = _get_batch(request, batch_id, lock=True)
        if batch.runs.filter(status__in=('Queued', 'Running')).exists():
            return _error(
                'This sweep still has queued or running runs. Cancel it and wait for running runs to finish before deleting.',
                409,
            )
        runs = list(batch.runs.all())
        for run in runs:
            if run.output:
                run.output.delete(save=False)
            if run.result:
                run.result.delete(save=False)
        batch.delete()
    return HttpResponse(status=204)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_sweep(request, batch_id):
    """Cancel runs that have not started. Running runs finish normally."""
    try:
        with transaction.atomic():
            batch = _get_batch(request, batch_id, lock=True)
            if not batch.cancel_requested:
                batch.cancel_requested = True
                batch.save(update_fields=['cancel_requested'])
            cancelled = batch.runs.filter(status='Queued').update(status='Cancelled')
    except SweepBatch.DoesNotExist:
        return _error('Sweep not found', 404)
    batch = _get_batch(request, batch_id)
    return JsonResponse({'cancelled': cancelled, **_detail(batch)})
