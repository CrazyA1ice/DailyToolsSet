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
        root=self.store.create({"title":"论文", "folder_path":r"D:\Research"})
        child=self.store.create({"title":"预测", "parent_id":root,"favorite":True})
        grand=self.store.create({"title":"数据", "parent_id":child})
        self.assertEqual(len(self.store.all()),3)
        self.assertEqual(next(x for x in self.store.all() if x["id"]==child)["parent_id"],root)
        self.store.update(child,{"title":"改名", "folder_path":r"D:\Data"})
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
        p=self.store.create({"title":"资料","folder_path":r"C:\文档"})
        self.store.create({"title":"课程", "parent_id":p})
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
        status,r=self.request("POST","/api/nodes",{"title":"科研","folder_path":r"D:\Research"})
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
        nid=self.srv.store.create({"title":"Local","folder_path":str(directory)})
        with patch.object(app,"open_in_explorer",return_value=None) as opener:
            status,r=self.request("POST",f"/api/nodes/{nid}/open",{})
            self.assertEqual(status,200)
            opener.assert_called_once_with(str(directory))
        nid2=self.srv.store.create({"title":"No folder"})
        self.assertEqual(self.request("POST",f"/api/nodes/{nid2}/open",{})[0],400)



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

if __name__ == "__main__":
    unittest.main()
