"""Convert bounded execution events into public activity messages."""
import json
import math


def public_activity(events):
    """Use fixed templates so logs cannot expose model prose, secrets, or traces."""
    if not isinstance(events, list) or len(events) > 32:
        raise ValueError("Invalid activity log")
    output = []
    for event in events:
        kind = event['kind']
        elapsed = event['elapsed_seconds']
        if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError('Invalid event timestamp')
        attempt = event.get('attempt', 0)
        if type(attempt) is not int or not 0 <= attempt <= 3:
            raise ValueError('Invalid event attempt')
        phase = 'observing'
        if kind == 'observing':
            runs = event.get('runs')
            if runs is not None and (type(runs) is not int or runs < 1):
                raise ValueError('Invalid run count')
            prefix = f'{runs} runs per mode: ' if runs is not None else ''
            message = prefix + 'running the target alone, with shuffled neighbors, and in file order.'
        elif kind in ('observed', 'verified'):
            rates = event['rates']
            values = [rates[key] for key in ('baseline_pass_rate', 'shuffled_pass_rate', 'full_suite_pass_rate')]
            if not all(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 100 for value in values):
                raise ValueError('Invalid event pass rates')
            prefix = 'Original test' if kind == 'observed' else f'Attempt {attempt}'
            message = f'{prefix}: isolated {values[0]:.1f}%, shuffled {values[1]:.1f}%, suite {values[2]:.1f}% passed.'
            phase = 'diagnosing' if kind == 'observed' else 'verifying'
        elif kind == 'diagnosed':
            category = event['category']
            if category not in ('Deterministic Pass', 'Deterministic Failure', 'Order Dependency', 'Standalone Flakiness', 'Complex Flakiness'):
                raise ValueError('Invalid diagnosis category')
            names = event['suspicious_vars']
            if not isinstance(names, list) or not all(isinstance(name, str) and name.isidentifier() and len(name) <= 100 for name in names):
                raise ValueError('Invalid shared-variable names')
            variables = ', '.join(names) if names else 'none detected'
            message = f'Rule-based diagnosis: {category}. AST shared-state candidates: {variables}.'
            phase = 'diagnosing'
        elif kind == 'repairing':
            message = f'Attempt {attempt}: requesting a repair using the source, diagnosis, and failure evidence.'
            phase = 'repairing'
        elif kind == 'verifying':
            message = f'Attempt {attempt}: patch written to the temporary copy. Rerunning the experiments.'
            phase = 'verifying'
        elif kind == 'retrying':
            message = (f'Attempt {attempt}: verification did not meet the pass-rate requirement.'
                       if event.get('reason') == 'verification_failed'
                       else f'Attempt {attempt}: generation or execution failed; details stay in server logs.')
            phase = 'repairing'
        elif kind == 'restored':
            message = 'Original test file restored; no verified repair was kept.'
            phase = 'verifying'
        elif kind == 'completed':
            if type(event['success']) is not bool:
                raise ValueError('Invalid completion event')
            message = 'Run finished successfully.' if event['success'] else 'Run finished without a verified repair.'
            phase = 'complete'
        else:
            raise ValueError('Unknown activity event')
        output.append({'elapsed_seconds': elapsed, 'phase': phase, 'message': message})
    return output


def read_activity(directory, secret=''):
    """Read an atomic progress snapshot, never follow a report symlink."""
    path = directory / 'progress.json'
    try:
        if path.is_symlink() or path.stat().st_size > 65536:
            return []
        events = public_activity(json.loads(path.read_text(encoding='utf-8')))
        if secret and secret in json.dumps(events):
            return []
        return events
    except (OSError, ValueError, KeyError, TypeError):
        return []
