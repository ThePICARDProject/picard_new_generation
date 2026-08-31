# experiments/tasks.py
import subprocess
import os
from celery import shared_task
from django.core.files.base import ContentFile
from django.core.files import File
from .models import SparkExperiment

SHARED_DIR = os.environ.get('SPARK_SHARED_DIR', '/opt/spark/apps')


@shared_task
def run_db_script(experiment_id):
    experiment = SparkExperiment.objects.select_related('script', 'dataset').get(id=experiment_id)
    experiment.status = 'Running'

    experiment.output.save(f"{experiment.id}.txt", ContentFile(""), save=False)
    experiment.save()

    script_path = experiment.script.get_absolute_file_path()
    output_path = experiment.get_absolute_output_path()

    # 1. Create a unique result filename in the shared directory
    unique_result_filename = f"results_{experiment.id}.txt"
    spark_result_file = os.path.join(SHARED_DIR, unique_result_filename)

    try:
        cmd = ['spark-submit', '--master', 'spark://spark-master:7077'] # do not append script path before --class if jar

        if experiment.script.file_type == 'jar' and experiment.script.main_class:
            cmd.extend(['--class', experiment.script.main_class])

        cmd.append(script_path) # ensure script path is appended after --class if jar

        #Upload input
        if experiment.dataset and experiment.dataset.file:
            cmd.append(experiment.dataset.get_absolute_file_path())

        # 2. Pass the unique result file path to your Spark script
        # (Make sure your Spark script reads this argument to know where to save!)
        cmd.append(spark_result_file)

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        with open(output_path, 'a') as f:
            for line in iter(process.stdout.readline, ''):
                f.write(line)
                f.flush()

        process.wait()
        experiment.status = 'Success' if process.returncode == 0 else 'Failed'

    except Exception as e:
        with open(output_path, 'a') as f:
            f.write(f"\nInternal Error: {str(e)}")
        experiment.status = 'Failed'
    finally:
        # 3. Process the unique results file
        if os.path.exists(spark_result_file):
            with open(spark_result_file, 'rb') as f:
                # The filename passed here (f"{experiment.id}.txt") is passed to your
                # experiment_result_path function in models.py.
                # Setting save=True ensures the file is safely ingested before we delete it.
                experiment.result.save(f"{experiment.id}.txt", File(f), save=True)

            # 4. Clean up the original file from the shared directory
            os.remove(spark_result_file)

            with open(output_path, 'a') as f:
                f.write(f"\n[System: Successfully imported results to backend storage.]")
        else:
            with open(output_path, 'a') as f:
                f.write(f"\n[System: No {unique_result_filename} found in shared directory.]")

        # Save the final status
        experiment.save()