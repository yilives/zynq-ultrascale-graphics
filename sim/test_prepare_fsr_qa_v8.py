"""Device-free tests; mock build/runtime receipts exist only in a temporary tree."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare_fsr_qa_v8', ROOT / 'scripts/prepare_fsr_qa_v8.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class GeneratorTests(unittest.TestCase):
    def fixture(self, target):
        def copy(name):
            path = target / name.replace('\\', '/')
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name.replace('\\', '/'), path)

        def write(name, data):
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        def document(name, value):
            write(name, (json.dumps(value, indent=2) + '\n').encode())

        for name in generator.TEMPLATE_HASHES:
            copy(name)
        copy('build/fsr-pl/fixed-v7/source-manifest.json')
        for name in ('build/fsr-pl/fixed-v8/source-manifest.json',
                     'build/fsr-pl/fixed-v8/video/source-manifest.json',
                     'build/fsr-pl/fixed-v8/video/regression-r2/result.json'):
            copy(name)
            value = generator.read_json(ROOT / name)
            for field in ('files', 'originals', 'shared_originals_unchanged'):
                for path in value.get(field, {}):
                    copy(path)
            for command in value.get('commands', []):
                copy(command['log'])
        copy('build/fsr-pl/fixed-v8/cosim/manifest.json')
        copy('build/fsr-pl/fixed-v8/cosim/hls-absolute/solution1/sim/report/rix_fsr1_hls_cosim.rpt')
        for profile in ('fixed-v7', 'fixed-v8'):
            for name in ('functional.json', 'stress/result.json'):
                copy('report/fsr-pl/' + profile + '/' + name)
            functional = generator.read_json(ROOT / ('report/fsr-pl/' + profile + '/functional.json'))
            for row in functional['cases']:
                copy('report/fsr-pl/' + profile + '/' + row['id'] + '.xrgb')
            stress = generator.read_json(ROOT / ('report/fsr-pl/' + profile + '/stress/result.json'))
            for row in stress['cases']:
                copy('report/fsr-pl/' + profile + '/stress/' + row['id'] + '-fixed.xrgb')
                if profile == 'fixed-v8':
                    copy('report/fsr-pl/' + profile + '/stress/' + row['id'] + '.rgb565')
        for scene in ('mc-live64', 'mc-terrain32-0', 'mc-terrain32-9'):
            copy('report/classicube-fsr-comparison-20261023/' + scene + '/source.rgb565')
        write('build/fsr-pl/fixed-v8/board-build.stdout.log',
              b'MOCK FIXTURE ONLY\nFSR_BOARD_ROUTED_AND_EXPORTED profile=fixed-v8\n')
        for name in ('fsr_routed.dcp', 'fsr.bit', 'fsr.bin'):
            write('build/fsr-pl/fixed-v8/board/' + name, b'MOCK FIXTURE ONLY: ' + name.encode())
        for name in ('timing', 'utilization', 'drc', 'cdc', 'bus-skew', 'route-status'):
            write('report/fsr-pl/fixed-v8/board/' + name + '.rpt', b'MOCK FIXTURE ONLY\n')
        bit_sha = generator.digest(target / 'build/fsr-pl/fixed-v8/board/fsr.bin')
        source_sha = generator.digest(target / 'build/fsr-pl/fixed-v8/source-manifest.json')
        required = ['build/fsr-pl/fixed-v8/board-build.stdout.log',
                    'build/fsr-pl/fixed-v8/source-manifest.json']
        required += ['build/fsr-pl/fixed-v8/board/' + n for n in ('fsr_routed.dcp', 'fsr.bit', 'fsr.bin')]
        required += ['report/fsr-pl/fixed-v8/board/' + n + '.rpt'
                     for n in ('timing', 'utilization', 'drc', 'cdc', 'bus-skew', 'route-status')]
        required += ['build/fsr-pl/fixed-v8/video/' + n
                     for n in ('source-manifest.json', 'regression-r2/result.json',
                               'rix_scaler.v', 'rasterix_linux_top.v')]
        acceptance = dict(passed=True, profile='fixed-v8', raw_sha256=bit_sha,
                          raw_bytes=(target / 'build/fsr-pl/fixed-v8/board/fsr.bin').stat().st_size,
                          FPGA_programming_included=False,
                          files={name: generator.digest(target / name) for name in required})
        document('report/fsr-pl/fixed-v8/board/acceptance.json', acceptance)
        header = ('#define FSR_PL_BIT_SHA256 "' + bit_sha + '"\n'
                  '#define FSR_PL_SOURCE_SHA256 "' + source_sha + '"\n').encode()
        write('build/fsr-pl/fixed-v8/runtime/fsr_pl_build.hpp', header)
        elf = bytearray(64)
        elf[:6] = b'\x7fELF\x02\x01'
        struct.pack_into('<H', elf, 18, 183)
        write('build/fsr-pl/fixed-v8/runtime/rix-fsr-pl', elf)
        write('build/fsr-pl/fixed-v8/runtime/rix-fsr-pl-host', b'MOCK HOST EXECUTABLE; NEVER RUN')
        runtime = dict(profile='fixed-v8', revision='r1', bit_sha256=bit_sha,
                       source_sha256=source_sha,
                       files={name: generator.digest(target / 'build/fsr-pl/fixed-v8/runtime' / name)
                              for name in ('fsr_pl_build.hpp', 'rix-fsr-pl', 'rix-fsr-pl-host')})
        document('build/fsr-pl/fixed-v8/runtime/manifest.json', runtime)

    def test_preflight_rejections_and_source_generation(self):
        with tempfile.TemporaryDirectory(prefix='fsr-qa-v8-fixture-') as directory:
            root = Path(directory)
            self.fixture(root)
            acceptance_path = root / 'report/fsr-pl/fixed-v8/board/acceptance.json'
            original_acceptance = acceptance_path.read_bytes()
            value = json.loads(original_acceptance)
            value['passed'] = False
            acceptance_path.write_text(json.dumps(value))
            with self.assertRaisesRegex(RuntimeError, 'acceptance is incomplete'):
                generator.generate(root)
            self.assertFalse(any((root / name).exists() for name in generator.TARGETS))
            acceptance_path.write_bytes(original_acceptance)
            runtime_path = root / 'build/fsr-pl/fixed-v8/runtime/manifest.json'
            original_runtime = runtime_path.read_bytes()
            value = json.loads(original_runtime)
            value['bit_sha256'] = '0' * 64
            runtime_path.write_text(json.dumps(value))
            with self.assertRaisesRegex(RuntimeError, 'not bound'):
                generator.generate(root)
            self.assertFalse(any((root / name).exists() for name in generator.TARGETS))
            runtime_path.write_bytes(original_runtime)
            raw_path = root / 'build/fsr-pl/fixed-v8/board/fsr.bin'
            original_raw = raw_path.read_bytes()
            raw_path.write_bytes(original_raw + b'tamper')
            with self.assertRaisesRegex(RuntimeError, 'File SHA256 mismatch'):
                generator.generate(root)
            self.assertFalse(any((root / name).exists() for name in generator.TARGETS))
            raw_path.write_bytes(original_raw)
            templates_before = {name: generator.digest(root / name) for name in generator.TEMPLATE_HASHES}
            report = generator.generate(root)
            self.assertTrue(report['passed'])
            self.assertFalse(report['board_qa_execution_included'])
            self.assertEqual(report['numeric_cases_verified'], 19)
            for name, expected in report['files'].items():
                self.assertEqual(generator.digest(root / name), expected)
            board = (root / generator.TARGETS[0]).read_text(encoding='utf-8')
            live = (root / generator.TARGETS[1]).read_text(encoding='utf-8')
            self.assertIn('test_fsr_pl_board_v8.py', live)
            self.assertIn("result.get('passed') is True", live)
            self.assertIn('32 * 1024**2', board)
            self.assertIn('16 * 1024**2', board)
            self.assertIn('process.send_signal(signal.SIGTERM)', board)
            self.assertNotIn('signal.SIGKILL', board + live)
            self.assertIn('Runtime SHA256 is not the reviewed fixed-v8 r1 build', board)
            self.assertEqual(templates_before, {name: generator.digest(root / name) for name in generator.TEMPLATE_HASHES})
            with self.assertRaisesRegex(RuntimeError, 'already exists'):
                generator.generate(root)

    def test_duplicate_json_and_path_escape(self):
        with tempfile.TemporaryDirectory(prefix='fsr-qa-v8-path-fixture-') as directory:
            root = Path(directory)
            duplicate = root / 'duplicate.json'
            duplicate.write_text('{"passed":true,"passed":false}')
            with self.assertRaisesRegex(RuntimeError, 'Duplicate JSON'):
                generator.read_json(duplicate)
            with self.assertRaisesRegex(RuntimeError, 'escapes workspace'):
                generator.local_path(root, '../outside')
            with self.assertRaisesRegex(RuntimeError, 'escapes workspace'):
                generator.local_path(root, 'C:/outside')


if __name__ == '__main__':
    unittest.main()
