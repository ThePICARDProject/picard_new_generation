import shlex


CODRIFT_MAIN_CLASS = 'edu.fsu.driver.CoDRIFt'
CODRIFT_RECOMMENDED_ARGS = '2 10 gini 5 32 70 1'
CODRIFT_ARGUMENT_LABELS = (
    'numClasses',
    'numTrees',
    'impurity',
    'maxDepth',
    'maxBins',
    'percentLabeled',
    'k',
)


def is_codrift_algorithm(*, display_name='', main_class='', upload_name=''):
    normalized_main_class = (main_class or '').strip().rstrip('$').lower()
    return normalized_main_class == CODRIFT_MAIN_CLASS.lower() or any(
        'codrift' in (candidate or '').lower()
        for candidate in (display_name, upload_name)
    )


def get_algorithm_metadata(*, display_name='', main_class='', upload_name=''):
    is_codrift = is_codrift_algorithm(
        display_name=display_name,
        main_class=main_class,
        upload_name=upload_name,
    )
    return {
        'is_codrift': is_codrift,
        'arguments_required': is_codrift,
        'recommended_args': CODRIFT_RECOMMENDED_ARGS if is_codrift else '',
    }


def validate_algorithm_arguments(script, arguments):
    normalized_arguments = str(arguments or '').strip()
    if not is_codrift_algorithm(
        display_name=script.name,
        main_class=script.main_class,
    ):
        return normalized_arguments, ''

    try:
        values = shlex.split(normalized_arguments)
    except ValueError:
        return '', 'CoDRIFT arguments contain an unmatched quote.'

    expected_arguments = ' '.join(CODRIFT_ARGUMENT_LABELS)
    if len(values) != len(CODRIFT_ARGUMENT_LABELS):
        return '', f'CoDRIFT requires seven arguments: {expected_arguments}.'

    try:
        num_classes = int(values[0])
        num_trees = int(values[1])
        max_depth = int(values[3])
        max_bins = int(values[4])
        percent_labeled = float(values[5])
        k = int(values[6])
    except ValueError:
        return '', f'CoDRIFT arguments must match: {expected_arguments}.'

    if num_classes < 2:
        return '', 'CoDRIFT numClasses must be at least 2.'
    if num_trees < 1:
        return '', 'CoDRIFT numTrees must be at least 1.'
    if values[2].lower() not in {'gini', 'entropy'}:
        return '', 'CoDRIFT impurity must be either gini or entropy.'
    if max_depth < 0:
        return '', 'CoDRIFT maxDepth cannot be negative.'
    if max_bins < 2:
        return '', 'CoDRIFT maxBins must be at least 2.'
    if not 0 < percent_labeled <= 100:
        return '', 'CoDRIFT percentLabeled must be greater than 0 and no more than 100.'
    if k < 1:
        return '', 'CoDRIFT k must be at least 1.'

    values[2] = values[2].lower()
    return ' '.join(values), ''
