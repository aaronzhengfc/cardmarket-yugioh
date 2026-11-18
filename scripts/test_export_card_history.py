import datetime as dt
import gzip
import hashlib
import json
import pathlib
import sqlite3
import subprocess
import tempfile
import unittest

from export_card_history import export


class ExportTests(unittest.TestCase):
    def test_rolling_window_mapping_missing_and_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            repo = root / 'repo'
            repo.mkdir()
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            subprocess.run(['git', '-C', str(repo), 'config', 'user.name', 'Test'], check=True)
            subprocess.run(['git', '-C', str(repo), 'config', 'user.email', 'test@example.invalid'], check=True)
            db = root / 'mapping.sqlite'
            conn = sqlite3.connect(db)
            conn.execute('CREATE TABLE cardmarket_product (idProduct INTEGER, cardId INTEGER, idMetacard INTEGER, idExpansion INTEGER, name TEXT)')
            conn.executemany('INSERT INTO cardmarket_product VALUES (?, ?, ?, ?, ?)', [(1, 101, 9, 11, 'Card A'), (2, 101, 9, 12, 'Card A'), (3, 102, 10, 13, 'Card B')])
            conn.commit()
            conn.close()
            archive = repo / 'price-guide-3'
            archive.mkdir()
            for date in ('2026-01-01', '2026-04-01', '2026-04-03'):
                doc = {'createdAt': date + 'T10:00:00+02:00', 'priceGuides': [{'idProduct': 1, 'low': 2.5, 'avg': 3, 'low-foil': None}, {'idProduct': 2, 'low': 1.2, 'avg': 5, 'low-foil': 0.0}, {'idProduct': 3, 'low': 0}]}
                raw = json.dumps(doc).encode()
                (archive / (date + '.json.gz')).write_bytes(gzip.compress(raw))
                (archive / (date + '.json.meta.json')).write_text(json.dumps({'day': date, 'createdAt': doc['createdAt'], 'sha256': hashlib.sha256(raw).hexdigest(), 'products': 3}))
            subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(repo), 'commit', '-qm', 'test'], check=True)
            out = root / 'result'
            export(repo, 'HEAD', db, out)
            card = json.loads((out / 'cards/101.json').read_text())
            self.assertEqual([d['date'] for d in card['history']], ['2026-04-01', '2026-04-03'])
            self.assertEqual(card['schemaVersion'], 4)
            self.assertEqual([p['idExpansion'] for p in card['products']], [11, 12])
            self.assertEqual(card['products'][0]['history'][0]['prices']['avg'], 3)
            self.assertIsNone(card['products'][0]['history'][0]['prices']['low-foil'])
            self.assertEqual(card['products'][1]['history'][0]['prices']['low-foil'], 0.0)
            self.assertEqual(card['history'][0], {'date': '2026-04-01', 'minimum': 1.2, 'maximum': 2.5, 'average': 1.85, 'productCount': 2})
            self.assertEqual(json.loads((out / 'cards/102.json').read_text())['history'], [])
            self.assertEqual(json.loads((out / 'manifest.json').read_text())['snapshotCount'], 2)
            with self.assertRaises(ValueError):
                export(repo, 'HEAD', db, out)
            bad = archive / '2026-04-03.json.meta.json'
            meta = json.loads(bad.read_text())
            meta['sha256'] = 'invalid'
            bad.write_text(json.dumps(meta))
            subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(repo), 'commit', '-qm', 'bad hash'], check=True)
            with self.assertRaises(ValueError):
                export(repo, 'HEAD', db, root / 'bad')
            self.assertFalse((root / 'bad').exists())

if __name__ == '__main__':
    unittest.main()
