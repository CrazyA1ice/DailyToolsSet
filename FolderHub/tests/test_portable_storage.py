"""Portable SQLite + cover files regression tests (Windows source migrations are mocked)."""
import base64
import hashlib
from pathlib import Path
from unittest.mock import patch
import shutil
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app

PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLdlwAAAABJRU5ErkJggg==')
DATA_URL = 'data:image/png;base64,' + base64.b64encode(PNG).decode()


class PortableTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        self.project = self.tmp / 'FolderHub'
        self.store = app.Store(self.project / 'data' / 'folderhub.db', self.project / 'uploads')

    def test_uses_relative_paths_and_real_cover_files(self):
        node = self.store.create({'title':'首页', 'node_type':'root'})
        self.store.save_image(node, DATA_URL)
        with self.store.connect() as db:
            row = db.execute('SELECT * FROM node_images WHERE node_id=?',(node,)).fetchone()
            self.assertEqual(list(row.keys()), ['node_id','mime_type','image_path','updated_at'])
            relative = row['image_path']
            self.assertTrue(relative.startswith('uploads/'))
            self.assertNotIn('image_data', {r['name'] for r in db.execute('PRAGMA table_info(node_images)')})
        self.assertEqual((self.project / relative).read_bytes(), PNG)
        self.assertEqual(self.store.get_image(node), ('image/png', PNG))
        self.assertEqual(self.store.export()['images'][str(node)]['base64'],base64.b64encode(PNG).decode())

    def test_delete_restores_shared_cover_and_prune_only_when_unused(self):
        a = self.store.create({'title':'第一组','node_type':'root'})
        b = self.store.create({'title':'第二组','node_type':'root'})
        self.store.save_image(a, DATA_URL)
        self.store.save_image(b, DATA_URL)
        cover = next(self.store.uploads_dir.glob('*.png'))
        self.assertEqual(len(list(self.store.uploads_dir.glob('*.png'))),1)
        deleted = self.store.delete(a)
        with self.store.connect() as db:
            record = db.execute('SELECT * FROM trash_nodes WHERE batch_id=?',(deleted['trash_id'],)).fetchone()
            self.assertEqual(record['image_path'],'uploads/'+cover.name)
            self.assertNotIn('image_data',{r['name'] for r in db.execute('PRAGMA table_info(trash_nodes)')})
        self.store.remove_image(b)
        self.assertTrue(cover.exists(), 'Recycle bin must keep its image')
        self.store.restore_trash(deleted['trash_id'])
        self.assertEqual(self.store.get_image(a),('image/png',PNG))
        self.store.remove_image(a)
        self.assertFalse(cover.exists(), 'Unreferenced file should be removed')

    def test_portable_copy_and_backup(self):
        root = self.store.create({'title':'科研','node_type':'root'})
        self.store.save_image(root,DATA_URL)
        backup = self.store.export()
        moved = self.tmp / 'Moved' / 'FolderHub'
        shutil.copytree(self.project,moved)
        portable = app.Store(moved / 'data' / 'folderhub.db', moved / 'uploads')
        self.assertEqual(portable.get_image(root),('image/png',PNG))
        portable.remove_image(root)
        portable.import_backup(backup)
        self.assertEqual(portable.get_image(root),('image/png',PNG))
        with portable.connect() as db:
            rel = db.execute('SELECT image_path FROM node_images WHERE node_id=?',(root,)).fetchone()[0]
        self.assertTrue((moved/rel).is_file())

    def test_refuses_tampered_relative_paths(self):
        for value in ('../private.txt','uploads/../private.txt','/tmp/secret','uploads/not-a-hash.png'):
            with self.subTest(value=value),self.assertRaises(app.UserError):
                self.store._read_image(value)

    def test_migrate_appdata_database_and_both_blob_tables(self):
        legacy = self.tmp / 'LegacyAppData'
        legacy.mkdir()
        old = legacy / 'folderhub.db'
        with sqlite3.connect(old) as db:
            db.executescript('''
                CREATE TABLE nodes (id INTEGER PRIMARY KEY,parent_id INTEGER,title TEXT NOT NULL,
                    folder_path TEXT,node_type TEXT NOT NULL,icon TEXT NOT NULL,favorite INTEGER,
                    sort_order INTEGER,created_at TEXT,updated_at TEXT);
                CREATE TABLE node_images (node_id INTEGER PRIMARY KEY,mime_type TEXT NOT NULL,
                    image_data BLOB NOT NULL,updated_at TEXT NOT NULL);
                CREATE TABLE trash_batches (id INTEGER PRIMARY KEY,deleted_at TEXT,title TEXT,
                    selected_count INTEGER,item_count INTEGER);
                CREATE TABLE trash_nodes (batch_id INTEGER,node_id INTEGER,parent_id INTEGER,
                    title TEXT NOT NULL,folder_path TEXT,node_type TEXT NOT NULL,icon TEXT,
                    favorite INTEGER,sort_order INTEGER,created_at TEXT,updated_at TEXT,
                    image_mime TEXT,image_data BLOB,PRIMARY KEY(batch_id,node_id));
                INSERT INTO nodes VALUES(1,NULL,'工作','D:\\Work','root','folder',0,0,'a','a');
                INSERT INTO trash_batches VALUES(1,'a','已删除',1,1);
                INSERT INTO trash_nodes(batch_id,node_id,parent_id,title,node_type,icon,
                    favorite,sort_order,created_at,updated_at,image_mime)
                    VALUES(1,2,NULL,'已删','root','book',0,0,'a','a','image/png');
            ''')
            db.execute('INSERT INTO node_images VALUES(1,?,?,?)',('image/png', PNG,'a'))
            db.execute('UPDATE trash_nodes SET image_data=? WHERE node_id=2',(PNG,))
        original_sha=hashlib.sha256(old.read_bytes()).hexdigest()
        dest = self.tmp/'NewFolderHub'/'data'
        self.assertTrue(app.migrate_legacy_database(dest,legacy))
        self.assertFalse(app.migrate_legacy_database(dest,legacy))
        self.assertEqual(hashlib.sha256(old.read_bytes()).hexdigest(),original_sha)
        new = app.Store(dest/'folderhub.db',dest.parent/'uploads')
        self.assertEqual(new.get_image(1),('image/png',PNG))
        self.assertEqual(new.trash_list()[0]['title'],'已删除')
        with new.connect() as db:
            for table in ('node_images','trash_nodes'):
                fields={r['name'] for r in db.execute(f'PRAGMA table_info({table})')}
                self.assertIn('image_path',fields)
                self.assertNotIn('image_data',fields)
        restored = new.restore_trash(1)
        self.assertEqual(restored['restored'],1)
        self.assertEqual(new.get_image(2),('image/png',PNG))
        self.assertEqual(len(list(new.uploads_dir.glob('*.png'))),1)
        self.assertEqual([x['title'] for x in new.all()], ['工作','已删'])

    def test_migration_closes_sqlite_connections_before_rename(self):
        """Regression: sqlite3 context managers do not close handles on Windows."""
        legacy=self.tmp/'legacy-locked';legacy.mkdir()
        old=legacy/'folderhub.db'
        with sqlite3.connect(old) as conn:
            conn.execute('CREATE TABLE keep (value TEXT)')
            conn.execute('INSERT INTO keep VALUES (?)',('must survive',))
        copied=self.tmp/'copied'/'data'
        real_connect=sqlite3.connect
        real_replace=app.os.replace
        observed=[]
        def watch_connect(*args,**kwargs):
            connection=real_connect(*args,**kwargs)
            observed.append(connection)
            return connection
        def verify_closed_then_replace(source,dest):
            self.assertEqual(len(observed),2)
            for connection in observed:
                with self.assertRaises(sqlite3.ProgrammingError):
                    connection.execute('SELECT 1')
            return real_replace(source,dest)
        with (patch.object(app.sqlite3,'connect',side_effect=watch_connect),
              patch.object(app.os,'replace',side_effect=verify_closed_then_replace)):
            self.assertTrue(app.migrate_legacy_database(copied,legacy))
        self.assertEqual(len(observed),2)
        self.assertEqual(list(copied.glob('.migrate-*.db')),[])
        with sqlite3.connect(copied/'folderhub.db') as conn:
            self.assertEqual(conn.execute('SELECT value FROM keep').fetchone()[0],
                             'must survive')
        with sqlite3.connect(old) as conn:
            self.assertEqual(conn.execute('SELECT value FROM keep').fetchone()[0],
                             'must survive')

    def test_migration_cleanup_failure_does_not_mask_replace_error(self):
        legacy=self.tmp/'legacy-cleanup';legacy.mkdir()
        with sqlite3.connect(legacy/'folderhub.db') as conn:
            conn.execute('CREATE TABLE keep (value INTEGER)')
        copied=self.tmp/'copied-failure'/'data'
        original_unlink=Path.unlink
        def locked_delete(path,*args,**kwargs):
            if path.name.startswith('.migrate-'):
                raise PermissionError(32,'模拟 Windows 文件锁定',str(path))
            return original_unlink(path,*args,**kwargs)
        with (patch.object(app.os,'replace',
                           side_effect=PermissionError(32,'原始替换失败')),
              patch.object(Path,'unlink',autospec=True,side_effect=locked_delete)):
            with self.assertRaisesRegex(PermissionError,'原始替换失败'):
                app.migrate_legacy_database(copied,legacy)
        self.assertFalse((copied/'folderhub.db').exists())

    def test_existing_portable_db_never_overwritten_by_legacy(self):
        legacy=self.tmp/'old';legacy.mkdir()
        with sqlite3.connect(legacy/'folderhub.db') as conn:
            conn.execute('CREATE TABLE t(x)')
        node=self.store.create({'title':'保留','node_type':'root'})
        self.assertFalse(app.migrate_legacy_database(self.project/'data', legacy))
        self.assertEqual(self.store.all()[0]['id'],node)


if __name__=='__main__':
    unittest.main()
