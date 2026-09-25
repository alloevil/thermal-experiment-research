import hashlib
import importlib.util
import json
import re
import shutil
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('case_site_build', ROOT / 'web/build.py')
SITE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SITE)


class PageParser(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.elements = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class CaseSiteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def test_real_page_has_static_results_full_series_and_semantics(self):
        content = SITE.render()
        parsed = PageParser(content)
        self.assertEqual(sum(tag == 'h1' for tag, attrs in parsed.elements), 1)
        self.assertIn('1.058', content)
        self.assertIn('13.556', content)
        self.assertIn('1.031', content)
        self.assertIn('2.169', content)
        self.assertIn('默认假设 · 未估计', content)
        self.assertIn('拟合触下界', content)
        self.assertIn('不是两次独立实验', content)
        panels = [attrs for tag, attrs in parsed.elements if 'data-case' in attrs]
        self.assertEqual(len(panels), 2)
        self.assertTrue(all('hidden' not in panel for panel in panels))
        curves = [attrs for tag, attrs in parsed.elements if tag == 'polyline']
        self.assertEqual(len(curves), 16)
        self.assertTrue(all(len(curve['points'].split()) == 599 for curve in curves))
        records = json.loads(re.search(r'<script id="case-data" type="application/json">(.*?)</script>', content, re.S).group(1))
        for cutoff in [100, 300]:
            report, rows = SITE.load_case(cutoff)
            self.assertEqual(records[str(cutoff)], rows)
            self.assertEqual(report['selection']['training_rows'], cutoff)

    def test_deterministic_build_and_evidence_copies(self):
        first = SITE.build(self.directory / 'first')
        second = SITE.build(self.directory / 'second')
        files = [path.relative_to(first) for path in first.rglob('*') if path.is_file()]
        for relative in files:
            self.assertEqual((first / relative).read_bytes(), (second / relative).read_bytes(), str(relative))
        for item in json.loads((first / 'evidence/manifest.json').read_text()):
            self.assertEqual(hashlib.sha256((first / item['file']).read_bytes()).hexdigest(), item['sha256'])
        for cutoff in [100, 300]:
            original = SITE.CASE / f'assessment_examples/before-{cutoff}/prediction.csv'
            self.assertEqual((first / f'evidence/before-{cutoff}/prediction.csv').read_bytes(), original.read_bytes())

    def test_preview_is_not_indexable_or_falsely_published(self):
        target = SITE.build(self.directory / 'preview')
        content = (target / 'index.html').read_text()
        self.assertIn('noindex, nofollow', content)
        self.assertNotIn('rel="canonical"', content)
        self.assertFalse((target / 'sitemap.xml').exists())
        self.assertIn('Disallow: /', (target / 'robots.txt').read_text())
        self.assertIn('尚未部署', content)

    def test_release_metadata_uses_explicit_base_path(self):
        target = SITE.build(self.directory / 'release', 'https://example.org/research')
        content = (target / 'index.html').read_text()
        self.assertIn('href="https://example.org/research/"', content)
        self.assertIn('content="https://example.org/research/social-card.png"', content)
        self.assertIn('index, follow', content)
        self.assertNotIn('noindex', content)
        self.assertNotIn('尚待发布', content)
        self.assertNotIn('尚待推送', content)
        self.assertNotIn('preview-note', content)
        self.assertIn('<loc>https://example.org/research/</loc>', (target / 'sitemap.xml').read_text())
        schema = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', content, re.S).group(1))
        self.assertEqual(schema['@type'], 'TechArticle')
        self.assertEqual(schema['url'], 'https://example.org/research/')
        self.assertNotIn('aggregateRating', schema)
        self.assertNotIn('license', schema)

    def test_rejects_unsafe_base_and_existing_output(self):
        for value in ['http://example.org', 'javascript:alert(1)', 'https://user:secret@example.org',
                      'https://example.org/?q=x', 'https://example.org/#bad', 'https://example.org/a/../b',
                      'https://example.org/a"b', 'https://example.org/ bad']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                SITE.build(self.directory / 'unused', value)
        self.assertFalse((self.directory / 'unused').exists())
        with self.assertRaisesRegex(ValueError, 'Output exists'):
            SITE.build(self.directory)
        link = self.directory / 'dangling'
        link.symlink_to(self.directory / 'absent')
        with self.assertRaisesRegex(ValueError, 'Output exists'):
            SITE.build(link)

    def test_local_resources_fragments_and_runtime_are_self_contained(self):
        target = SITE.build(self.directory / 'site')
        content = (target / 'index.html').read_text()
        parser = PageParser(content)
        ids = [attrs['id'] for tag, attrs in parser.elements if 'id' in attrs]
        self.assertEqual(len(ids), len(set(ids)))
        for tag, attrs in parser.elements:
            for field in ['src', 'href']:
                value = attrs.get(field, '')
                if value.startswith('#'):
                    self.assertIn(value[1:], ids)
                elif value and not value.startswith('https://'):
                    self.assertTrue((target / value).is_file(), value)
                if field == 'src':
                    self.assertNotIn('://', value)
        javascript = (target / 'app.js').read_text()
        for forbidden in ['fetch(', 'XMLHttpRequest', 'localStorage', 'innerHTML', 'eval(']:
            self.assertNotIn(forbidden, javascript)

    def test_tampered_score_or_prediction_is_rejected(self):
        case = self.directory / 'case'
        shutil.copytree(SITE.CASE, case)
        folder = case / 'assessment_examples/before-100'
        path = folder / 'report.json'
        original = path.read_bytes()
        report = json.loads(original)
        report['validation_metrics']['rmse_C'] += 1
        path.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, 'RMSE'):
            SITE.load_case(100, case)
        path.write_bytes(original)
        csv_path = folder / 'prediction.csv'
        rows = csv_path.read_text().splitlines()
        fields = rows[2].split(',')
        fields[4] = str(float(fields[4]) + 20)
        rows[2] = ','.join(fields)
        csv_path.write_text('\n'.join(rows) + '\n')
        with self.assertRaisesRegex(ValueError, 'RMSE'):
            SITE.load_case(100, case)

    def test_tampered_source_is_rejected(self):
        case = self.directory / 'case'
        shutil.copytree(SITE.CASE, case)
        path = case / 'thermal_model.py'
        path.write_text(path.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            SITE.load_case(100, case)


if __name__ == '__main__':
    unittest.main(verbosity=2)
