#!/usr/bin/env python3
"""Download and preserve one verified Cardmarket guide in an archive directory."""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import pathlib
import sys
import tempfile
import urllib.request
from zoneinfo import ZoneInfo

from cardmarket_history import GUIDE_URL, ingest


class GuideNotReadyError(ValueError):
    """The source still serves a snapshot from a previous day."""


def archive(data, directory, *, now=None, require_today=False):
    # Reuse the local importer's validation before writing any archive file.
    with tempfile.TemporaryDirectory() as temp:
        day, count, _ = ingest(pathlib.Path(temp) / 'check.sqlite', data, GUIDE_URL)
    now = now or dt.datetime.now(dt.timezone.utc)
    source_day = dt.date.fromisoformat(day)
    today = now.astimezone(ZoneInfo('Europe/Berlin')).date()
    if source_day > today:
        raise ValueError(f'Guide date {day} is after current Cardmarket date {today}')
    if require_today and source_day < today:
        raise GuideNotReadyError(f'Guide date {day} does not match current Cardmarket date {today}')
    doc = json.loads(data)
    digest = hashlib.sha256(data).hexdigest()
    destination = directory / 'price-guide-3' / f'{day}.json.gz'
    metadata = destination.with_suffix('.meta.json')
    if destination.exists():
        with gzip.open(destination, 'rb') as f:
            existing = hashlib.sha256(f.read()).hexdigest()
        if existing != digest:
            raise ValueError(f'{day} already archived with different content; refusing to overwrite')
        if not metadata.exists():
            raise ValueError(f'{day} exists without metadata; inspect the archive')
        return day, count, False
    if metadata.exists():
        raise ValueError(f'{day} metadata exists without a snapshot; inspect the archive')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 makes gzip reproducible; the exact source bytes are preserved.
    compressed = gzip.compress(data, compresslevel=9, mtime=0)
    info = {'source': GUIDE_URL, 'createdAt': doc['createdAt'], 'day': day,
            'sha256': digest, 'products': count}
    destination.write_bytes(compressed)
    metadata.write_text(json.dumps(info, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return day, count, True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive-dir', type=pathlib.Path, required=True)
    p.add_argument('--file', type=pathlib.Path, help='Use a local official guide instead of downloading')
    p.add_argument('--require-today', action='store_true', help='Fail if Cardmarket has not published today’s guide')
    args = p.parse_args()
    if args.file:
        data = args.file.read_bytes()
    else:
        req = urllib.request.Request(GUIDE_URL, headers={'User-Agent': 'yugioh-cardmarket-history/1.0'})
        with urllib.request.urlopen(req, timeout=120) as response:
            data = response.read()
    try:
        day, count, saved = archive(data, args.archive_dir, require_today=args.require_today)
    except GuideNotReadyError as exc:
        print(f'Not ready: {exc}', file=sys.stderr)
        sys.exit(75)
    print(f'{day}: {count} products, {"saved" if saved else "already archived"}')


if __name__ == '__main__':
    main()
