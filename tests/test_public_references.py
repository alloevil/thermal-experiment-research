import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_public_references import check_references


class PublicReferenceChecks(unittest.TestCase):
    def fixture(self, root):
        for directory in ['docs', 'sources', 'feasibility/upstream']:
            (root / directory).mkdir(parents=True, exist_ok=True)
        text = '# External reference: content not redistributed\n\nhttps://example.org/paper\n'
        (root / 'sources/paper.pdf.source.md').write_text(text)
        for name in ['pde-LICENSE', 'botorch-LICENSE']:
            (root / 'feasibility/upstream' / name).write_bytes((ROOT / 'feasibility/upstream' / name).read_bytes())
        item = {'path': 'sources/paper.pdf', 'action': 'omitted_binary_with_source_notice',
                'notice_path': 'sources/paper.pdf.source.md', 'public_notice_sha256': hashlib.sha256(text.encode()).hexdigest(),
                'source_urls': ['https://example.org/paper']}
        (root / 'docs/reference-publication.json').write_text(json.dumps({'entries': [item]}))

    def test_real_public_references(self):
        self.assertEqual(check_references(ROOT), 59)

    def test_reference_only_fixture(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            self.assertEqual(check_references(root), 1)

    def test_restored_pdf_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            (root / 'sources/paper.pdf').write_bytes(b'%PDF withheld')
            with self.assertRaisesRegex(ValueError, 'restored'):
                check_references(root)

    def test_tampered_notice_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            (root / 'sources/paper.pdf.source.md').write_text('external full text')
            with self.assertRaisesRegex(ValueError, 'changed'):
                check_references(root)

    def test_upstream_license_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            (root / 'feasibility/upstream/botorch-LICENSE').write_text('omitted')
            with self.assertRaisesRegex(ValueError, 'Missing upstream license'):
                check_references(root)


if __name__ == '__main__':
    unittest.main()
