# experiments/views.py
import os
from kombu.exceptions import OperationalError

from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, JsonResponse

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from datasets.models import CSVDataset
from scripts.algorithms import validate_algorithm_arguments
from scripts.models import Script
from .models import SparkExperiment, PUBLIC
from .tasks import run_db_script


# def _get_result_path(experiment):
#     shared_dir = os.environ.get('SPARK_SHARED_DIR', '/opt/spark/apps')
#     return os.path.join(shared_dir, f'{experiment.id}_results.txt')

# Author: Chris Jones
# Date: August 31 2026
# Purpose: Helper method for checking if experiment result exists
def _has_experiment_result(experiment):
    return bool(
        experiment.result
        and experiment.result.name
        and experiment.result.storage.exists(experiment.result.name)
    )

# Author: Chris Jones
# Date: August 31st, 2026
# Purpose: Helper method for getting experiment data so that it can be properly rendered on the page.
# Previously, exp.output was used but was causing an HTTP 500 error. Using this method prevents that.
def _read_experiment_output(experiment):
    if not experiment.output:
        return ''

    try: 
        with experiment.output.open('rb') as output_file:
            return output_file.read().decode('utf-8', errors='replace')
    except (FileNotFoundError, OSError):
        return ''

def _serialize_experiment_summary(experiment):
    has_result = _has_experiment_result(experiment) # use helper method for checking if the experiment result exists
    return {
        "id": experiment.id,
        "script_name": experiment.script.name,
        "dataset_name": experiment.dataset.name if experiment.dataset else '',
        "args": getattr(experiment, 'args', ''),  # <-- NEW: Include args
        "status": experiment.status,
        "created_at": experiment.created_at,
        "has_result": has_result,
        "result_url": f"/experiments/{experiment.id}/result/" if has_result else '', # update to use new has_result bool
    }
# 1. GET: List all experiments for the logged-in user
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_experiments(request):
    # Fetch experiments belonging to the user, newest first
    experiments = SparkExperiment.objects.select_related('script', 'dataset').filter(user=request.user).order_by('-created_at')

    # Format the data for the frontend
    experiment_data = [_serialize_experiment_summary(exp) for exp in experiments]

    return JsonResponse(experiment_data, safe=False)

# 2. GET: Allows for the frontend to watch an experiments results
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_experiment_detail(request, experiment_id):
    try:
        exp = SparkExperiment.objects.get(id=experiment_id, user=request.user)
        has_result = _has_experiment_result(exp) # update to use helper method
        return JsonResponse({
            "id": exp.id,
            "script_name": exp.script.name,
            "dataset_name": exp.dataset.name if exp.dataset else '',
            "status": exp.status,
            "output": _read_experiment_output(exp),
            "created_at": exp.created_at,
            "has_result": has_result,
            "result_url": f"/experiments/{exp.id}/result/" if has_result else '',
        })
    except SparkExperiment.DoesNotExist:
        return JsonResponse({"error": "Not found"}, status=404)

# 3. POST: Construct a new experiment without immediately running it
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_experiment(request):
    script_id = request.data.get('script_id')
    dataset_id = request.data.get('dataset_id')
    args = request.data.get('args', '')

    if not script_id or not dataset_id:
        return JsonResponse({"error": "Both script_id and dataset_id are required"}, status=400)

    try:
        # Check permissions: script must be mine OR public
        script = Script.objects.get(
            Q(id=script_id) & (Q(user=request.user) | Q(access_level=PUBLIC))
        )

        args, argument_error = validate_algorithm_arguments(script, args)
        if argument_error:
            return JsonResponse({"error": argument_error}, status=400)

        dataset = None
        if dataset_id:
            dataset = CSVDataset.objects.get(
                Q(id=dataset_id) & (Q(user=request.user) | Q(access_level=PUBLIC))
            )

        # Construct the experiment
        experiment = SparkExperiment.objects.create(
            user=request.user,
            script=script,
            dataset=dataset,
            args=args,
            status='Pending'
        )

        return JsonResponse({
            "message": "Experiment created successfully",
            "experiment_id": experiment.id,
            "status": experiment.status
        }, status=201)

    except Script.DoesNotExist:
        return JsonResponse({"error": "Script not found or access denied"}, status=404)
    except CSVDataset.DoesNotExist:
        return JsonResponse({"error": "Dataset not found or access denied"}, status=404)

# 4. POST: Trigger the Spark run for an existing ID
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def run_script(request, script_id):
    # Get dataset_id from POST data
    dataset_id = request.data.get('dataset_id')
    args = request.data.get('args', '')

    if not dataset_id:
        return JsonResponse({"error": "dataset_id is required"}, status=400)

    try:
        # Check permissions: script must be mine OR public
        script = Script.objects.get(
            Q(id=script_id) & (Q(user=request.user) | Q(access_level=PUBLIC))
        )

        args, argument_error = validate_algorithm_arguments(script, args)
        if argument_error:
            return JsonResponse({"error": argument_error}, status=400)

        # Validate Dataset permissions (Mine OR Public)
        dataset = CSVDataset.objects.get(
            Q(id=dataset_id) & (Q(user=request.user) | Q(access_level=PUBLIC))
        )

        experiment = SparkExperiment.objects.create(
            user=request.user,
            script=script,
            dataset=dataset,
            args=args,
            status='Queued'
        )
        # Pass the experiment ID to the worker
        run_db_script.delay(experiment.id)

        return JsonResponse({"experiment_id": experiment.id, "status": "Queued"})
    except Script.DoesNotExist:
        return JsonResponse({"error": "Script not found or access denied"}, status=404)
    except CSVDataset.DoesNotExist:
        return JsonResponse({"error": "Dataset not found or access denied"}, status=404)

# 5. POST: Queue an already existing Experiment
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def run_experiment(request, experiment_id):  # <-- New Method
    try:
        # Keep the state change and broker publish together. If the execution
        # service is unavailable, the transaction rolls back so a failed run
        # does not become stuck in a misleading Queued state.
        with transaction.atomic():
            experiment = SparkExperiment.objects.select_for_update().get(
                id=experiment_id,
                user=request.user,
            )

            experiment.status = 'Queued'
            experiment.save(update_fields=['status'])

            # The worker replaces stale output/result artifacts once it has
            # actually accepted the job. Until then, preserve the failed run.
            run_db_script.delay(experiment.id)

        return JsonResponse(
            {"experiment_id": experiment.id, "status": "Queued", "message": "Experiment added to queue"})
    except SparkExperiment.DoesNotExist:
        return JsonResponse({"error": "Experiment not found or access denied"}, status=404)
    except OperationalError:
        return JsonResponse(
            {"error": "Experiment execution service is unavailable. Please try again shortly."},
            status=503,
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def download_experiment_result(request, experiment_id):
    try:
        experiment = SparkExperiment.objects.get(id=experiment_id, user=request.user)
    except SparkExperiment.DoesNotExist:
        return JsonResponse({"error": "Experiment not found or access denied"}, status=404)

    if not _has_experiment_result(experiment): # use helper method for checking if the experiment has a result
        return JsonResponse({"error": "Result file not found"}, status=404)

    # Stream the storage-backed result as a download without loading the entire file into memory.
    return FileResponse(
        experiment.result.open('rb'),
        as_attachment=True,
        filename=os.path.basename(experiment.result.name),
    )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_experiment(request, experiment_id):
    try:
        experiment = SparkExperiment.objects.get(id=experiment_id, user=request.user)
    except SparkExperiment.DoesNotExist:
        return JsonResponse({"error": "Experiment not found or access denied"}, status=404)

    # result_path = _get_result_path(experiment)
    # experiment.delete()

    # if os.path.exists(result_path):
    #     os.remove(result_path)

    if experiment.output:
        experiment.output.delete(save=False)

    if experiment.result:
        experiment.result.delete(save=False)

    experiment.delete()

    return JsonResponse({"message": "Experiment deleted successfully"}, status=200)
