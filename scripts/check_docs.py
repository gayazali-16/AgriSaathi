"""Check local Markdown targets, declared ports, and optional public HTTP links."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

import httpx

from backend.config import ROOT


def local_checks() -> tuple[list[str], set[str]]:
    files = [ROOT / 'README.md', ROOT / 'MANUAL_TESTING_GUIDE.md',
             ROOT / 'THIRD_PARTY_NOTICES.md',
             *sorted((ROOT / 'docs').glob('*.md'))]
    errors, urls = [], set()
    for path in files:
        text = path.read_text(encoding='utf-8')
        # Code samples may contain environment/template expressions, never request these.
        # Markdown links wrap URLs as `[https://example.test](https://example.test)`.
        # Stop at both delimiters so the link label's `](` is not parsed as URL data.
        urls.update(url.rstrip('.,;') for url in re.findall(r"https?://[^\s<>`\"'\)\]]+", text) if '$' not in url and '{' not in url)
        for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', text):
            if target.startswith(('http:', 'https:', '#')):
                continue
            relative = target.split('#')[0]
            if not (path.parent / relative).exists():
                errors.append(f'{path.name}: missing {relative}')
        for port in re.findall(r'(?:localhost|127\.0\.0\.1):(\d+)', text):
            if port not in {'5174', '8000', '8001', '8002', '8081'}:
                errors.append(f'{path.name}: unexplained local port {port}')
    return errors, urls


def check_url(url: str) -> dict:
    parsed_url = urlsplit(url)
    safe_url = parsed_url._replace(query='', fragment='').geturl()
    if parsed_url.hostname in {'127.0.0.1', 'localhost'}:
        return {'url': safe_url, 'status': 'local endpoint; not probed by this report, check in its configured run context'}
    try:
        with httpx.Client(timeout=12, follow_redirects=True) as client:
            response = client.head(url)
            if response.status_code in {403, 405}:
                response = client.get(url)
            resolved = urlsplit(str(response.url))._replace(query='', fragment='').geturl()
            return {'url': safe_url, 'status': response.status_code, 'resolved_url': resolved}
    except httpx.HTTPError as error:
        return {'url': safe_url, 'status': 'unverified', 'error_type': type(error).__name__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--external', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    errors, urls = local_checks()
    results = list(ThreadPoolExecutor(max_workers=4).map(check_url, sorted(urls))) if args.external else []
    report = {'local_errors': errors, 'url_results': results,
              'limits': 'HTTP reachability only. Login/anti-bot/provider restrictions are reported, not silently treated as passes.'}
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    raise SystemExit(bool(errors))


if __name__ == '__main__':
    main()
