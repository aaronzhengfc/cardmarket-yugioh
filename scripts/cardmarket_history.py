#!/usr/bin/env python3
"""Archive official Cardmarket Yu-Gi-Oh daily guides on this computer.

Only actual source snapshots are stored. This cannot reconstruct missing days.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import pathlib
import sqlite3
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / 'docs/local-data/cardmarket-history.sqlite'
GUIDE_URL = 'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_3.json'
FIELDS = ('avg', 'low', 'trend', 'avg1', 'avg7', 'avg30',
          'avg-foil', 'low-foil', 'trend-foil', 'avg1-foil', 'avg7-foil', 'avg30-foil')


def ingest(db_path, data, source):
    doc = json.loads(data)
    created = doc['createdAt']
    timestamp = dt.datetime.strptime(created, "%Y-%m-%dT%H:%M:%S%z")
    if timestamp.tzinfo is None:
        raise ValueError('createdAt must include the source time zone')
    day = timestamp.date().isoformat()
    prices = doc['priceGuides']
    if not isinstance(prices, list) or not prices:
        raise ValueError('priceGuides must be a nonempty list')
    rows = []
    seen = set()
    for row in prices:
        product = row['idProduct']
        if isinstance(product, bool) or not isinstance(product, int) or product <= 0 or product in seen:
            raise ValueError(f'invalid or duplicate product ID: {product!r}')
        seen.add(product)
        values = []
        for field in FIELDS:
            value = row.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
                raise ValueError(f'invalid {field} for product {product}')
            values.append(value)
        rows.append((day, product, row.get('idCategory'), *values))
    digest = hashlib.sha256(data).hexdigest()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('CREATE TABLE IF NOT EXISTS snapshots (day TEXT PRIMARY KEY, created_at TEXT NOT NULL, sha256 TEXT NOT NULL, source TEXT NOT NULL, product_count INTEGER NOT NULL)')
        db.execute('''CREATE TABLE IF NOT EXISTS prices (
            day TEXT NOT NULL REFERENCES snapshots(day), product_id INTEGER NOT NULL, category_id INTEGER,
            avg REAL, low REAL, trend REAL, avg1 REAL, avg7 REAL, avg30 REAL,
            avg_foil REAL, low_foil REAL, trend_foil REAL, avg1_foil REAL, avg7_foil REAL, avg30_foil REAL,
            PRIMARY KEY(day, product_id)) WITHOUT ROWID''')
        db.execute('CREATE INDEX IF NOT EXISTS prices_product_day ON prices(product_id, day)')
        existing = db.execute('SELECT sha256 FROM snapshots WHERE day=?', (day,)).fetchone()
        if existing:
            if existing[0] != digest:
                raise ValueError(f'{day} already exists with a different SHA-256; inspect it before replacing')
            return day, len(rows), False
        db.execute('INSERT INTO snapshots VALUES (?,?,?,?,?)', (day, created, digest, source, len(rows)))
        db.executemany('INSERT INTO prices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)
    return day, len(rows), True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=pathlib.Path, default=DEFAULT_DB)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--file', type=pathlib.Path, help='import an already downloaded official JSON file')
    action.add_argument('--download', action='store_true', help='download and import the current official guide once')
    action.add_argument('--status', action='store_true', help='list stored snapshot days')
    args = parser.parse_args()
    if args.status:
        if not args.db.exists():
            print('No archive exists yet.')
            return
        with sqlite3.connect(f'file:{args.db.resolve()}?mode=ro', uri=True) as db:
            for day, created, count in db.execute('SELECT day, created_at, product_count FROM snapshots ORDER BY day'):
                print(f'{day}\t{created}\t{count} products')
        return
    if args.file:
        data = args.file.read_bytes()
        source = str(args.file)
    else:
        request = urllib.request.Request(GUIDE_URL, headers={'User-Agent': 'yugioh-local-price-archive/1.0'})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
        source = GUIDE_URL
    day, count, inserted = ingest(args.db, data, source)
    print(f'{day}: {count} products; {"saved" if inserted else "already archived"} in {args.db}')


if __name__ == '__main__':
    main()
