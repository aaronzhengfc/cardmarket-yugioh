#!/usr/bin/env python3
"""Export per-card, 90-calendar-day Cardmarket summaries and product-level prices from a Git archive."""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import math
import pathlib
import re
import sqlite3
import subprocess
import sys
import tempfile


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def export(repo, ref, mapping_db, output):
    if output.exists():
        raise ValueError(f'Output already exists: {output}; choose a new directory')
    files = git(repo, 'ls-tree', '-r', '--name-only', ref, '--', 'price-guide-3/').decode().splitlines()
    dates = sorted((dt.date.fromisoformat(m.group(1)), name) for name in files
                   if (m := re.fullmatch(r'price-guide-3/(\d{4}-\d{2}-\d{2})\.json\.gz', name)))
    if not dates:
        raise ValueError(f'No archived snapshots found in {ref}')
    latest = dates[-1][0]
    dates = [(day, name) for day, name in dates if day >= latest - dt.timedelta(days=89)]
    conn = sqlite3.connect(f'file:{mapping_db.resolve().as_posix()}?mode=ro', uri=True)
    try:
        columns = {row[1] for row in conn.execute('PRAGMA table_info(cardmarket_product)')}
        required = {'idProduct', 'cardId', 'idMetacard', 'idExpansion', 'name'}
        if not required.issubset(columns):
            raise ValueError('Mapping database lacks product metadata; use cards-maintenance.cdb')
        mapping = {}
        catalog = {}
        for product, card, metacard, expansion, name in conn.execute('SELECT idProduct, cardId, idMetacard, idExpansion, name FROM cardmarket_product'):
            mapping[int(product)] = str(card)
            catalog[int(product)] = {'idProduct': int(product), 'idMetacard': metacard, 'idExpansion': expansion, 'name': name}
    finally:
        conn.close()
    if not mapping:
        raise ValueError('Product-to-card mapping is empty')
    cards = set(mapping.values())
    with tempfile.TemporaryDirectory(prefix="cardmarket-daily-") as stage_name:
        stage_path = pathlib.Path(stage_name)
        snapshots = []
        for day, name in dates:
            raw = gzip.decompress(git(repo, 'show', f'{ref}:{name}'))
            meta_name = name[:-3] + '.meta.json'
            meta = json.loads(git(repo, 'show', f'{ref}:{meta_name}'))
            doc = json.loads(raw)
            if meta['day'] != day.isoformat() or meta['sha256'] != hashlib.sha256(raw).hexdigest() or doc['createdAt'] != meta['createdAt']:
                raise ValueError(f'Archive metadata mismatch: {name}')
            if dt.datetime.strptime(doc['createdAt'], '%Y-%m-%dT%H:%M:%S%z').date() != day:
                raise ValueError(f'Snapshot date mismatch: {name}')
            rows = doc['priceGuides']
            if len(rows) != meta['products']:
                raise ValueError(f'Product count mismatch: {name}')
            by_card = {}
            product_rows = {}
            seen = set()
            for row in rows:
                product = row['idProduct']
                if product in seen:
                    raise ValueError(f'Duplicate product {product}: {name}')
                seen.add(product)
                card = mapping.get(product)
                if card is not None:
                    # Preserve the original price-guide fields, including nulls and zero.
                    product_rows.setdefault(card, []).append(row)
                low = row.get('low')
                if card is not None and isinstance(low, (int, float)) and not isinstance(low, bool) and math.isfinite(low) and low > 0:
                    by_card.setdefault(card, []).append(low)
            for card, products in product_rows.items():
                prices = by_card.get(card, [])
                summary = {'date': day.isoformat(), 'minimum': min(prices), 'maximum': max(prices), 'average': round(math.fsum(prices) / len(prices), 6), 'productCount': len(prices)} if prices else None
                with (stage_path / (card + '.jsonl')).open('a', encoding='utf-8') as f:
                    f.write(json.dumps({'date': day.isoformat(), 'summary': summary, 'products': products}, ensure_ascii=False, separators=(',', ':')) + '\n')
            snapshots.append({'date': day.isoformat(), 'createdAt': doc['createdAt'], 'sha256': meta['sha256'], 'products': len(rows), 'cardsWithPrice': len(by_card)})
            print(f'{day}: {len(by_card)} cards with valid prices', flush=True)
        output.parent.mkdir(parents=True, exist_ok=True)
        # Build the whole publication before exposing it. Never overwrite prior exports.
        with tempfile.TemporaryDirectory(prefix='.cardmarket-export-', dir=output.parent) as tmp:
            root = pathlib.Path(tmp)
            (root / 'cards').mkdir()
            for card in cards:
                points = []
                details = {}
                source = stage_path / (card + '.jsonl')
                if source.exists():
                    with source.open(encoding='utf-8') as f:
                        for line in f:
                            day = json.loads(line)
                            if day['summary'] is not None:
                                points.append(day['summary'])
                            for row in day['products']:
                                product = row['idProduct']
                                if product not in details:
                                    details[product] = dict(catalog[product], history=[])
                                details[product]['history'].append({'date': day['date'], 'prices': {k: v for k, v in row.items() if k != 'idProduct'}})
                if not re.fullmatch(r'\d+', card):
                    raise ValueError(f'Invalid card ID: {card}')
                payload = {'schemaVersion': 4, 'cardId': card, 'currency': 'EUR', 'metric': 'product_low_summary', 'updatedAt': snapshots[-1]['createdAt'], 'history': points, 'products': [details[pid] for pid in sorted(details)] }
                (root / 'cards' / f'{card}.json').write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
            manifest = {'schemaVersion': 4, 'windowDays': 90, 'windowStart': (latest - dt.timedelta(days=89)).isoformat(), 'windowEnd': latest.isoformat(), 'snapshotCount': len(snapshots), 'cardCount': len(cards), 'mappingSha256': hashlib.sha256(mapping_db.read_bytes()).hexdigest(), 'snapshots': snapshots}
            (root / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            root.rename(output)
        print(f'Exported {len(cards)} cards to {output}')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=pathlib.Path, default=pathlib.Path.cwd())
    p.add_argument('--archive-ref', default='origin/cardmarket-price-archive')
    p.add_argument('--mapping-db', type=pathlib.Path, required=True)
    p.add_argument('--output', type=pathlib.Path, required=True)
    args = p.parse_args()
    try:
        export(args.repo, args.archive_ref, args.mapping_db, args.output)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, sqlite3.Error, subprocess.CalledProcessError) as e:
        print(f'Export failed: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
