"""Expand a parameter-sweep definition into experiment argument sets.

Pure functions with no database access. Preview and creation both call
plan_sweep() so they always agree.

A definition maps manifest parameter names to one of:

    5                                   a fixed value
    [10, 25, 50]                        an explicit list
    {"start": 1, "stop": 9, "step": 2}  an inclusive range (integer/number only)

The grid-search tool's format, {"parameters": {name: [values]}}, is accepted
as well. Omitted parameters use the manifest default.
"""

from decimal import Decimal, InvalidOperation
from itertools import product
import math
from types import SimpleNamespace

from scripts.algorithms import normalize_parameter, validate_algorithm_arguments


RANGE_KEYS = {'start', 'stop', 'step'}


class SweepDefinitionError(ValueError):
    def __init__(self, message, errors=None):
        super().__init__(message)
        self.errors = errors or {}


def _decimal(value, label, key):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f'{label}: range {key} must be a number.')
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        raise ValueError(f'{label}: range {key} must be a number.') from None
    if not number.is_finite():
        raise ValueError(f'{label}: range {key} must be finite.')
    return number


def _range_values(parameter, spec, limit):
    label = parameter.get('label') or parameter['name']
    if parameter['type'] not in ('integer', 'number'):
        raise ValueError(f'{label}: ranges apply only to integer or number parameters.')
    if set(spec) != RANGE_KEYS:
        raise ValueError(f'{label}: a range needs exactly start, stop, and step.')
    start, stop, step = (_decimal(spec[key], label, key) for key in ('start', 'stop', 'step'))
    if step <= 0:
        raise ValueError(f'{label}: step must be greater than zero.')
    if stop < start:
        raise ValueError(f'{label}: stop must be greater than or equal to start.')
    # Decimal arithmetic avoids float drift, so a stop of 0.3 with a step of
    # 0.1 is included. Count first, so a huge range is rejected before any
    # list is built.
    count = int((stop - start) / step) + 1
    if count > limit:
        raise ValueError(f'{label}: this range has {count} values; the limit is {limit}.')
    values = []
    for index in range(count):
        value = start + index * step
        values.append(int(value) if value == value.to_integral_value() else float(value))
    return values


def expand_parameter(parameter, spec, limit):
    """Return the normalized, de-duplicated values for one parameter."""
    label = parameter.get('label') or parameter['name']
    if spec is None:
        if 'default' not in parameter:
            raise ValueError(f'{label} has no default; supply a value.')
        raw = [parameter['default']]
    elif isinstance(spec, dict):
        raw = _range_values(parameter, spec, limit)
    elif isinstance(spec, list):
        if not spec:
            raise ValueError(f'{label}: supply at least one value.')
        if len(spec) > limit:
            raise ValueError(f'{label}: at most {limit} values are allowed.')
        raw = spec
    else:
        raw = [spec]

    values = []
    for value in raw:
        normalized = normalize_parameter(parameter, value)
        # Normalize first, so GINI and gini, or 10 and 10.0, count once.
        if normalized not in values:
            values.append(normalized)
    return values


def unwrap_definition(definition):
    """Accept {name: spec} or the grid-search tool's {"parameters": {name: spec}}."""
    if isinstance(definition, dict) and set(definition) == {'parameters'} and isinstance(definition['parameters'], dict):
        definition = definition['parameters']
    if not isinstance(definition, dict):
        raise SweepDefinitionError('parameters must be an object mapping parameter names to values.')
    return definition


def plan_sweep(manifest, definition, limit):
    """Validate a definition against a manifest and return the sweep plan.

    Returns {'axes': [{'name', 'varied', 'values'}], 'count': int}, with axes
    in manifest order. Raises SweepDefinitionError with per-parameter errors.
    """
    if not manifest or not manifest.get('parameters'):
        raise SweepDefinitionError('Parameter sweeps require an algorithm with a parameter manifest.')
    definition = unwrap_definition(definition)
    parameters = manifest['parameters']
    known = {parameter['name'] for parameter in parameters}
    errors = {name: 'Unknown parameter for this algorithm.' for name in definition if name not in known}

    axes = []
    for parameter in parameters:
        name = parameter['name']
        try:
            values = expand_parameter(parameter, definition.get(name), limit)
            axes.append({'name': name, 'varied': len(values) > 1, 'values': values})
        except ValueError as error:
            errors[name] = str(error)
    if errors:
        raise SweepDefinitionError('Check the highlighted parameters.', errors)

    count = math.prod(len(axis['values']) for axis in axes)
    if count > limit:
        raise SweepDefinitionError(f'This sweep creates {count} runs; the limit is {limit}.')
    return {'axes': axes, 'count': count}


def iter_runs(manifest, plan):
    """Yield (sweep_index, param_values, args) in deterministic order.

    itertools.product over manifest order: the last parameter changes
    fastest. args is the same canonical string a single run would store.
    """
    script = SimpleNamespace(algorithm_config=manifest)
    names = [axis['name'] for axis in plan['axes']]
    for index, combination in enumerate(product(*(axis['values'] for axis in plan['axes']))):
        args, error = validate_algorithm_arguments(script, list(combination))
        if error:
            raise SweepDefinitionError(error)
        yield index, dict(zip(names, combination)), args


def batch_status(counts, cancel_requested):
    """Derive a sweep's status from its runs' status counts. Never stored."""
    if counts.get('Running'):
        return 'Running'
    if counts.get('Queued') or counts.get('Pending'):
        return 'Queued'
    if cancel_requested and counts.get('Cancelled'):
        return 'Cancelled'
    total = sum(counts.values())
    if total and counts.get('Success') == total:
        return 'Success'
    return 'Completed with failures'
