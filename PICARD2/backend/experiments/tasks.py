# experiments/tasks.py
import subprocess
import os
import shlex
import shutil
from celery import shared_task
from django.core.files.base import ContentFile
from .models import SparkExperiment
from pathlib import Path

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
        cmd.extend([ # CoDRIFT expects the output location as two separate values, this may have to be tweaked in the future when restoring algorithm-agnosticism, this change is being made for the sake of getting a single (CoDRIFT) algorithm working. 
            SHARED_DIR,
            unique_result_filename
        ])

        cmd.extend(shlex.split(experiment.args)) # split the arg string stored in the database into seven separate arguments, which CoDRIFT expects.
        # cmd.extend adds each value separately

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
        result_directory = Path(spark_result_file)
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
                )

        # Save the final status
        experiment.save()