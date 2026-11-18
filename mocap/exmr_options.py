"""Lightweight ExMR settings; safe to import in the editor process."""
import json

from .hip_motion import GAIN_LIMITS, BEND_LIMITS

DEFAULTS = {'static_camera': True, 'smoothing': 'global',
            'hip_motion': False, 'hip_sway_gain': 1.0, 'hip_bob_gain': 1.0}


def _gain(value, name):
    try:
        gain = float(value)
    except (TypeError, ValueError):
        raise ValueError('Invalid ExMR settings') from None
    if not GAIN_LIMITS[0] <= gain <= GAIN_LIMITS[1]:
        raise ValueError(f'ExMR {name} must be within {GAIN_LIMITS[0]}-{GAIN_LIMITS[1]}')
    return gain


def _bend(value):
    try:
        bend = float(value)
    except (TypeError, ValueError):
        raise ValueError('Invalid ExMR settings') from None
    if not BEND_LIMITS[0] <= bend <= BEND_LIMITS[1]:
        raise ValueError(f'ExMR leg refit must be within {BEND_LIMITS[0]}-{BEND_LIMITS[1]}')
    return bend


def options(value=None):
    value = {**DEFAULTS, **(value or {})}
    if type(value['static_camera']) is not bool or value['smoothing'] not in ('global', 'none'):
        raise ValueError('Invalid ExMR settings')
    if type(value['hip_motion']) is not bool:
        raise ValueError('Invalid ExMR settings')
    value['hip_sway_gain'] = _gain(value['hip_sway_gain'], 'hip sway gain')
    value['hip_bob_gain'] = _bend(value['hip_bob_gain'])
    return {key: value[key] for key in DEFAULTS}


def saved(project, state=None):
    state = state or json.loads((project/'project.json').read_text(encoding='utf-8'))
    return options(state.get('exmr_options'))
