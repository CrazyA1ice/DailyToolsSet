"""V2.1 complete portable backup and read-only health checks."""
import base64
import http.client
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLdlwAAAABJRU5ErkJggg==')
DATA = 'data:image/png;base64,' + base64.b64encode(PNG).decode('ascii')

class PortableBackupTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.store = app.Store(self.root / 'data' / 'folderhub.db', self.root / 'uploads')

    def test_status_and_backup_include_recycle_bin_and_no_orphans(self):
        active = self.store.create({'title': '论文', 'node_type': 'root'})
        deleted = self.store.create({'title': '旧项目', 'node_type': 'root'})
        self.store.save_image(active, DATA)
        self.store.save_image(deleted, DATA)
        self.store.delete(deleted)
        (self.store.uploads_dir / ('a' * 64 + '.png')).write_bytes(b'orphan')
        status = self.store.storage_status()
        self.assertEqual(status['active_modules'], 1)
        self.assertEqual(status['trash_batches'], 1)
        self.assertEqual(status['cover_files'], 1)
        self.assertEqual(status['missing_covers'], 0)
        self.assertEqual(status['unused_covers'], 1)
        self.assertTrue(status['backup_ready'])
        zip_path = self.store.make_portable_backup()
        try:
            with zipfile.ZipFile(zip_path) as z:
                names = z.namelist()
                self.assertIn('data/folderhub.db', names)
                self.assertIn('README-RESTORE.txt', names)
                self.assertEqual(len([x for x in names if x.startswith('uploads/')]), 1)
                self.assertNotIn('uploads/' + 'a' * 64 + '.png', names)
                self.assertEqual(z.read(next(x for x in names if x.startswith('uploads/'))), PNG)
                restored_db = self.root / 'restored.db'
                restored_db.write_bytes(z.read('data/folderhub.db'))
            with sqlite3.connect(restored_db) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM nodes').fetchone()[0], 1)
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM trash_nodes').fetchone()[0], 1)
                self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        finally:
            zip_path.unlink(missing_ok=True)

    def test_missing_cover_blocks_backup_without_leaking_temp_files(self):
        n = self.store.create({'title': '图像', 'node_type': 'root'})
        self.store.save_image(n, DATA)
        next(self.store.uploads_dir.glob('*.png')).unlink()
        status = self.store.storage_status()
        self.assertEqual(status['missing_covers'], 1)
        self.assertFalse(status['backup_ready'])
        with self.assertRaisesRegex(app.UserError, '封面文件丢失'):
            self.store.make_portable_backup()
        self.assertEqual(list((self.root / 'data').glob('.backup-*')), [])

    def test_http_status_and_download_stream_zip(self):
        n = self.store.create({'title': '本机', 'node_type': 'root'})
        self.store.save_image(n, DATA)
        server = app.FolderServer(('127.0.0.1', 0), self.store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def get(path):
            conn = http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=6)
            conn.request('GET',path,headers={'Host':f'127.0.0.1:{server.server_port}'})
            response = conn.getresponse()
            result = response.status,response.getheader('Content-Type'),response.read()
            conn.close()
            return result
        code, content_type, body = get('/api/storage/status')
        self.assertEqual(code,200)
        self.assertEqual(json.loads(body)['active_modules'],1)
        self.assertEqual(get('/api/storage/backup')[0],403)
        unauthorized=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=6)
        unauthorized.request('POST','/api/storage/backup-ticket',body='{}',headers={
            'Host':f'127.0.0.1:{server.server_port}', 'Content-Type':'application/json'})
        result=unauthorized.getresponse()
        self.assertEqual(result.status,403)
        result.read();unauthorized.close()
        conn = http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=6)
        conn.request('POST','/api/storage/backup-ticket',body='{}',headers={
            'Host':f'127.0.0.1:{server.server_port}',
            'Content-Type':'application/json','X-FolderHub-Token':server.token})
        resp=conn.getresponse()
        self.assertEqual(resp.status,200)
        ticket=json.loads(resp.read())['ticket']
        conn.close()
        code, content_type, body = get('/api/storage/backup?ticket='+ticket)
        self.assertEqual((code,content_type),(200,'application/zip'))
        self.assertEqual(get('/api/storage/backup?ticket='+ticket)[0],403)
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            self.assertIn('data/folderhub.db',z.namelist())
        self.assertFalse(list((self.root/'data').glob('.backup-*')))

    def test_missing_images_are_not_cleaned_automatically(self):
        n = self.store.create({'title': '项目', 'node_type': 'root'})
        self.store.save_image(n,DATA)
        orphan = self.store.uploads_dir / ('b'*64+'.jpg')
        orphan.write_bytes(b'keep until deliberate cleanup')
        self.assertEqual(self.store.storage_status()['unused_covers'],1)
        self.assertTrue(orphan.is_file())

if __name__ == '__main__':
    unittest.main()
