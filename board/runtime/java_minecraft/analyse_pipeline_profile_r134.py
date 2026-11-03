"""Summarize inclusive phase counters inside the real Java world interval."""
import argparse
import json
from pathlib import Path
import re


def summarize(folder):
    log = (folder / 'minecraft.log').read_text(errors='replace')
    begin = int(re.search(r'JAVA_WORLD_MONO_START (\d+)', log)[1])
    end = int(re.search(r'JAVA_WORLD_MONO_END (\d+)', log)[1])
    assert begin < end
    rows = [json.loads(line) for line in (folder / 'pipeline-profile.jsonl').read_text().splitlines()]
    assert all(a['ns'] <= b['ns'] for a, b in zip(rows, rows[1:]))
    window = [row for row in rows if begin <= row['ns'] <= end]
    assert len(window) >= 10
    left, right = window[0], window[-1]
    seconds = (right['ns'] - left['ns']) / 1e9
    phases = {}
    for name, a in left['phases'].items():
        b = right['phases'][name]
        delta = {key: b[key] - a[key] for key in a}
        assert min(delta.values()) >= 0
        phases[name] = dict(delta, wall_seconds=delta['wall_ns'] / 1e9,
                            cpu_seconds=delta['cpu_ns'] / 1e9,
                            wall_fraction=delta['wall_ns'] / (seconds * 1e9),
                            one_core_cpu_fraction=delta['cpu_ns'] / (seconds * 1e9),
                            mean_wall_us=delta['wall_ns'] / max(1, delta['calls']) / 1000,
                            units_per_second=delta['units'] / seconds)
    return dict(passed=True, seconds=seconds, sample_begin_ns=left['ns'], sample_end_ns=right['ns'],
                phases=phases, diagnostic_only=True, exclusive_times=False,
                caveats=[
                    'Nested and concurrent totals must not be added.',
                    'Scopes are counted on completion; window edges have in-flight scope skew.',
                    'DMA lifetime is submit-to-observed-FINISH; includes producer delay and downstream backpressure.',
                    'Request delay includes START, intervening work and time before FINISH; not DMA idle time.',
                    'CPU timer/logging overhead is included; not corrected.',
                    'Physical DMA saturation requires additional hardware flow-control measurements.'
                ])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    result = summarize(args.folder)
    (args.folder / 'pipeline-summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
