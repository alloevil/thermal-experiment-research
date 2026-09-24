import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CsvAttributesTests(unittest.TestCase):
    def test_crlf_preserved_but_real_trailing_whitespace_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)

            def git(*arguments):
                return subprocess.run(['git', *arguments], cwd=directory, capture_output=True, check=False)

            self.assertEqual(git('init', '-q').returncode, 0)
            (directory / '.gitattributes').write_bytes((ROOT / '.gitattributes').read_bytes())
            for cutoff in [100, 300]:
                relative = f'real_data/tclab/assessment_examples/before-{cutoff}/prediction.csv'
                target = directory / relative
                target.parent.mkdir(parents=True)
                original = (ROOT / relative).read_bytes()
                self.assertIn(b'\r\n', original)
                target.write_bytes(original)
                self.assertEqual(git('add', '.gitattributes', relative).returncode, 0)
                self.assertEqual(git('diff', '--cached', '--check').returncode, 0)
                self.assertEqual(git('show', ':' + relative).stdout, original)
                target.write_bytes(original.replace(b'\r\n', b' \r\n', 1))
                self.assertEqual(git('add', relative).returncode, 0)
                rejected = git('diff', '--cached', '--check')
                self.assertNotEqual(rejected.returncode, 0)
                self.assertIn(b'trailing whitespace', rejected.stdout)
                target.write_bytes(original)
                self.assertEqual(git('add', relative).returncode, 0)
            unrelated = directory / 'unrelated.csv'
            unrelated.write_bytes(b'column\r\nvalue\r\n')
            self.assertEqual(git('add', 'unrelated.csv').returncode, 0)
            self.assertNotEqual(git('diff', '--cached', '--check').returncode, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
