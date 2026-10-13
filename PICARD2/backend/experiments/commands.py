"""Build the Spark argument list without launching a process or reading the database."""

from pathlib import Path
import shlex
import os

from scripts.algorithms import CLASSIFICATION_PROTOCOL, validate_algorithm_arguments


def build_spark_command(script, dataset_path, result_path, arguments):
    # Validate again in the worker so saved experiments and direct task calls
    # follow the same rules as newly submitted experiments.
    arguments, error = validate_algorithm_arguments(script, arguments)
    if error:
        raise ValueError(error)

    cmd = [
        'spark-submit',
        '--master', 'spark://spark-master:7077',
        '--deploy-mode', 'client',
        '--driver-memory', os.environ.get('SPARK_DRIVER_MEMORY', '1g'),
        '--executor-memory', os.environ.get('SPARK_EXECUTOR_MEMORY', '1g'),
        '--executor-cores', os.environ.get('SPARK_EXECUTOR_CORES', '1'),
        '--total-executor-cores', os.environ.get('SPARK_MAX_CORES', '2'),
    ]
    if script.file_type == 'jar' and script.main_class:
        cmd.extend(['--class', script.main_class])
    cmd.append(script.get_absolute_file_path())

    if script.algorithm_config:
        if script.algorithm_config['protocol'] != CLASSIFICATION_PROTOCOL:
            raise ValueError('This algorithm uses an unsupported launch protocol.')
        if not dataset_path:
            raise ValueError('A classification experiment requires a dataset.')
        # Every configured classifier receives these three arguments first.
        # Splitting the result path into directory and name lets the JAR create
        # exactly the directory that PICARD will later read for part-* files.
        result_path = Path(result_path)
        cmd.extend([dataset_path, str(result_path.parent), result_path.name])
    else:
        # Existing uploads without a manifest keep their original interface:
        # dataset path, complete output path, then any manually entered values.
        if dataset_path:
            cmd.append(dataset_path)
        cmd.append(str(result_path))

    # Popen receives a list, so spaces and shell characters stay inside each
    # argument. The argument text is never executed as a shell command.
    cmd.extend(shlex.split(arguments))
    return cmd

