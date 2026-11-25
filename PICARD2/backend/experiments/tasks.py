import logging
import os
from pathlib import Path
import shutil
import subprocess

from celery import shared_task
from django.core.files.base import ContentFile

from .commands import build_spark_command
from .models import SparkExperiment


SHARED_DIR = os.environ.get('SPARK_SHARED_DIR', '/opt/spark/apps')
logger = logging.getLogger(__name__)


def _save_fields(experiment, fields):
    # A plain save() would INSERT the row again if it was deleted while the
    # job ran. An UPDATE changes nothing in that case, so it stays deleted.
    values = {field: getattr(experiment, field) for field in fields}
    if SparkExperiment.objects.filter(pk=experiment.pk).update(**values):
        return True
    logger.info('Experiment %s was deleted while running; discarding its files.', experiment.pk)
    for field in (experiment.output, experiment.result):
        if field:
            field.delete(save=False)
    return False


@shared_task
def run_db_script(experiment_id):
    # Claim the run atomically. Only a Queued row moves to Running, so a run
    # that was cancelled, deleted, already started, or already finished is
    # never submitted to Spark, including when Celery delivers a task twice.
    claimed = SparkExperiment.objects.filter(pk=experiment_id, status='Queued').update(status='Running')
    if not claimed:
        logger.info('Experiment %s is not queued; skipping.', experiment_id)
        return
    try:
        experiment = SparkExperiment.objects.select_related('script', 'dataset').get(id=experiment_id)
    except SparkExperiment.DoesNotExist:
        return

    # Replace old artifacts only after the worker accepts the run. A failed
    # attempt to contact Celery must not erase the previous run's report.
    if experiment.output:
        experiment.output.delete(save=False)
    if experiment.result:
        experiment.result.delete(save=False)
    experiment.output.save(f'{experiment.id}.txt', ContentFile(''), save=False)
    if not _save_fields(experiment, ['output', 'result']):
        return

    output_path = experiment.get_absolute_output_path()
    result_directory = Path(SHARED_DIR) / f'results_{experiment.id}.txt'

    try:
        # Spark requires a new output directory, including when retrying a run.
        if result_directory.is_dir():
            shutil.rmtree(result_directory)
        elif result_directory.exists():
            result_directory.unlink()

        dataset_path = None
        if experiment.dataset and experiment.dataset.file:
            dataset_path = experiment.dataset.get_absolute_file_path()
        cmd = build_spark_command(
            experiment.script, dataset_path, result_directory, experiment.args,
        )
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        with open(output_path, 'a') as output:
            for line in iter(process.stdout.readline, ''):
                output.write(line)
                output.flush()
        process.wait()
        experiment.status = 'Success' if process.returncode == 0 else 'Failed'
    except Exception as error:
        with open(output_path, 'a') as output:
            output.write(f'\nInternal Error: {error}')
        experiment.status = 'Failed'
    finally:
        # Both example JARs produce Spark text directories. Combine their parts
        # in filename order; ignore Spark's _SUCCESS and checksum files.
        try:
            part_files = sorted(path for path in result_directory.glob('part-*') if path.is_file())
            if part_files:
                experiment.result.save(
                    f'{experiment.id}.txt',
                    ContentFile(b''.join(path.read_bytes() for path in part_files)),
                    save=False,
                )
                shutil.rmtree(result_directory)
                message = 'Successfully imported results to backend storage.'
            else:
                message = f'No result parts found in {result_directory.name}.'
                # A classifier promises a report. A zero exit code alone does
                # not count as success when that report was never produced.
                if experiment.script.algorithm_config:
                    experiment.status = 'Failed'
            with open(output_path, 'a') as output:
                output.write(f'\n[System: {message}]')
        except Exception as error:
            # A storage error must not leave the experiment stuck as Running.
            experiment.status = 'Failed'
            with open(output_path, 'a') as output:
                output.write(f'\nResult import error: {error}')
        finally:
            _save_fields(experiment, ['status', 'result'])
