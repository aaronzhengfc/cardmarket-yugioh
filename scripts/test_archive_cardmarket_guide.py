import datetime as dt
import gzip
import json
import pathlib
import tempfile
import unittest

from archive_cardmarket_guide import archive


class ArchiveTests(unittest.TestCase):
    def test_archive_preserves_bytes_and_rejects_different_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            doc = {'createdAt': '2026-11-16T02:49:07+0100', 'priceGuides': [{'idProduct': 12, 'low': 1.5}]}
            raw = json.dumps(doc).encode()
            now = dt.datetime(2026, 11, 16, 12, tzinfo=dt.timezone.utc)
            self.assertEqual(archive(raw, directory, now=now, require_today=True), ('2026-11-16', 1, True))
            path = directory / 'price-guide-3/2026-11-16.json.gz'
            self.assertEqual(gzip.decompress(path.read_bytes()), raw)
            self.assertFalse(archive(raw, directory, now=now)[2])
            doc['priceGuides'][0]['low'] = 2
            with self.assertRaises(ValueError):
                archive(json.dumps(doc).encode(), directory, now=now)
            self.assertEqual(gzip.decompress(path.read_bytes()), raw)

    def test_stale_and_invalid_snapshots_not_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            now = dt.datetime(2026, 11, 17, 12, tzinfo=dt.timezone.utc)
            raw = json.dumps({'createdAt': '2026-11-16T02:49:07+0100', 'priceGuides': [{'idProduct': 12, 'low': 1}]}).encode()
            with self.assertRaises(ValueError):
                archive(raw, directory, now=now, require_today=True)
            with self.assertRaises(ValueError):
                archive(b'{"createdAt":"2026-11-17T02:00:00+0100","priceGuides":[]}', directory, now=now)
            self.assertFalse(list(directory.iterdir()))


if __name__ == '__main__':
    unittest.main()
