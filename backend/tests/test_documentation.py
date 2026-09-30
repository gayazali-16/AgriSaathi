import hashlib
import re

from backend.config import ROOT
from scripts.check_docs import check_url, local_checks


def test_current_documentation_targets_and_architecture_receipt():
    errors, urls = local_checks()
    assert errors == []
    assert urls
    receipt = (ROOT / 'docs/runtime-architecture-validation.md').read_text(encoding='utf-8')
    for name in ['runtime-architecture.json', 'runtime-architecture.html']:
        digest = hashlib.sha256((ROOT / 'docs' / name).read_bytes()).hexdigest()
        assert digest in receipt
    assert not re.search(r'(?:localhost|127\.0\.0\.1):5173', (ROOT / 'README.md').read_text(encoding='utf-8'))


def test_markdown_link_urls_are_extracted_without_surrounding_syntax():
    _, urls = local_checks()
    assert 'http://localhost:5174' in urls
    assert all('](' not in url for url in urls)
    assert 'not probed' in check_url('http://localhost:5174')['status']


def test_submission_setup_and_dataset_citations_are_standalone():
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    assert 'https://github.com/gayazali-16/AgriSaathi.git' in readme
    assert 'Copy-Item .env.example .env' in readme
    assert 'python -m venv .venv' in readme
    assert 'npm ci' in readme
    assert 'empty case/advisory history' in readme
    assert 'Code-for-Communities.git' not in readme
    assert (ROOT / 'DEPLOYMENT_GUIDE.md').is_file()
    assert (ROOT / '.gcloudignore').is_file()
    assert (ROOT / 'docs/sources/crop-dataset-README.md').is_file()
    assert (ROOT / 'docs/sources/crop-dataset-references.pdf').is_file()
    assert (ROOT / 'docs/sources/ARCHIFY-LICENSE').is_file()
