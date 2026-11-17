import json
import pathlib
import sqlite3
import tempfile
import unittest

from cardmarket_history import ingest


class HistoryTests(unittest.TestCase):
    def test_import_is_idempotent_and_rejects_changed_same_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / 'history.sqlite'
            payload = {'createdAt': '2026-11-09T02:50:37+0100', 'priceGuides': [
                {'idProduct': 123, 'idCategory': 1, 'low': 0.25, 'avg-foil': 1.5},
                {'idProduct': 456, 'low': None}]}
            data = json.dumps(payload).encode()
            self.assertEqual(ingest(db, data, 'fixture'), ('2026-11-09', 2, True))
            self.assertFalse(ingest(db, data, 'fixture')[2])
            payload['priceGuides'][0]['low'] = 0.5
            with self.assertRaises(ValueError):
                ingest(db, json.dumps(payload).encode(), 'fixture')
            with sqlite3.connect(db) as conn:
                self.assertEqual(conn.execute('SELECT low, avg_foil FROM prices WHERE product_id=123').fetchone(), (0.25, 1.5))
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0], 1)

    def test_invalid_or_duplicate_prices_are_not_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / 'history.sqlite'
            payload = {'createdAt': '2026-11-09T02:50:37+0100', 'priceGuides': [{'idProduct': 1, 'low': 1}, {'idProduct': 1, 'low': 2}]}
            with self.assertRaises(ValueError):
                ingest(db, json.dumps(payload).encode(), 'fixture')
            self.assertFalse(db.exists())


if __name__ == '__main__':
    unittest.main()
