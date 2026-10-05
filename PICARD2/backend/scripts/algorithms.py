"""Read algorithm settings and validate arguments without knowing algorithm names."""

import json
import math
import re
import shlex


CLASSIFICATION_PROTOCOL = 'spark-classification-v1'
MAX_MANIFEST_BYTES = 65536
PARAMETER_TYPES = {'integer', 'number', 'choice', 'string'}
BOUNDS = ('min', 'max', 'exclusiveMin', 'exclusiveMax')


def normalize_parameter(parameter, value):
    # Use the same rules for a manifest's defaults and an experiment's values.
    label = parameter.get('label') or parameter['name']
    if type(value) not in (str, int, float) or '\0' in str(value):
        raise ValueError(f'{label} must be a text or numeric value.')
    text = str(value)
    kind = parameter['type']

    if kind in ('integer', 'number'):
        try:
            if kind == 'integer':
                if not re.fullmatch(r'[+-]?[0-9]+', text):
                    raise ValueError
                number = int(text)
            else:
                number = float(text)
                if not math.isfinite(number):
                    raise ValueError
        except (ValueError, OverflowError):
            raise ValueError(f'{label} must be a finite {kind}.') from None

        # Inclusive and exclusive bounds say whether endpoints such as a 0%
        # training set are allowed by this algorithm.
        if 'min' in parameter and number < parameter['min']:
            raise ValueError(f'{label} must be at least {parameter["min"]}.')
        if 'max' in parameter and number > parameter['max']:
            raise ValueError(f'{label} must be at most {parameter["max"]}.')
        if 'exclusiveMin' in parameter and number <= parameter['exclusiveMin']:
            raise ValueError(f'{label} must be greater than {parameter["exclusiveMin"]}.')
        if 'exclusiveMax' in parameter and number >= parameter['exclusiveMax']:
            raise ValueError(f'{label} must be less than {parameter["exclusiveMax"]}.')
        return str(int(number)) if number == int(number) else str(number)

    if kind == 'choice':
        # Accept GINI as gini, for example, but pass the spelling from the
        # definition to the algorithm. Choices cannot differ only by case.
        for choice in parameter['choices']:
            if text.casefold() == choice.casefold():
                return choice
        raise ValueError(f'{label} must be one of: {", ".join(parameter["choices"])}.')

    if not text.strip():
        raise ValueError(f'{label} cannot be empty.')
    return text


def validate_algorithm_config(config):
    # This small format describes fields. It contains no executable validators,
    # command templates, or algorithm-specific hooks.
    if not isinstance(config, dict):
        raise ValueError('The algorithm manifest must contain a JSON object.')
    if set(config) - {'protocol', 'parameters', 'input_description'}:
        raise ValueError('The manifest accepts only protocol, parameters, and input_description.')
    if config.get('protocol') != CLASSIFICATION_PROTOCOL:
        raise ValueError(f'The manifest protocol must be {CLASSIFICATION_PROTOCOL}.')
    if not isinstance(config.get('input_description', ''), str):
        raise ValueError('input_description must be text.')
    parameters = config.get('parameters')
    if not isinstance(parameters, list) or len(parameters) > 100:
        raise ValueError('parameters must be a list with at most 100 entries.')

    names = set()
    allowed_fields = {'name', 'label', 'type', 'default', 'choices', 'description', *BOUNDS}
    for parameter in parameters:
        if not isinstance(parameter, dict) or set(parameter) - allowed_fields:
            raise ValueError('Each parameter must use only the documented parameter fields.')
        name = parameter.get('name')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name):
            raise ValueError('Parameter names must start with a letter and use letters, numbers, or underscores.')
        if name in names:
            raise ValueError(f'Parameter name {name} is repeated.')
        names.add(name)
        kind = parameter.get('type')
        if not isinstance(kind, str) or kind not in PARAMETER_TYPES:
            raise ValueError(f'{name}: type must be integer, number, choice, or string.')
        for field in ('label', 'description'):
            if field in parameter and not isinstance(parameter[field], str):
                raise ValueError(f'{name}: {field} must be text.')

        for bound in BOUNDS:
            if bound in parameter:
                value = parameter[bound]
                if kind not in ('integer', 'number') or type(value) not in (int, float):
                    raise ValueError(f'{name}: numeric bounds apply only to integer or number parameters.')
                if isinstance(value, float) and not math.isfinite(value):
                    raise ValueError(f'{name}: bounds must be finite numbers.')
        for lower in ('min', 'exclusiveMin'):
            for upper in ('max', 'exclusiveMax'):
                if lower in parameter and upper in parameter:
                    low, high = parameter[lower], parameter[upper]
                    if low > high or (low == high and (lower != 'min' or upper != 'max')):
                        raise ValueError(f'{name}: the lower bound must allow values up to the upper bound.')

        if kind == 'choice':
            choices = parameter.get('choices')
            if not isinstance(choices, list) or not choices or any(
                not isinstance(choice, str) or not choice.strip() or '\0' in choice
                for choice in choices
            ):
                raise ValueError(f'{name}: choices must be a nonempty list of nonempty strings.')
            if len({choice.casefold() for choice in choices}) != len(choices):
                raise ValueError(f'{name}: choices must be distinct, ignoring case.')
        elif 'choices' in parameter:
            raise ValueError(f'{name}: choices apply only to choice parameters.')
        if 'default' in parameter:
            default = normalize_parameter(parameter, parameter['default'])
            # Store a choice's actual spelling so the browser can select the
            # matching option even when the author wrote its default in caps.
            if kind == 'choice':
                parameter['default'] = default
    return config


def read_algorithm_manifest(upload):
    # Limit the small settings file separately from the much larger JAR.
    content = upload.read(MAX_MANIFEST_BYTES + 1)
    if len(content) > MAX_MANIFEST_BYTES:
        raise ValueError('The algorithm manifest must be at most 64 KiB.')
    try:
        config = json.loads(content.decode('utf-8-sig'))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise ValueError('The algorithm manifest must be valid UTF-8 JSON.') from None
    return validate_algorithm_config(config)


def get_algorithm_metadata(script):
    # Return the stored definition to the form. Keep the older recommendation
    # fields in the API too, deriving them from that same definition.
    config = script.algorithm_config
    parameters = config['parameters'] if config else []
    defaults = []
    if all('default' in parameter for parameter in parameters):
        defaults = [normalize_parameter(parameter, parameter['default']) for parameter in parameters]
    return {
        'algorithm_config': config,
        'arguments_required': bool(parameters),
        'recommended_args': shlex.join(defaults),
    }


def validate_algorithm_arguments(script, arguments):
    # Forms send an ordered list so a value such as "my model" stays one
    # argument. Older clients and saved experiments can still send text.
    try:
        if isinstance(arguments, str):
            try:
                values = shlex.split(arguments)
            except ValueError:
                raise ValueError('Arguments contain an unmatched quote.') from None
        elif isinstance(arguments, list) and all(isinstance(value, str) for value in arguments):
            values = arguments
        else:
            raise ValueError('Arguments must be text or a list of strings.')
        if any('\0' in value for value in values):
            raise ValueError('Arguments cannot contain null characters.')

        if script.algorithm_config:
            parameters = script.algorithm_config['parameters']
            if len(values) != len(parameters):
                names = ', '.join(parameter['name'] for parameter in parameters)
                raise ValueError(f'This algorithm requires {len(parameters)} arguments: {names}.')
            values = [normalize_parameter(parameter, value) for parameter, value in zip(parameters, values)]
        # Keep the existing database field. Quoting here preserves spaces and
        # apostrophes when the worker later recovers the individual arguments.
        return shlex.join(values), ''
    except ValueError as error:
        return '', str(error)
