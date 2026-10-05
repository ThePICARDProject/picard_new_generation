<<<<<<< HEAD
# experiments/tasks.py
import subprocess
=======
"""Submit one experiment to Spark and copy its text report into backend storage."""

>>>>>>> 48f30fea00502885aae855842f15440bdc9e93a0
import os
from pathlib import Path
import shutil
import subprocess

from celery import shared_task
from django.core.files.base import ContentFile

from .commands import build_spark_command
from .models import SparkExperiment


SHARED_DIR = os.environ.get('SPARK_SHARED_DIR', '/opt/spark/apps')


@shared_task
def run_db_script(experiment_id):
    experiment = SparkExperiment.objects.select_related('script', 'dataset').get(id=experiment_id)
    experiment.status = 'Running'

    # Replace old artifacts only after the worker accepts the run. A failed
    # attempt to contact Celery must not erase the previous run's report.
    if experiment.output:
        experiment.output.delete(save=False)
    if experiment.result:
        experiment.result.delete(save=False)
    experiment.output.save(f'{experiment.id}.txt', ContentFile(''), save=False)
    experiment.save()

    output_path = experiment.get_absolute_output_path()
    result_directory = Path(SHARED_DIR) / f'results_{experiment.id}.txt'

    try:
<<<<<<< HEAD
        # Spark refuses to write to an existing output path, including one
        # left behind by a failed attempt.
=======
        # Spark requires a new output directory, including when retrying a run.
>>>>>>> 48f30fea00502885aae855842f15440bdc9e93a0
        if result_directory.is_dir():
            shutil.rmtree(result_directory)
        elif result_directory.exists():
            result_directory.unlink()

<<<<<<< HEAD
        cmd = ['spark-submit', '--master', 'spark://spark-master:7077']

        if experiment.script.file_type == 'jar' and experiment.script.main_class:
            cmd.extend(['--class', experiment.script.main_class])

        cmd.append(script_path) # ensure script path is appended after --class if jar

        #Upload input
        if experiment.dataset and experiment.dataset.file:
            cmd.append(experiment.dataset.get_absolute_file_path())

        # 2. Pass the unique result file path to your Spark script
        # (Make sure your Spark script reads this argument to know where to save!)
        cmd.extend([ # CoDRIFT expects the output location as two separate values, this may have to be tweaked in the future when restoring algorithm-agnosticism, this change is being made for the sake of getting a single (CoDRIFT) algorithm working.
            SHARED_DIR,
            unique_result_filename
        ])

        cmd.extend(shlex.split(experiment.args or '')) # split the arg string stored in the database into seven separate arguments, which CoDRIFT expects.
        # cmd.extend adds each value separately

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
=======
        dataset_path = None
        if experiment.dataset and experiment.dataset.file:
            dataset_path = experiment.dataset.get_absolute_file_path()
        cmd = build_spark_command(
            experiment.script, dataset_path, result_directory, experiment.args,
>>>>>>> 48f30fea00502885aae855842f15440bdc9e93a0
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
<<<<<<< HEAD
        # 3. Process the unique results file
        part_files = sorted(result_directory.glob('part-*')) # sort part files

        if result_directory.is_dir() and part_files:
            result_content = b''.join( # combine part files into one result artifact
                part_file.read_bytes() # read part files in deterministic filename order
                for part_file in part_files
            )

            experiment.result.save( # save the result artifact
                f'{experiment.id}.txt',
                ContentFile(result_content),
                save=False
            )

            shutil.rmtree(result_directory) # remove the temporary Spark output directory

            with open(output_path, 'a') as f:
                f.write('\n[System: Successfully imported results to backend storage.]')

        else:
            with open(output_path, 'a') as f:
                f.write(
                    f'\n[System: No result parts found in {unique_result_filename}.]'
=======
        # Both example JARs produce Spark text directories. Combine their parts
        # in filename order; ignore Spark's _SUCCESS and checksum files.
        try:
            part_files = sorted(path for path in result_directory.glob('part-*') if path.is_file())
            if part_files:
                experiment.result.save(
                    f'{experiment.id}.txt',
                    ContentFile(b''.join(path.read_bytes() for path in part_files)),
                    save=False,
>>>>>>> 48f30fea00502885aae855842f15440bdc9e93a0
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
            experiment.save()
