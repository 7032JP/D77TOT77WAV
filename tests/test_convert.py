#!/usr/bin/env python3
"""End-to-end tests for d77_to_t77_chunks.py.

Four cases cover every pass plan the planner can produce:

    n1          N = 1                      (single pass, rev_last)
    n2_simple   N = 2, entry >= $2000      (SIMPLE: rev_int + rev_last)
    n2_article  N = 2, entry <  $2000      (ARTICLE: stash + relocate2)
    n3          N = 3, entry >= $2000      (SIMPLE: rev_int x2 + fwd_last)

For each case the converter is run on a generated fixture (see
make_fixtures.py) and the outputs are compared with tests/expected/:

    <case>.txt      procedure text, compared verbatim (diff shown on failure)
    <case>.sha256   SHA-256 of the T77 and the WAV (too large to check in)

The WAV header is additionally validated as 44.1 kHz / 16-bit / mono PCM.

Run from the repository root:

    python3 -m unittest discover -s tests -v
    tests/run.sh

Set UPDATE_EXPECTED=1 to rewrite tests/expected/ from the current output
(only after confirming the change in behaviour is intended).
"""

import difflib
import hashlib
import os
import re
import struct
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import make_fixtures  # noqa: E402

SCRIPT = os.path.join(ROOT, 'd77_to_t77_chunks.py')
EXPECTED_DIR = os.path.join(HERE, 'expected')
OUT_DIR = os.environ.get('D77TOT77WAV_TEST_OUT', os.path.join(HERE, 'out'))
UPDATE = os.environ.get('UPDATE_EXPECTED', '') not in ('', '0')

CHUNK_SIZE = 0x4000
WAV_SAMPLE_RATE = 44100


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def _read_sha256_file(path):
    """Parse `<hex>  <name>` lines (sha256sum format)."""
    out = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            digest, name = line.split(None, 1)
            out[name.lstrip('*')] = digest
    return out


class ConvertTest(unittest.TestCase):
    fixtures = None

    @classmethod
    def setUpClass(cls):
        os.makedirs(OUT_DIR, exist_ok=True)
        cls.fixtures = make_fixtures.write_fixtures(OUT_DIR)

    # ---- helpers --------------------------------------------------------

    def _run_case(self, case, fixture, addr):
        t77 = os.path.join(OUT_DIR, case + '.t77')
        txt = os.path.join(OUT_DIR, case + '.txt')
        wav = os.path.join(OUT_DIR, case + '.wav')
        for p in (t77, txt, wav):
            if os.path.exists(p):
                os.remove(p)
        cmd = [sys.executable, SCRIPT, self.fixtures[fixture],
               '--addr', '0x%04X' % addr,
               '-o', t77, '-t', txt, '-w', wav]
        proc = subprocess.run(cmd, cwd=OUT_DIR, capture_output=True,
                              text=True, encoding='utf-8')
        self.assertEqual(proc.returncode, 0,
                         'converter failed (%d)\n--- stdout ---\n%s\n--- stderr ---\n%s'
                         % (proc.returncode, proc.stdout, proc.stderr))
        return proc.stdout, t77, txt, wav

    def _check_plan(self, stdout, n_expected, variants_expected):
        m = re.search(r'split into\s*:\s*(\d+) x 16 KiB chunk', stdout)
        self.assertIsNotNone(m, 'chunk count line missing from stdout')
        self.assertEqual(int(m.group(1)), n_expected, 'unexpected chunk count')
        variants = re.findall(r'^\s*tape\[\d+/\d+\]\s+C\d+\s+\[([^\]]+)\]',
                              stdout, re.M)
        variants = [v.strip() for v in variants]
        self.assertEqual(variants, variants_expected, 'unexpected pass plan')

    def _check_txt(self, case, txt_path):
        with open(txt_path, encoding='utf-8') as f:
            actual = f.read()
        exp_path = os.path.join(EXPECTED_DIR, case + '.txt')
        if UPDATE:
            with open(exp_path, 'w', encoding='utf-8') as f:
                f.write(actual)
            return
        self.assertTrue(os.path.isfile(exp_path),
                        'missing expected file %s (run with UPDATE_EXPECTED=1)' % exp_path)
        with open(exp_path, encoding='utf-8') as f:
            expected = f.read()
        if actual != expected:
            diff = ''.join(difflib.unified_diff(
                expected.splitlines(True), actual.splitlines(True),
                fromfile='expected/' + case + '.txt',
                tofile='out/' + case + '.txt'))
            self.fail('procedure TXT differs from expected:\n' + diff)

    def _check_wav_header(self, wav_path):
        size = os.path.getsize(wav_path)
        with open(wav_path, 'rb') as f:
            head = f.read(44)
        self.assertEqual(head[0:4], b'RIFF')
        self.assertEqual(head[8:12], b'WAVE')
        self.assertEqual(head[12:16], b'fmt ')
        (fmt_size, fmt_tag, channels, rate, byte_rate,
         block_align, bits) = struct.unpack('<IHHIIHH', head[16:36])
        self.assertEqual(fmt_size, 16)
        self.assertEqual(fmt_tag, 1)                     # PCM
        self.assertEqual(channels, 1)
        self.assertEqual(rate, WAV_SAMPLE_RATE)
        self.assertEqual(bits, 16)
        self.assertEqual(block_align, 2)
        self.assertEqual(byte_rate, WAV_SAMPLE_RATE * 2)
        self.assertEqual(head[36:40], b'data')
        riff_size, = struct.unpack('<I', head[4:8])
        data_size, = struct.unpack('<I', head[40:44])
        self.assertEqual(riff_size, size - 8)
        self.assertEqual(data_size, size - 44)
        self.assertEqual(data_size % 2, 0)

    def _check_hashes(self, case, t77_path, wav_path):
        actual = {case + '.t77': _sha256(t77_path),
                  case + '.wav': _sha256(wav_path)}
        exp_path = os.path.join(EXPECTED_DIR, case + '.sha256')
        if UPDATE:
            with open(exp_path, 'w', encoding='utf-8') as f:
                for name in sorted(actual):
                    f.write('%s  %s\n' % (actual[name], name))
            return
        self.assertTrue(os.path.isfile(exp_path),
                        'missing expected file %s (run with UPDATE_EXPECTED=1)' % exp_path)
        expected = _read_sha256_file(exp_path)
        for name in sorted(actual):
            self.assertIn(name, expected, 'no expected SHA-256 for ' + name)
            self.assertEqual(actual[name], expected[name],
                             'SHA-256 mismatch for ' + name)

    def _check_case(self, case):
        entry = next(c for c in make_fixtures.CASES if c[0] == case)
        _, fixture, _, addr, n_expected, variants = entry
        stdout, t77, txt, wav = self._run_case(case, fixture, addr)
        self._check_plan(stdout, n_expected, variants)
        self._check_txt(case, txt)
        self._check_wav_header(wav)
        self._check_hashes(case, t77, wav)

    # ---- the four cases ---------------------------------------------------

    def test_n1(self):
        self._check_case('n1')

    def test_n2_simple(self):
        self._check_case('n2_simple')

    def test_n2_article(self):
        self._check_case('n2_article')

    def test_n3(self):
        self._check_case('n3')


class TrampolineBinTest(unittest.TestCase):
    """Static checks on the shipped trampoline .bin templates.

    Stage 1 copies the bytes from offset STAGE1_SIZE up to (but excluding)
    the CMPX #imm operand to $D000 and runs them there. Anything that reads
    $FD0F (ROM overlay ON) must NOT be inside that copied range: as soon as
    the overlay is back on, $8000-$FBFF is the BASIC ROM, so code running at
    $D000 can not execute its own following bytes.
    """

    STAGER_LOAD_ADDR = 0x1400
    STAGE1_SIZE = 26
    CMPX_IMM_OFFSET = 18          # Stage 1: ORCC LDA STA LDX LDY LDA STA -> CMPX
    LDA_ROM_PORT = b'\xB6\xFD\x0F'   # LDA $FD0F (extended)
    BINS = ('trampoline_fwd_int.bin', 'trampoline_rev_int.bin',
            'trampoline_fwd_last.bin', 'trampoline_rev_last.bin',
            'trampoline_relocate2.bin')

    def _stage2_range(self, data):
        self.assertEqual(data[self.CMPX_IMM_OFFSET], 0x8C, 'CMPX #imm expected')
        end_addr = struct.unpack('>H', data[self.CMPX_IMM_OFFSET + 1:
                                            self.CMPX_IMM_OFFSET + 3])[0]
        end = end_addr - self.STAGER_LOAD_ADDR
        self.assertGreater(end, self.STAGE1_SIZE)
        self.assertLessEqual(end, len(data))
        return self.STAGE1_SIZE, end

    def test_rom_on_is_outside_the_copied_range(self):
        for name in self.BINS:
            with self.subTest(bin=name):
                with open(os.path.join(ROOT, name), 'rb') as f:
                    data = f.read()
                start, end = self._stage2_range(data)
                self.assertNotIn(self.LDA_ROM_PORT, data[start:end],
                                 'LDA $FD0F must not run from $D000')
                if name.endswith('_int.bin'):
                    # Stage 2 ends with JMP to the low-RAM return routine
                    # that is left outside the copied range.
                    self.assertEqual(data[end - 3], 0x7E, 'JMP ext expected')
                    ret = struct.unpack('>H', data[end - 2:end])[0]
                    self.assertEqual(ret, self.STAGER_LOAD_ADDR + end)
                    self.assertEqual(data[end:end + 3], self.LDA_ROM_PORT)
                    self.assertEqual(data[end + 3:], b'\x1C\xAF\x39')


if __name__ == '__main__':
    unittest.main()
