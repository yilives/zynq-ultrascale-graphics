#!/usr/bin/env python3
"""Compare presentation scheduling on the real LCD, using the same game build."""
import argparse, json, os, re, subprocess
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('prefix')
parser.add_argument('seconds', type=int, nargs='?', default=18)
parser.add_argument('strategies', nargs='*', choices=('pipeline', 'serial', 'async'))
parser.add_argument('--async-fps-limit', type=int, choices=(60, 120), default=60)
args = parser.parse_args()
prefix = args.prefix
assert re.fullmatch(r'cc_perf_[a-z0-9_]+', prefix)
seconds = args.seconds
strategies = args.strategies or ['pipeline', 'serial', 'async', 'pipeline']
assert all(s in ('pipeline', 'serial', 'async') for s in strategies)
out = Path('/tmp/postproc-tests')
records = []
supports_option = b'--present-strategy' in subprocess.check_output(['rix-classicube', '--help'])
for i, strategy in enumerate(strategies):
    name = '%s_%d_%s' % (prefix, i, strategy)
    env = os.environ.copy()
    env['RIX_PRESENT_STRATEGY'] = strategy
    # Keep presentation validation enabled, including the final queue drain.
    env.pop('RIX_PRESENT_SYNC', None)
    command = ['rix-classicube', '--attempt', name, '--seconds', str(seconds),
               '--world-size', '64', '--view-distance', '32', '--autoplay', '--capture',
               '--fps-limit', str(args.async_fps_limit if strategy == 'async' else 60)]
    if supports_option:
        command += ['--present-strategy', strategy]
    with Path('/tmp/' + name + '.log').open('w') as log:
        result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT)
    data = json.loads((out / name / 'result.json').read_text())
    data['presentation_strategy'] = strategy
    records.append(data)
    report = out / (prefix + '.json')
    temporary = report.with_suffix('.json.incoming')
    temporary.write_text(json.dumps(records, indent=2) + '\n')
    temporary.replace(report)
    assert result.returncode == 0 and data['passed'], data
    print('CLASSICUBE_PERFORMANCE', name, data['hardware_window'], flush=True)
assert not subprocess.run(['pidof', 'ClassiCube'], stdout=subprocess.PIPE).stdout
print('CLASSICUBE_PERFORMANCE_PASS', prefix, flush=True)
