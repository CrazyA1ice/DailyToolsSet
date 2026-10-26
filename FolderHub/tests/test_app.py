"""Run: python -m unittest discover -s tests -v"""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=app.Store(Path(self.tmp.name)/"folderhub.db")

    def test_crud_nested_and_favorites(self):
        root=self.store.create({"title":"论文", "node_type":"root"})
        child=self.store.create({"title":"预测", "parent_id":root,"node_type":"group","favorite":True})
        grand=self.store.create({"title":"数据", "parent_id":child})
        self.assertEqual(len(self.store.all()),3)
        self.assertEqual(next(x for x in self.store.all() if x["id"]==child)["parent_id"],root)
        self.store.update(child,{"title":"改名"})
        leaf=self.store.create({"title":"文件夹", "node_type":"leaf", "parent_id":grand,"folder_path":r"D:\Data"})
        self.assertEqual(next(x for x in self.store.all() if x["id"]==leaf)["folder_path"],r"D:\Data")
        self.assertEqual(next(x for x in self.store.all() if x["id"]==child)["title"],"改名")
        self.assertTrue(next(x for x in self.store.all() if x["id"]==child)["favorite"])
        with self.assertRaises(app.UserError):self.store.update(root,{"parent_id":grand})
        with self.assertRaises(app.UserError):self.store.update(root,{"parent_id":root})
        self.store.delete(child)
        self.assertEqual([n["id"] for n in self.store.all()],[root])

    def test_move_and_sort(self):
        a=self.store.create({"title":"A"})
        b=self.store.create({"title":"B"})
        c=self.store.create({"title":"C", "parent_id":a})
        self.store.update(c,{"parent_id":b})
        self.assertEqual(next(n for n in self.store.all() if n["id"]==c)["parent_id"],b)
        self.store.order(None,[b,a])
        root=[n["title"] for n in self.store.all() if n["parent_id"] is None]
        self.assertEqual(root,["B","A"])
        with self.assertRaises(app.UserError):self.store.order(None,[a])

    def test_backup_round_trip_and_rollback(self):
        p=self.store.create({"title":"资料","node_type":"root"})
        self.store.create({"title":"课程", "parent_id":p,"node_type":"leaf","folder_path":r"C:\文档"})
        backup=self.store.export()
        self.store.delete(p)
        self.store.import_backup(backup)
        self.assertEqual(len(self.store.all()),2)
        corrupt=json.loads(json.dumps(backup))
        corrupt["nodes"][0]["parent_id"]=corrupt["nodes"][1]["id"]
        with self.assertRaises(app.UserError):self.store.import_backup(corrupt)
        self.assertEqual(self.store.export()["nodes"],backup["nodes"])

    def test_reject_bad_inputs(self):
        for payload in ({"title":""},{"title":"a","folder_path":"./relative"},{"title":"a","parent_id":999},{"title":7}):
            with self.subTest(payload=payload),self.assertRaises(app.UserError):
                self.store.create(payload)


    def test_node_types_and_structure_guards(self):
        root=self.store.create({"title":"科研","node_type":"root"})
        group=self.store.create({"title":"项目","parent_id":root,"node_type":"group"})
        leaf=self.store.create({"title":"代码","parent_id":group,"node_type":"leaf","folder_path":r"D:\Code"})
        self.assertEqual([n["node_type"] for n in self.store.all()],["root","group","leaf"])
        for payload in (
            {"title":"wrong","node_type":"root","parent_id":root},
            {"title":"wrong","node_type":"group"},
            {"title":"wrong","node_type":"leaf","parent_id":root},
            {"title":"wrong","node_type":"leaf","parent_id":leaf,"folder_path":r"D:\Foo"},
            {"title":"wrong","node_type":"group","parent_id":root,"folder_path":r"D:\Foo"},
            {"title":"wrong","node_type":"other","parent_id":root},
        ):
            with self.subTest(payload=payload), self.assertRaises(app.UserError):self.store.create(payload)
        with self.assertRaises(app.UserError):self.store.update(group,{"node_type":"leaf","folder_path":r"D:\Somewhere"})
        with self.assertRaises(app.UserError):self.store.update(leaf,{"parent_id":None})
        with self.assertRaises(app.UserError):self.store.update(group,{"parent_id":leaf})
        with self.assertRaises(app.UserError):self.store.update(root,{"parent_id":group})
        self.store.update(leaf,{"title":"代码更新"})
        self.assertEqual(next(n for n in self.store.all() if n["id"]==leaf)["title"],"代码更新")

    def test_legacy_migration_keeps_paths_and_old_backups(self):
        db_path=Path(self.tmp.name)/"old.db"
        import sqlite3
        with sqlite3.connect(db_path) as conn:
            conn.executescript(r"""CREATE TABLE nodes (id INTEGER PRIMARY KEY,
                parent_id INTEGER, title TEXT NOT NULL, folder_path TEXT, favorite INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
                INSERT INTO nodes VALUES (1,NULL,'旧根','D:\Root',0,0,'a','a');
                INSERT INTO nodes VALUES (2,1,'中间分类','D:\Group',0,0,'a','a');
                INSERT INTO nodes VALUES (3,2,'叶子','D:\Data',0,0,'a','a');""")
        migrated=app.Store(db_path)
        rows=migrated.all()
        self.assertEqual([n["node_type"] for n in rows],["root","group","leaf"])
        self.assertEqual([n["folder_path"] for n in rows],[r"D:\Root",r"D:\Group",r"D:\Data"])
        migrated.update(1,{"title":"仍可改名"})
        with self.assertRaises(app.UserError):migrated.update(1,{"folder_path":r"D:\New"})
        backup=migrated.export()
        self.assertEqual(backup["version"],2)
        migrated.import_backup(backup)
        self.assertEqual([(n["id"],n["parent_id"],n["folder_path"],n["node_type"]) for n in migrated.all()],[(n["id"],n["parent_id"],n["folder_path"],n["node_type"]) for n in backup["nodes"]])
        legacy={"format":"FolderHub","version":1,"nodes":[{k:v for k,v in n.items() if k!="node_type"} for n in backup["nodes"]]}
        migrated.import_backup(legacy)
        self.assertEqual([n["node_type"] for n in migrated.all()],["root","group","leaf"])

    def test_corrupt_v2_backup_is_atomic(self):
        root=self.store.create({"title":"根","node_type":"root"})
        leaf=self.store.create({"title":"文件","node_type":"leaf","parent_id":root,"folder_path":r"D:\Files"})
        backup=self.store.export()
        bad=json.loads(json.dumps(backup))
        bad["nodes"][0]["node_type"]="leaf"
        with self.assertRaises(app.UserError):self.store.import_backup(bad)
        self.assertEqual(self.store.export()["nodes"],backup["nodes"])
        bad=json.loads(json.dumps(backup))
        bad["nodes"][1]["parent_id"]=leaf
        with self.assertRaises(app.UserError):self.store.import_backup(bad)
        self.assertEqual(self.store.export()["nodes"],backup["nodes"])


class HttpTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.srv=app.FolderServer(("127.0.0.1",0),app.Store(Path(tmp.name)/"data.db"))
        self.thread=threading.Thread(target=self.srv.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.host=f"127.0.0.1:{self.srv.server_port}"

    def request(self,method,path,payload=None,token=True,origin=None,host=None):
        conn=http.client.HTTPConnection("127.0.0.1",self.srv.server_port,timeout=3)
        headers={"Host":host or self.host}
        if payload is not None:
            headers["Content-Type"]="application/json"
        if method!="GET" and token:
            headers["X-FolderHub-Token"]=self.srv.token
        if origin:headers["Origin"]=origin
        conn.request(method,path,body=json.dumps(payload) if payload is not None else None,headers=headers)
        r=conn.getresponse();content=r.read();conn.close()
        try: content=json.loads(content)
        except ValueError:pass
        return r.status,content

    def test_static_and_crud(self):
        status,page=self.request("GET","/")
        self.assertEqual(status,200)
        self.assertIn(b"FolderHub",page)
        status,r=self.request("POST","/api/nodes",{"title":"科研","node_type":"root"})
        self.assertEqual(status,201)
        nid=r["id"]
        status,r=self.request("GET","/api/nodes")
        self.assertEqual((status,len(r["nodes"])),(200,1))
        status,r=self.request("PATCH",f"/api/nodes/{nid}",{"title":"科研资料"})
        self.assertEqual(status,200)
        self.assertEqual(self.request("GET","/api/nodes")[1]["nodes"][0]["title"],"科研资料")
        self.assertEqual(self.request("DELETE",f"/api/nodes/{nid}")[0],200)
        self.assertFalse(self.request("GET","/api/nodes")[1]["nodes"])

    def test_security(self):
        body={"title":"secret"}
        self.assertEqual(self.request("POST","/api/nodes",body,token=False)[0],403)
        self.assertEqual(self.request("POST","/api/nodes",body,origin="https://example.com")[0],403)
        self.assertEqual(self.request("GET","/api/config",host="evil.com")[0],403)
        self.assertEqual(self.request("GET","/../../app.py")[0],404)

    def test_open_folder_and_missing_folder(self):
        directory=Path(self.srv.store.db_path.parent)
        root=self.srv.store.create({"title":"Root","node_type":"root"})
        nid=self.srv.store.create({"title":"Local","parent_id":root,"node_type":"leaf","folder_path":str(directory)})
        with patch.object(app,"open_in_explorer",return_value=None) as opener:
            status,r=self.request("POST",f"/api/nodes/{nid}/open",{})
            self.assertEqual(status,200)
            opener.assert_called_once_with(str(directory))
        nid2=self.srv.store.create({"title":"No folder"})
        self.assertEqual(self.request("POST",f"/api/nodes/{nid2}/open",{})[0],400)
        self.assertEqual(self.request("POST","/api/nodes",{"title":"bad","node_type":"leaf","parent_id":nid,"folder_path":str(directory)})[0],400)



# Tests added in v1.1. Keep outside the original __main__ block so discovery can see them.
import startup


class FakeWinReg:
    HKEY_CURRENT_USER = 1
    KEY_READ = 2
    KEY_SET_VALUE = 4
    REG_SZ = 1

    def __init__(self):
        self.values = {}
    def __enter__(self):return self
    def __exit__(self, *_):pass
    def CreateKeyEx(self, *args):return self
    def OpenKey(self, *args):return self
    def QueryValueEx(self, key, name):
        if name not in self.values:raise FileNotFoundError(name)
        return self.values[name], self.REG_SZ
    def SetValueEx(self, key, name, reserved, typ, value):self.values[name]=value
    def DeleteValue(self, key, name):
        if name not in self.values:raise FileNotFoundError(name)
        del self.values[name]


class StartupTests(unittest.TestCase):
    def test_command_quoting(self):
        cmd = startup.command_for(Path(r"C:\Program Files\Python\pythonw.exe"), Path(r"D:\Work Space\FolderHub\app.py"))
        self.assertIn('"C:\\Program Files\\Python\\pythonw.exe"',cmd)
        self.assertIn('"D:\\Work Space\\FolderHub\\app.py"',cmd)
        self.assertTrue(cmd.endswith('--no-browser'))

    def test_toggle_is_explicit_and_reversible(self):
        fake=FakeWinReg()
        with patch.object(startup,'supported',return_value=True), patch.object(startup,'_winreg',return_value=fake), patch.object(startup,'launch_command',return_value='"C:\\pythonw.exe" "D:\\FolderHub\\app.py" --no-browser'):
            self.assertFalse(startup.status()['enabled'])
            self.assertTrue(startup.set_enabled(True)['enabled'])
            self.assertIn(startup.VALUE_NAME,fake.values)
            self.assertTrue(startup.set_enabled(False)['supported'])
            self.assertFalse(startup.status()['enabled'])
            self.assertNotIn(startup.VALUE_NAME,fake.values)
            with self.assertRaises(startup.StartupError):startup.set_enabled(1)

    def test_nonwindows_is_safe(self):
        with patch.object(startup,'supported',return_value=False):
            self.assertEqual(startup.status(),{'supported':False,'enabled':False})
            with self.assertRaises(startup.StartupError):startup.set_enabled(True)

    def test_startup_api_security_and_state(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        srv=app.FolderServer(('127.0.0.1',0),app.Store(Path(tmp.name)/'x.db'))
        thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
        self.addCleanup(srv.server_close);self.addCleanup(srv.shutdown)
        conn=http.client.HTTPConnection('127.0.0.1',srv.server_port,timeout=3)
        conn.request('POST','/api/startup',body='{"enabled":true}',headers={'Host':f'127.0.0.1:{srv.server_port}','Content-Type':'application/json'})
        r=conn.getresponse();r.read();self.assertEqual(r.status,403);conn.close()
        with patch.object(app.startup,'status',return_value={'supported':True,'enabled':False}), patch.object(app.startup,'set_enabled',return_value={'supported':True,'enabled':True}) as setter:
            conn=http.client.HTTPConnection('127.0.0.1',srv.server_port,timeout=3)
            conn.request('GET','/api/startup',headers={'Host':f'127.0.0.1:{srv.server_port}'})
            r=conn.getresponse();self.assertEqual(r.status,200);self.assertFalse(json.loads(r.read())['enabled']);conn.close()
            conn=http.client.HTTPConnection('127.0.0.1',srv.server_port,timeout=3)
            conn.request('POST','/api/startup',body='{"enabled":true}',headers={'Host':f'127.0.0.1:{srv.server_port}','X-FolderHub-Token':srv.token,'Content-Type':'application/json'})
            r=conn.getresponse();self.assertEqual(r.status,200);self.assertTrue(json.loads(r.read())['enabled']);conn.close()
            setter.assert_called_once_with(True)



# Explorer foreground-window integration tests (Win32 UI APIs are mocked here).
import explorer_window


class ExplorerForegroundTests(unittest.TestCase):
    def test_matches_new_or_existing_explorer_window(self):
        before = {100: '科研'}
        after = {100: '科研', 200: 'Projects', 300: '浏览器'}
        self.assertEqual(explorer_window._best_match(before, after, r'D:\\Projects'), 200)
        self.assertEqual(explorer_window._best_match(before, {100: '科研'}, r'D:\\科研'), 100)
        self.assertIsNone(explorer_window._best_match(before, after, r'D:\\Unrelated'))

    def test_opens_folder_even_when_activation_unavailable(self):
        calls = []
        activated = []
        result = explorer_window.open_and_focus(r'D:\\Projects',
            opener=lambda p: calls.append(p),
            list_windows=lambda: {10:'Projects'},
            focus=lambda hwnd: activated.append(hwnd),
            sleep=lambda t: None)
        self.assertTrue(result)
        self.assertEqual(calls,[r'D:\\Projects'])
        self.assertEqual(activated,[10])
        no_focus = explorer_window.open_and_focus(r'D:\\Projects',
            opener=lambda p: calls.append(p),
            list_windows=lambda: {},
            sleep=lambda t: None)
        self.assertFalse(no_focus)
        self.assertEqual(len(calls),2)

    def test_foreground_error_does_not_cancel_open(self):
        attempted = []
        result = explorer_window.open_and_focus(r'D:\\Projects',
            opener=lambda p: attempted.append(p),
            list_windows=lambda: {11:'Projects'},
            focus=lambda hwnd: (_ for _ in ()).throw(OSError('focus locked')),
            sleep=lambda t: None)
        self.assertFalse(result)
        self.assertEqual(attempted,[r'D:\\Projects'])

if __name__ == "__main__":
    unittest.main()
