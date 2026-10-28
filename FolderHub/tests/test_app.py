"""Run: python -m unittest discover -s tests -v"""
import http.client
import json
import sqlite3
from contextlib import closing
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

    def test_v51_upgrade_legacy_v4_sqlite_preserves_nodes_and_recycle(self):
        legacy=Path(self.tmp.name)/"legacy-v4.db"
        # sqlite3.Connection.__exit__ commits but does NOT close. Keep the
        # synthetic legacy file unlocked on Windows, including failed tests.
        with closing(sqlite3.connect(legacy)) as db, db:
            db.executescript("""
                CREATE TABLE nodes(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    folder_path TEXT,
                    node_type TEXT NOT NULL DEFAULT 'group',
                    icon TEXT NOT NULL DEFAULT 'folder',
                    favorite INTEGER NOT NULL DEFAULT 0,
                    tags TEXT NOT NULL DEFAULT '[]',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE trash_batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deleted_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    selected_count INTEGER NOT NULL,
                    item_count INTEGER NOT NULL
                );
                CREATE TABLE trash_nodes (
                    batch_id INTEGER NOT NULL REFERENCES trash_batches(id) ON DELETE CASCADE,
                    node_id INTEGER NOT NULL,
                    parent_id INTEGER,
                    title TEXT NOT NULL,
                    folder_path TEXT,
                    node_type TEXT NOT NULL,
                    icon TEXT NOT NULL,
                    favorite INTEGER NOT NULL,
                    tags TEXT NOT NULL DEFAULT '[]',
                    sort_order INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    image_mime TEXT,
                    image_path TEXT,
                    PRIMARY KEY(batch_id,node_id)
                );
            """)
            db.execute("""INSERT INTO nodes
                (id,parent_id,title,folder_path,node_type,created_at,updated_at)
                VALUES(1,NULL,'旧根模块',NULL,'root','old','old')""")
            db.execute("INSERT INTO trash_batches VALUES(1,'old','旧叶子模块',1,1)")
            db.execute("""INSERT INTO trash_nodes VALUES
                (1,2,1,'旧文件夹','D:\\Legacy','leaf','folder',0,'[]',0,'old','old',NULL,NULL)""")
        upgraded=app.Store(legacy)
        with upgraded.connect() as db:
            for table in ("nodes","trash_nodes"):
                columns={r["name"] for r in db.execute("PRAGMA table_info("+table+")")}
                self.assertIn("resource_kind",columns)
                self.assertIn("resource_target",columns)
        self.assertEqual(upgraded.all()[0]["resource_kind"],"folder")
        self.assertIsNone(upgraded.all()[0]["resource_target"])
        self.assertEqual(upgraded.restore_trash(1)["restored"],1)
        restored={node["id"]:node for node in upgraded.all()}
        self.assertEqual(restored[2]["folder_path"],r"D:\Legacy")
        self.assertEqual(restored[2]["resource_kind"],"folder")
        new_id=upgraded.create({"title":"新网页","node_type":"leaf","parent_id":1,
                                "resource_kind":"url",
                                "resource_target":"https://example.org/"})
        self.assertEqual(next(n for n in upgraded.all() if n["id"]==new_id)
                         ["resource_kind"],"url")

    def test_v50_mixed_resource_roundtrip_and_recycle(self):
        root=self.store.create({"title":"项目","node_type":"root"})
        file_id=self.store.create({
            "title":"实验报告","node_type":"leaf","parent_id":root,
            "resource_kind":"file","resource_target":r"D:\Research\report.pdf"})
        url_id=self.store.create({
            "title":"项目主页","node_type":"leaf","parent_id":root,
            "resource_kind":"url","resource_target":"https://example.org/docs?q=1"})
        resources={n["id"]:n for n in self.store.all()}
        self.assertEqual(resources[file_id]["resource_kind"],"file")
        self.assertEqual(resources[file_id]["resource_target"],r"D:\Research\report.pdf")
        self.assertIsNone(resources[url_id]["folder_path"])
        self.store.update(file_id,{"title":"正式报告"})
        self.assertEqual(next(n for n in self.store.all() if n["id"]==file_id)["resource_kind"],"file")
        exported=self.store.export()
        self.assertEqual(exported["version"],5)
        self.store.delete(url_id)
        self.assertEqual(self.store.restore_trash(self.store.trash_list()[0]["id"])["restored"],1)
        self.assertEqual(next(n for n in self.store.all() if n["id"]==url_id)["resource_target"],
                         "https://example.org/docs?q=1")
        self.store.import_backup(exported)
        restored={n["id"]:n for n in self.store.all()}
        self.assertEqual(restored[file_id]["resource_target"],r"D:\Research\report.pdf")
        self.assertEqual(restored[url_id]["resource_kind"],"url")

    def test_v50_rejects_executable_and_unsafe_web_links(self):
        root=self.store.create({"title":"项目","node_type":"root"})
        baseline=self.store.export()
        bad=[
            ("file",r"D:\Tools\start.exe"),("file",r"D:\Tools\run.bat"),
            ("file","relative/report.pdf"),("url","javascript:alert(1)"),
            ("url","file:///C:/private"),("url","https://u:p@example.com/"),
            ("url","https://example.com/space here"),("url","http://"),
            ("url","https://example.org\\@evil.example"),
        ]
        for kind,target in bad:
            with self.subTest(kind=kind,target=target),self.assertRaises(app.UserError):
                self.store.create({"title":"Unsafe","node_type":"leaf","parent_id":root,
                                   "resource_kind":kind,"resource_target":target})
            self.assertEqual(self.store.export()["nodes"],baseline["nodes"])
        with self.assertRaises(app.UserError):
            self.store.create({"title":"Bad Group","node_type":"group","parent_id":root,
                               "resource_kind":"url","resource_target":"https://example.org/"})

    def test_v50_web_open_only_after_explicit_call(self):
        row={"resource_kind":"url","resource_target":"https://example.org/",
             "folder_path":None}
        with patch.object(app.webbrowser,"open",return_value=True) as browser:
            app.open_saved_resource(row)
            browser.assert_called_once_with("https://example.org/")
        with patch.object(app.webbrowser,"open") as browser:
            with self.assertRaises(app.UserError):
                app.open_saved_resource({**row,"resource_target":"data:text/html,hello"})
            browser.assert_not_called()

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
        # Import must preserve the archive's timestamps even when it happens
        # much later. Previously this only failed when a second ticked over.
        with patch.object(app, "now", return_value="2099-01-01T00:00:00+00:00"):
            self.store.import_backup(backup)
        self.assertEqual(len(self.store.all()),2)
        self.assertEqual(self.store.export()["nodes"], backup["nodes"])
        corrupt=json.loads(json.dumps(backup))
        corrupt["nodes"][0]["parent_id"]=corrupt["nodes"][1]["id"]
        with self.assertRaises(app.UserError):self.store.import_backup(corrupt)
        self.assertEqual(self.store.export()["nodes"],backup["nodes"])

    def test_backup_keeps_legacy_timestamp_text_and_rejects_malformed_fields(self):
        root=self.store.create({"title":"Time capsule","node_type":"root"})
        with self.store.connect() as db:
            db.execute("UPDATE nodes SET created_at=?,updated_at=? WHERE id=?",
                       ("old-created-at", "old-updated-at", root))
        backup=self.store.export()
        with patch.object(app,"now",return_value="2099-01-01T00:00:00+00:00"):
            self.store.import_backup(backup)
        self.assertEqual(self.store.export()["nodes"],backup["nodes"])

        before=self.store.export()["nodes"]
        # Build actual control characters, not literal backslash-n/backslash-x00
        # text. Explicit chr() calls make escaping across editors unambiguous.
        newline_value="bad"+chr(10)+"newline"
        nul_value="bad"+chr(0)+"zero"
        self.assertEqual(ord(newline_value[3]),10)
        self.assertEqual(ord(nul_value[3]),0)
        for key,value in (("created_at",None),("updated_at",42),
                          ("created_at","x" * 129),
                          ("updated_at",newline_value),
                          ("created_at",nul_value),
                          ("updated_at","bad"+chr(9)+"tab"),
                          ("created_at","bad"+chr(127)+"del")):
            corrupt=json.loads(json.dumps(backup))
            corrupt["nodes"][0][key]=value
            with self.subTest(key=key,value=repr(value)):
                with self.assertRaisesRegex(app.UserError,"时间字段"):
                    self.store.import_backup(corrupt)
                self.assertEqual(self.store.export()["nodes"],before)

    def test_backup_without_time_fields_remains_compatible(self):
        self.store.create({"title":"Legacy root","node_type":"root"})
        backup=self.store.export()
        for node in backup["nodes"]:
            node.pop("created_at")
            node.pop("updated_at")
        # Older manually assembled backups may omit both time fields.
        # The fallback must use one consistent timestamp per import.
        with patch.object(app,"now",return_value="2099-01-01T00:00:00+00:00"):
            self.store.import_backup(backup)
        restored=self.store.all()
        self.assertEqual(len(restored),1)
        self.assertEqual(restored[0]["created_at"],"2099-01-01T00:00:00+00:00")
        self.assertEqual(restored[0]["updated_at"],"2099-01-01T00:00:00+00:00")

    def test_batch_favorite_and_atomic_validation(self):
        root=self.store.create({"title":"科研","node_type":"root"})
        group=self.store.create({"title":"研究","node_type":"group","parent_id":root})
        before=self.store.export()
        for action, ids in (
            ("favorite", []), ("favorite", [root,root]),
            ("favorite", [root,999999]), ("favorite", [True]),
            ("favorite", [root] * 201), ("unknown", [root]),
            ("favorite", "1"), ("delete", [group,-1])
        ):
            with self.subTest(action=action,ids=ids),self.assertRaises(app.UserError):
                self.store.batch(action,ids)
            self.assertEqual(self.store.export()["nodes"],before["nodes"])
        result=self.store.batch("favorite",[root,group])
        self.assertEqual(result["changed"],2)
        self.assertTrue(all(n["favorite"] for n in self.store.all()))
        self.store.batch("unfavorite",[group])
        self.assertEqual({n["title"]:n["favorite"] for n in self.store.all()},
                         {"科研":True,"研究":False})

    def test_batch_delete_cascades_navigation_and_images_only(self):
        root=self.store.create({"title":"根","node_type":"root"})
        leaf=self.store.create({"title":"叶","node_type":"leaf","parent_id":root,
                                "folder_path":str(Path(self.tmp.name).resolve())})
        self.store.save_image(leaf,ImageStoreTests.PNG_URL)
        folder=Path(self.tmp.name)/"keep.txt"
        folder.write_text("must survive",encoding="utf-8")
        result=self.store.batch("delete",[root,leaf])
        self.assertEqual((result["ok"],result["changed"],result["deleted"]),(True,2,2))
        self.assertIsInstance(result["trash_id"],int)
        self.assertEqual(self.store.all(),[])
        self.assertIsNone(self.store.get_image(leaf))
        self.assertEqual(folder.read_text(encoding="utf-8"),"must survive")

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
        with closing(sqlite3.connect(db_path)) as conn, conn:
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
        self.assertEqual(backup["version"],5)
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


class ImageStoreTests(unittest.TestCase):
    PNG_URL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLdlwAAAABJRU5ErkJggg=="

    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store=app.Store(Path(tmp.name)/"images.db")
        self.root=self.store.create({"title":"图像封面","node_type":"root","icon":"book"})

    def test_image_create_fetch_delete_and_preset_icon(self):
        self.store.save_image(self.root,self.PNG_URL)
        self.assertTrue(self.store.all()[0]["has_image"])
        self.assertEqual(self.store.all()[0]["icon"],"book")
        mime,data=self.store.get_image(self.root)
        self.assertEqual(mime,"image/png")
        self.assertTrue(data.startswith(b"\x89PNG"))
        self.store.update(self.root,{"title":"更新名称","icon":"code"})
        self.assertEqual(self.store.all()[0]["icon"],"code")
        self.assertTrue(self.store.all()[0]["has_image"])
        self.store.remove_image(self.root)
        self.assertFalse(self.store.all()[0]["has_image"])
        self.assertIsNone(self.store.get_image(self.root))

    def test_backup_includes_images_and_is_atomic(self):
        self.store.save_image(self.root,self.PNG_URL)
        backup=self.store.export()
        self.assertEqual(backup["version"],5)
        self.assertIn(str(self.root),backup["images"])
        self.store.delete(self.root)
        self.store.import_backup(backup)
        self.assertEqual(self.store.export()["images"],backup["images"])
        bad=json.loads(json.dumps(backup))
        bad["images"][str(self.root)]["base64"]="not-base64!"
        with self.assertRaises(app.UserError):self.store.import_backup(bad)
        self.assertEqual(self.store.export()["images"],backup["images"])

    def test_image_validation_rejects_unsafe_formats(self):
        import base64
        cases=["data:image/svg+xml;base64,"+base64.b64encode(b"<svg/>").decode(),
               "data:image/png;base64,"+base64.b64encode(b"<script>").decode(),
               "data:image/jpeg;base64,"+base64.b64encode(b"<svg>").decode(),
               "data:image/png;base64,bad*content", "data:image/png;base64,"+"A"*3000000]
        for value in cases:
            with self.subTest(value=value[:30]),self.assertRaises(app.UserError):
                self.store.save_image(self.root,value)
        with self.assertRaises(app.UserError):self.store.create({"title":"图标","icon":"<svg>"})
        self.assertFalse(self.store.all()[0]["has_image"])

    def test_v2_backup_preserves_without_images(self):
        backup=self.store.export()
        backup["version"]=2
        del backup["images"]
        self.store.import_backup(backup)
        self.assertEqual(self.store.all()[0]["title"],"图像封面")
        self.assertFalse(self.store.all()[0]["has_image"])


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

    def workspace_snapshot(self, ids):
        """Mirror the frozen, ordered confirmation shown by the browser."""
        nodes = {node["id"]: node for node in self.srv.store.all()}
        snapshot = []
        for node_id in ids:
            node = nodes.get(node_id)
            kind = node["resource_kind"] if node else None
            snapshot.append({
                "id": node_id, "title": node["title"] if node else None,
                "kind": kind,
                "target": (node["folder_path"] if kind == "folder"
                           else node["resource_target"]) if node else None,
            })
        return snapshot

    def test_v53_workspace_launch_http_auth_saved_ids_and_partial_failures(self):
        root=self.srv.store.create({"title":"Project","node_type":"root"})
        doc=self.srv.store.create({"title":"Paper","node_type":"leaf",
              "parent_id":root,"resource_kind":"file",
              "resource_target":r"D:\\Project\\paper.pdf"})
        web=self.srv.store.create({"title":"Website","node_type":"leaf",
              "parent_id":root,"resource_kind":"url",
              "resource_target":"https://example.org/"})
        self.srv.store.preferences.save({"workspaces":[{
            "name":"科研","description":"","members":[doc,web],
            "launch_ids":[doc,web]}]})
        endpoint="/api/workspaces/launch"
        self.assertEqual(self.request("POST",endpoint,{"name":"科研"},token=False)[0],403)
        self.assertEqual(self.request("POST",endpoint,{"name":"科研"},
                                      origin="https://evil.example")[0],403)
        self.assertEqual(self.request("POST",endpoint,{"name":"Unknown"})[0],400)
        called=[]
        def run(node):
            called.append(node["id"])
            if node["id"]==web:raise app.UserError("目标网页暂时无法启动")
        with patch.object(app,"open_saved_resource",side_effect=run):
            status,body=self.request("POST",endpoint,{"name":"科研","ids":[root],
                                                     "expected_items":self.workspace_snapshot([doc,web]),
                                                     "command":"dangerous"})
        self.assertEqual(status,200)
        self.assertEqual(body["attempted"],2)
        self.assertEqual(body["succeeded"],1)
        self.assertEqual([item["ok"] for item in body["results"]],[True,False])
        self.assertIn("目标网页暂时无法启动",body["results"][1]["error"])
        self.assertEqual(called,[doc,web])

    def test_v53_workspace_launch_empty_missing_and_category_never_execute(self):
        root=self.srv.store.create({"title":"Root","node_type":"root"})
        self.srv.store.preferences.save({"workspaces":[{
            "name":"Old","description":"","members":[root]}]})
        with patch.object(app,"open_saved_resource") as opener:
            self.assertEqual(self.request("POST","/api/workspaces/launch",{"name":"Old"})[0],400)
            self.srv.store.preferences.save({"workspaces":[{
                "name":"BadType","description":"","members":[root],
                "launch_ids":[root]}]})
            status,response=self.request("POST","/api/workspaces/launch",
                 {"name":"BadType","expected_items":self.workspace_snapshot([root])})
            self.assertEqual(status,200)
            self.assertFalse(response["results"][0]["ok"])
            self.assertIn("分类模块",response["results"][0]["error"])
            opener.assert_not_called()

    def test_v56_quick_menu_api_is_read_only_bounded_and_path_free(self):
        root=self.srv.store.create({"title":"Projects","node_type":"root"})
        folder=self.srv.store.create({"title":"Folder","node_type":"leaf",
                   "parent_id":root,"folder_path":r"D:\\Data"})
        doc=self.srv.store.create({"title":"PDF","node_type":"leaf",
                   "parent_id":root,"resource_kind":"file",
                   "resource_target":r"D:\\Data\\report.pdf"})
        web=self.srv.store.create({"title":"Web","node_type":"leaf",
                   "parent_id":root,"resource_kind":"url",
                   "resource_target":"https://example.org/"})
        # More than eight workspaces should still produce eight quick links.
        self.srv.store.preferences.save({"workspaces":[
            {"name":"Workspace "+str(i),"description":"","members":[folder]}
            for i in range(12)]})
        status,body=self.request("GET","/api/quick-menu")
        self.assertEqual(status,200)
        self.assertEqual({row["id"] for row in body["nodes"]},{folder,doc,web})
        self.assertEqual([w["name"] for w in body["workspaces"]],
                         ["Workspace "+str(i) for i in range(8)])
        self.assertLessEqual(len(body["nodes"]),24)
        self.assertTrue(all(row.get("has_target") is True for row in body["nodes"]))
        self.assertTrue(all("folder_path" not in row and
                            "resource_target" not in row and
                            "tags" not in row for row in body["nodes"]))
        self.assertFalse("D:\\\\Data" in json.dumps(body,ensure_ascii=False))
        self.assertEqual(self.request("POST","/api/quick-menu",{})[0],405)
        # No navigation state changes, even if requested repeatedly.
        original=self.srv.store.export()
        for _ in range(3):
            self.assertEqual(self.request("GET","/api/quick-menu")[0],200)
        self.assertEqual(self.srv.store.export(),original)

    def test_v54_workspace_launch_requires_fresh_ordered_resource_snapshot(self):
        root = self.srv.store.create({"title":"Project","node_type":"root"})
        doc = self.srv.store.create({"title":"Report","node_type":"leaf",
            "parent_id":root,"resource_kind":"file",
            "resource_target":r"D:\\Project\\report.pdf"})
        web = self.srv.store.create({"title":"Docs","node_type":"leaf",
            "parent_id":root,"resource_kind":"url",
            "resource_target":"https://example.org/"})
        workspace = {"name":"Lab","description":"","members":[doc,web],
                     "launch_ids":[doc,web]}
        self.srv.store.preferences.save({"workspaces":[workspace]})
        original = self.workspace_snapshot([doc,web])
        endpoint = "/api/workspaces/launch"

        with patch.object(app,"open_saved_resource") as opener:
            bad_requests = [
                {"name":"Lab"},  # Previous frontend versions must refresh.
                {"name":"Lab","expected_items":list(reversed(original))},
                {"name":"Lab","expected_items":[{**original[0],"id":True},original[1]]},
                {"name":"Lab","expected_items":[{**original[0],"target":"D:changed"},original[1]]},
                {"name":"Lab","expected_items":[{**original[0],"title":"Renamed"},original[1]]},
                {"name":"Lab","expected_items":[{**original[0],"extra":"unconfirmed"},original[1]]},
            ]
            for request in bad_requests:
                with self.subTest(request=request):
                    status, response = self.request("POST",endpoint,request)
                    self.assertEqual(status,400)
                    self.assertIn("重新确认",response["error"])
            opener.assert_not_called()

            self.srv.store.update(doc,{"resource_target":r"D:\\Project\\report-v2.pdf"})
            status, response = self.request("POST",endpoint,
                {"name":"Lab","expected_items":original})
            self.assertEqual(status,400)
            self.assertIn("重新确认",response["error"])
            opener.assert_not_called()

            refreshed = self.workspace_snapshot([doc,web])
            status, response = self.request("POST",endpoint,
                {"name":"Lab","expected_items":refreshed})
            self.assertEqual(status,200)
            self.assertEqual(response["succeeded"],2)
            self.assertEqual(opener.call_count,2)

            # The preferences schema requires launch_ids to follow member
            # order. Reorder both to test a *valid* concurrent-tab change.
            reordered = {**workspace,"members":[web,doc],"launch_ids":[web,doc]}
            self.srv.store.preferences.save({"workspaces":[reordered]})
            opener.reset_mock()
            status, response = self.request("POST",endpoint,
                {"name":"Lab","expected_items":refreshed})
            self.assertEqual(status,400)
            self.assertIn("重新确认",response["error"])
            opener.assert_not_called()

    def test_everything_search_endpoint_is_opt_in_and_bounds_input(self):
        payload={"items":[{"name":"report.pdf","path":r"C:\Docs\report.pdf",
                            "kind":"file"}],"source":"Everything","limit":30}
        with patch.object(app.everything_search,"search",return_value=payload) as search:
            code,response=self.request("GET","/api/everything/search?q=report")
            self.assertEqual((code,response),(200,payload))
            search.assert_called_once_with("report")
        self.assertTrue(response["items"][0]["supported"])
        self.assertEqual(self.request("GET","/api/everything/search?q=a")[0],400)
        self.assertEqual(self.request("GET","/api/everything/search")[0],400)

    def test_v51_everything_marks_executable_results_unavailable_for_import(self):
        payload={"items":[{"name":"installer.exe","path":r"C:\Tools\installer.exe",
                            "kind":"file"},
                           {"name":"研究报告.pdf","path":r"C:\Docs\研究报告.pdf",
                            "kind":"file"},
                           {"name":"资料目录","path":r"C:\Docs",
                            "kind":"folder"}],"source":"Everything","limit":30}
        with patch.object(app.everything_search,"search",return_value=payload):
            code,body=self.request("GET","/api/everything/search?q=report")
        self.assertEqual(code,200)
        self.assertEqual([item["supported"] for item in body["items"]],
                         [False,True,True])
        self.assertTrue(all(item["path"]==payload["items"][i]["path"]
                            for i,item in enumerate(body["items"])))

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

    def test_image_api_and_security(self):
        url=ImageStoreTests.PNG_URL
        root=self.srv.store.create({"title":"测试","node_type":"root"})
        path=f"/api/nodes/{root}/image"
        self.assertEqual(self.request("POST",path,{"data_url":url},token=False)[0],403)
        self.assertEqual(self.request("POST",path,{"data_url":url})[0],200)
        self.assertTrue(self.request("GET","/api/nodes")[1]["nodes"][0]["has_image"])
        conn=http.client.HTTPConnection("127.0.0.1",self.srv.server_port,timeout=3)
        conn.request("GET",path,headers={"Host":self.host})
        response=conn.getresponse()
        self.assertEqual(response.status,200)
        self.assertEqual(response.getheader("Content-Type"),"image/png")
        self.assertEqual(response.getheader("X-Content-Type-Options"),"nosniff")
        self.assertTrue(response.read().startswith(b"\x89PNG"));conn.close()
        self.assertEqual(self.request("DELETE",path,{},token=False)[0],403)
        self.assertEqual(self.request("DELETE",path,{})[0],200)
        self.assertEqual(self.request("GET",path)[0],404)

    def test_batch_http_requires_token_and_works_atomically(self):
        root=self.srv.store.create({"title":"根","node_type":"root"})
        other=self.srv.store.create({"title":"另一个","node_type":"root"})
        payload={"action":"favorite","ids":[root,other]}
        self.assertEqual(self.request("POST","/api/batch",payload,token=False)[0],403)
        self.assertEqual(self.request("POST","/api/batch",payload,origin="https://evil.test")[0],403)
        self.assertEqual(self.request("POST","/api/batch",{"action":"favorite","ids":[root,999]})[0],400)
        self.assertTrue(all(not n["favorite"] for n in self.srv.store.all()))
        status,response=self.request("POST","/api/batch",payload)
        self.assertEqual((status,response["changed"]),(200,2))
        self.assertTrue(all(n["favorite"] for n in self.srv.store.all()))
        self.assertEqual(self.request("POST","/api/batch",{"action":"delete","ids":[other]})[0],200)
        self.assertEqual([n["id"] for n in self.srv.store.all()],[root])

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



class TrashTests(unittest.TestCase):
    """Navigation-only recycle bin: atomic subtree snapshots and reversible deletion."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = app.Store(Path(self.tmp.name)/"trash.db")

    def test_restore_entire_subtree_and_original_properties(self):
        root = self.store.create({"title":"论文", "node_type":"root", "icon":"book"})
        folder = self.store.create({"title":"实验", "node_type":"group", "parent_id":root})
        leaf = self.store.create({"title":"GEANT", "node_type":"leaf", "parent_id":folder,
                                  "folder_path":r"D:\Research\GEANT", "favorite":True})
        png = "data:image/png;base64," + __import__('base64').b64encode(
            b"\x89PNG\r\n\x1a\n" + b"\x00"*4 + b"IHDR" + b"\x00"*12).decode()
        self.store.save_image(leaf,png)
        before=self.store.all()
        result=self.store.delete(root)
        self.assertEqual((result["ok"],result["deleted"]),(True,3))
        self.assertEqual(self.store.all(),[])
        self.assertIsNone(self.store.get_image(leaf))
        self.assertEqual(self.store.trash_list()[0]["item_count"],3)
        back=self.store.restore_trash(result["trash_id"])
        self.assertEqual(back["restored"],3)
        restored=self.store.all()
        self.assertEqual([r["id"] for r in restored],[r["id"] for r in before])
        self.assertEqual(next(r for r in restored if r["id"]==leaf)["folder_path"],r"D:\Research\GEANT")
        self.assertTrue(next(r for r in restored if r["id"]==leaf)["favorite"])
        self.assertEqual(self.store.get_image(leaf)[0],"image/png")
        self.assertEqual(self.store.trash_list(),[])

    def test_batch_snapshot_no_duplicate_children_and_atomic_failure(self):
        root=self.store.create({"title":"Root", "node_type":"root"})
        group=self.store.create({"title":"Child", "node_type":"group", "parent_id":root})
        leaf=self.store.create({"title":"Folder", "node_type":"leaf", "parent_id":group,
                                "folder_path":r"D:\stuff"})
        with self.assertRaises(app.UserError):self.store.batch("delete",[root,999999])
        self.assertEqual(len(self.store.all()),3)
        self.assertFalse(self.store.trash_list())
        response=self.store.batch("delete",[root,leaf])
        self.assertEqual(response["deleted"],3)
        self.assertEqual(self.store.trash_list()[0]["selected_count"],2)
        self.store.restore_trash(response["trash_id"])
        self.assertEqual(len(self.store.all()),3)

    def test_recovery_requires_original_parent_and_preserves_trash_on_error(self):
        root=self.store.create({"title":"Root", "node_type":"root"})
        group=self.store.create({"title":"Child", "node_type":"group", "parent_id":root})
        r=self.store.delete(group)
        self.store.delete(root)
        with self.assertRaisesRegex(app.UserError,"上级模块"):
            self.store.restore_trash(r["trash_id"])
        self.assertEqual(len(self.store.trash_list()),2)
        for batch in self.store.trash_list():
            self.store.restore_trash(batch["id"])
        self.assertEqual(len(self.store.all()),2)

    def test_purge_does_not_affect_actual_path(self):
        folder=Path(self.tmp.name)/"keep-me"
        folder.mkdir()
        leaf=self.store.create({"title":"Folder", "node_type":"root"})
        batch=self.store.delete(leaf)
        self.store.purge_trash(batch["trash_id"])
        self.assertTrue(folder.is_dir())
        self.assertEqual(self.store.trash_list(),[])
        with self.assertRaises(app.UserError):self.store.restore_trash(batch["trash_id"])

    def test_restore_id_collision_rolls_back(self):
        a=self.store.create({"title":"A", "node_type":"root"})
        batch=self.store.delete(a)
        # Explicit old ID reuse, as can happen after importing a prior backup.
        with self.store.connect() as db:
            db.execute("""INSERT INTO nodes(id,parent_id,title,node_type,icon,favorite,sort_order,created_at,updated_at)
                VALUES(?,NULL,'replacement','root','folder',0,0,'x','x')""",(a,))
        with self.assertRaisesRegex(app.UserError,"ID"):
            self.store.restore_trash(batch["trash_id"])
        self.assertEqual(len(self.store.trash_list()),1)
        self.assertEqual(self.store.all()[0]["title"],"replacement")


class TrashHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.server=app.FolderServer(("127.0.0.1",0),app.Store(Path(self.tmp.name)/"server.db"))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)

    def request(self,method,path,payload=None,authenticated=True):
        conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=5)
        headers={"Host":f"127.0.0.1:{self.server.server_port}"}
        if payload is not None:headers["Content-Type"]="application/json"
        if authenticated:headers["X-FolderHub-Token"]=self.server.token
        conn.request(method,path,body=json.dumps(payload) if payload is not None else None,headers=headers)
        response=conn.getresponse();raw=response.read();status=response.status;conn.close()
        return status,json.loads(raw)

    def test_trash_auth_restore_and_purge(self):
        node=self.server.store.create({"title":"Test", "node_type":"root"})
        status,deleted=self.request("DELETE",f"/api/nodes/{node}")
        self.assertEqual(status,200)
        rid=deleted["trash_id"]
        self.assertEqual(self.request("GET","/api/trash")[1]["items"][0]["id"],rid)
        self.assertEqual(self.request("POST",f"/api/trash/{rid}/restore",{},False)[0],403)
        self.assertEqual(self.request("DELETE",f"/api/trash/{rid}",{},False)[0],403)
        self.assertEqual(self.request("POST",f"/api/trash/{rid}/restore",{})[0],200)
        self.assertEqual(len(self.server.store.all()),1)
        self.assertEqual(self.request("GET","/api/trash")[1]["items"],[])
        new=self.request("DELETE",f"/api/nodes/{node}")[1]["trash_id"]
        self.assertEqual(self.request("DELETE",f"/api/trash/{new}",{})[0],200)
        self.assertEqual(self.request("POST",f"/api/trash/{new}/restore",{})[0],400)


if __name__ == "__main__":
    unittest.main()



class RecentUsageTests(unittest.TestCase):
    """Recent folders belong to portable SQLite and never manipulate disk paths."""

    def setUp(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store=app.Store(Path(folder.name)/"data"/"folderhub.db")

    def test_recent_order_counter_and_delete_cascade(self):
        root=self.store.create({"title":"根","node_type":"root"})
        a=self.store.create({"title":"A","node_type":"leaf","parent_id":root,"folder_path":r"D:\\A"})
        b=self.store.create({"title":"B","node_type":"leaf","parent_id":root,"folder_path":r"D:\\B"})
        self.assertEqual(self.store.recent(),[])
        self.store.record_open(a)
        self.store.record_open(b)
        self.store.record_open(a)
        self.assertEqual([v["node_id"] for v in self.store.recent()],[a,b])
        self.assertEqual(self.store.recent()[0]["open_count"],2)
        self.assertEqual(len(self.store.recent(limit=1)),1)
        self.store.delete(a)
        self.assertEqual([v["node_id"] for v in self.store.recent()],[b])

    def test_clear_is_navigation_safe_and_rejects_invalid_limits(self):
        root=self.store.create({"title":"根","node_type":"root"})
        leaf=self.store.create({"title":"叶","node_type":"leaf","parent_id":root,"folder_path":r"E:\\Research"})
        self.store.record_open(leaf)
        self.assertEqual(self.store.clear_recent(),{"ok":True,"cleared":1})
        self.assertEqual(self.store.recent(),[])
        self.assertEqual(len(self.store.all()),2)
        for val in (True,0,-1,201,"20"):
            with self.subTest(limit=val),self.assertRaises(app.UserError):self.store.recent(val)

    def test_recent_survives_portable_copy_and_full_import_resets(self):
        root=self.store.create({"title":"根","node_type":"root"})
        leaf=self.store.create({"title":"资料","node_type":"leaf","parent_id":root,"folder_path":r"D:\\Docs"})
        self.store.record_open(leaf)
        folder=Path(self.store.db_path.parent)
        moved=folder.parent/"moved.db"
        with self.store.connect() as src, closing(app.sqlite3.connect(moved)) as target:
            src.backup(target)
            target.commit()
        restored=app.Store(moved)
        self.assertEqual(restored.recent()[0]["node_id"],leaf)
        data=restored.export()
        restored.import_backup(data)
        self.assertEqual(restored.recent(),[], "Full JSON replacement resets history for reused node IDs")


class RecentUsageHttpTests(unittest.TestCase):
    # Reuse the HTTP fixture without inheriting and re-running every HttpTests case.
    setUp = HttpTests.setUp
    request = HttpTests.request

    def test_open_success_only_and_recent_clear_security(self):
        root=self.srv.store.create({"title":"根","node_type":"root"})
        leaf=self.srv.store.create({"title":"入口","node_type":"leaf","parent_id":root,
                                    "folder_path":str(self.srv.store.db_path.parent)})
        url=f"/api/nodes/{leaf}/open"
        with patch.object(app,"open_in_explorer",side_effect=app.UserError("无法打开")):
            self.assertEqual(self.request("POST",url,{})[0],400)
            self.assertEqual(self.request("GET","/api/recent")[1]["items"],[])
        with patch.object(app,"open_in_explorer",return_value=None):
            self.assertEqual(self.request("POST",url,{})[0],200)
        self.assertEqual(self.request("GET","/api/recent")[1]["items"][0]["node_id"],leaf)
        # Windows may reset the socket when an unauthenticated request body
        # remains unread before the HTTP/1.0 handler closes the connection.
        for _ in range(4):
            self.assertEqual(self.request("DELETE","/api/recent",{},token=False)[0],403)
        self.assertEqual(self.request("DELETE","/api/recent",{},origin="https://evil.example")[0],403)
        self.assertEqual(self.request("DELETE","/api/recent",{})[1]["cleared"],1)
        self.assertEqual(len(self.srv.store.all()),2)


class RecentPinTests(unittest.TestCase):
    """V2.5: portable pinned folders, including legacy schema migration."""
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store=app.Store(Path(temporary.name)/"data"/"folderhub.db")

    def test_pin_sort_repeat_open_and_unpin(self):
        root=self.store.create({"title":"根","node_type":"root"})
        a=self.store.create({"title":"A","node_type":"leaf","parent_id":root,"folder_path":r"D:\A"})
        b=self.store.create({"title":"B","node_type":"leaf","parent_id":root,"folder_path":r"D:\B"})
        self.store.record_open(a)
        self.store.record_open(b)
        self.assertEqual([v["node_id"] for v in self.store.recent()],[b,a])
        self.assertEqual(self.store.set_recent_pin(a,True), {"ok":True,"node_id":a,"pinned":True})
        self.assertEqual([v["node_id"] for v in self.store.recent()],[a,b])
        self.store.record_open(b)
        self.assertEqual([v["node_id"] for v in self.store.recent()],[a,b])
        self.assertEqual(self.store.recent()[0]["pinned"],1)
        self.assertEqual(self.store.recent()[1]["open_count"],2)
        self.store.set_recent_pin(a,False)
        self.assertEqual([v["node_id"] for v in self.store.recent()],[b,a])

    def test_pin_input_validation_is_atomic(self):
        root=self.store.create({"title":"根","node_type":"root"})
        a=self.store.create({"title":"A","node_type":"leaf","parent_id":root,"folder_path":r"D:\A"})
        for identity, pin in [(a,True),(a,False)]:
            with self.assertRaises(app.UserError):self.store.set_recent_pin(identity,pin)
        self.store.record_open(a)
        for identity,pin in [(a,1),(a,"true"),(True,True),(0,True),(99999,True)]:
            with self.subTest(identity=identity,pin=pin),self.assertRaises(app.UserError):
                self.store.set_recent_pin(identity,pin)
        self.assertEqual(self.store.recent()[0]["pinned"],0)
        self.store.set_recent_pin(a,True)
        self.assertEqual(self.store.clear_recent()["cleared"],1)
        self.assertEqual(self.store.recent(),[])
        self.assertEqual(len(self.store.all()),2)

    def test_pre_v25_visits_schema_migration(self):
        db_path=self.store.db_path
        with self.store.connect() as conn:
            conn.execute("DROP INDEX IF EXISTS idx_node_visits_pin_time")
            conn.execute("DROP TABLE node_visits")
            conn.execute("""CREATE TABLE node_visits (node_id INTEGER PRIMARY KEY
                         REFERENCES nodes(id) ON DELETE CASCADE,
                         open_count INTEGER NOT NULL DEFAULT 0,last_opened_at TEXT NOT NULL)""")
        migrated=app.Store(db_path)
        with migrated.connect() as conn:
            columns={r["name"] for r in conn.execute("PRAGMA table_info(node_visits)")}
        self.assertIn("pinned",columns)
        self.assertEqual(migrated.recent(),[])

    def test_pins_survive_zip_and_are_removed_with_node(self):
        import zipfile
        root=self.store.create({"title":"根","node_type":"root"})
        a=self.store.create({"title":"A","node_type":"leaf","parent_id":root,"folder_path":r"D:\A"})
        self.store.record_open(a);self.store.set_recent_pin(a,True)
        backup=self.store.make_portable_backup()
        try:
            with zipfile.ZipFile(backup) as archive:
                payload=archive.read("data/folderhub.db")
            other=Path(self.store.db_path.parent)/"from-zip.db"
            other.write_bytes(payload)
            moved=app.Store(other)
            self.assertEqual(moved.recent()[0]["pinned"],1)
        finally:
            backup.unlink(missing_ok=True)
        self.store.delete(a)
        self.assertEqual(self.store.recent(),[])


class RecentPinHttpTests(unittest.TestCase):
    setUp=HttpTests.setUp
    request=HttpTests.request

    def test_pin_endpoint_auth_and_validation(self):
        root=self.srv.store.create({"title":"根","node_type":"root"})
        leaf=self.srv.store.create({"title":"叶","node_type":"leaf","parent_id":root,"folder_path":r"D:\A"})
        self.srv.store.record_open(leaf)
        url="/api/recent/pin";params={"node_id":leaf,"pinned":True}
        self.assertEqual(self.request("POST",url,params,token=False)[0],403)
        self.assertEqual(self.request("POST",url,params,origin="https://evil.example")[0],403)
        self.assertEqual(self.request("POST",url,{"node_id":leaf,"pinned":1})[0],400)
        self.assertEqual(self.request("POST",url,params)[0],200)
        self.assertEqual(self.request("GET","/api/recent")[1]["items"][0]["pinned"],1)
        self.assertEqual(self.request("POST",url,{"node_id":leaf,"pinned":False})[1]["pinned"],False)
        self.assertEqual(self.request("DELETE","/api/recent",{})[0],200)


class TagStoreTests(unittest.TestCase):
    """V3.2: labels are data, not operations on real folders."""
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.store=app.Store(Path(temp.name)/"data"/"folderhub.db")

    def test_create_patch_and_reject_invalid_tags_atomically(self):
        root=self.store.create({"title":"研究","node_type":"root","tags":["论文","A股"]})
        self.assertEqual(self.store.all()[0]["tags"],["论文","A股"])
        self.store.update(root,{"title":"研究室"})
        self.assertEqual(self.store.all()[0]["tags"],["论文","A股"])
        self.store.update(root,{"tags":["教学","Python"]})
        baseline=self.store.export()["nodes"]
        for invalid in ("股票",["重复","重复"],["a","A"],[""],["x"*25],
                        ["a,b"],["a\n"],[5],[True],list(map(str,range(13))),{"金融":True}):
            with self.subTest(value=str(invalid)[:50]),self.assertRaises(app.UserError):
                self.store.update(root,{"tags":invalid})
            self.assertEqual(self.store.export()["nodes"],baseline)

    def test_tags_survive_trash_json_backup_and_full_zip(self):
        root=self.store.create({"title":"科研","node_type":"root","tags":["工作"]})
        leaf=self.store.create({"title":"A股","node_type":"leaf","parent_id":root,
                                "folder_path":r"D:\Stocks","tags":["股票","数据"]})
        export=self.store.export()
        self.assertEqual(export["version"],5)
        self.assertEqual(next(n["tags"] for n in export["nodes"] if n["id"]==leaf),["股票","数据"])
        trash=self.store.delete(root)
        self.assertEqual(self.store.all(),[])
        self.store.restore_trash(trash["trash_id"])
        self.assertEqual(next(n["tags"] for n in self.store.all() if n["id"]==leaf),["股票","数据"])
        self.store.import_backup(export)
        self.assertEqual(next(n["tags"] for n in self.store.all() if n["id"]==leaf),["股票","数据"])
        archive=self.store.make_portable_backup()
        try:
            import zipfile
            with zipfile.ZipFile(archive) as z:
                contents=z.read("data/folderhub.db")
            copy=Path(self.store.db_path.parent)/"copied.db"
            copy.write_bytes(contents)
            restored=app.Store(copy)
            self.assertEqual(next(n["tags"] for n in restored.all() if n["id"]==leaf),["股票","数据"])
        finally:
            archive.unlink(missing_ok=True)

    def test_legacy_backup_v3_omits_tags_and_imports_cleanly(self):
        self.store.create({"title":"研究","node_type":"root","tags":["新版"]})
        v3=self.store.export();v3["version"]=3
        for n in v3["nodes"]:n.pop("tags",None)
        self.store.import_backup(v3)
        self.assertEqual(self.store.all()[0]["tags"],[])

    def test_http_tag_validation_and_auth(self):
        server=app.FolderServer(("127.0.0.1",0),self.store)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        def send(method,path,payload=None,auth=True):
            conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=4)
            headers={"Host":f"127.0.0.1:{server.server_port}"}
            if payload is not None:headers["Content-Type"]="application/json"
            if method!="GET" and auth:headers["X-FolderHub-Token"]=server.token
            conn.request(method,path,body=json.dumps(payload) if payload is not None else None,headers=headers)
            r=conn.getresponse();status=r.status;data=json.loads(r.read());conn.close()
            return status,data
        status,res=send("POST","/api/nodes",{"title":"研究","node_type":"root","tags":["金融","论文"]})
        self.assertEqual(status,201);node_id=res["id"]
        self.assertEqual(send("PATCH",f"/api/nodes/{node_id}",{"tags":["新"]},auth=False)[0],403)
        self.assertEqual(send("PATCH",f"/api/nodes/{node_id}",{"tags":["重复","重复"]})[0],400)
        self.assertEqual(send("GET","/api/nodes")[1]["nodes"][0]["tags"],["金融","论文"])
        self.assertEqual(send("PATCH",f"/api/nodes/{node_id}",{"tags":["金融","量化"]})[0],200)
        self.assertEqual(send("GET","/api/nodes")[1]["nodes"][0]["tags"],["金融","量化"])


class TagMaintenanceTests(unittest.TestCase):
    """Tag management changes only the navigation DB, not real folder paths."""

    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.store=app.Store(Path(folder.name)/"db"/"folderhub.db")
        self.a=self.store.create({"title":"A","node_type":"root","tags":["A股","数据"]})
        self.b=self.store.create({"title":"B","node_type":"root","tags":["论文"]})

    def tags(self,node_id):
        return next(node["tags"] for node in self.store.all() if node["id"]==node_id)

    def test_batch_add_remove_and_preserve_order(self):
        out=self.store.batch_tags("add",[self.a,self.b],["量化","A股"])
        self.assertEqual((out["changed"],out["selected"]),(2,2))
        self.assertEqual(self.tags(self.a),["A股","数据","量化"])
        self.assertEqual(self.tags(self.b),["论文","量化","A股"])
        self.assertEqual(self.store.batch_tags("add",[self.a],["A股"])["changed"],0)
        self.assertEqual(self.store.batch_tags("remove",[self.a,self.b],["数据","量化"])["changed"],2)
        self.assertEqual(self.tags(self.a),["A股"])
        self.assertEqual(self.tags(self.b),["论文","A股"])

    def test_validation_and_limit_errors_are_atomic(self):
        self.store.update(self.a,{"tags":[str(i) for i in range(12)]})
        initial=self.store.export()["nodes"]
        for action,ids,tags in (
            ("add",[self.a,self.b],["overflow"]),
            ("add",[self.a,9999],["x"]),
            ("add",[self.a,self.a],["x"]),
            ("remove",[self.a],[]),
            ("add",[self.a],[True]),
            ("add",[self.a],["x","X"]),
            ("unknown",[self.a],["x"]),
            ("remove",[True],["x"]),
        ):
            with self.subTest(action=action,ids=ids,tags=tags),self.assertRaises(app.UserError):
                self.store.batch_tags(action,ids,tags)
            self.assertEqual(self.store.export()["nodes"],initial)

    def test_global_rename_merges_and_carries_into_recycle_bin(self):
        self.store.update(self.a,{"tags":["A股","论文"]})
        deleted=self.store.delete(self.b)
        result=self.store.rename_tag("论文","A股")
        self.assertEqual(result["changed"],2)
        self.assertEqual(self.tags(self.a),["A股"])
        self.store.restore_trash(deleted["trash_id"])
        self.assertEqual(self.tags(self.b),["A股"])
        self.assertEqual(self.store.rename_tag("A股","股票")["changed"],2)
        self.assertEqual(self.tags(self.a),["股票"])
        self.assertEqual(self.tags(self.b),["股票"])
        with self.assertRaises(app.UserError):self.store.rename_tag("不存在","测试")

    def test_http_tag_mutations_require_auth(self):
        server=app.FolderServer(("127.0.0.1",0),self.store)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        def call(path,body,auth=True):
            conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=4)
            headers={"Host":f"127.0.0.1:{server.server_port}","Content-Type":"application/json"}
            if auth:headers["X-FolderHub-Token"]=server.token
            conn.request("POST",path,json.dumps(body),headers)
            r=conn.getresponse();status=r.status;payload=json.loads(r.read());conn.close()
            return status,payload
        bulk={"action":"add","ids":[self.a,self.b],"tags":["整理"]}
        self.assertEqual(call("/api/tags/batch",bulk,False)[0],403)
        self.assertEqual(call("/api/tags/batch",bulk)[0],200)
        self.assertEqual(call("/api/tags/rename",{"source":"整理","target":"归档"},False)[0],403)
        self.assertEqual(call("/api/tags/rename",{"source":"整理","target":"归档"})[0],200)
        self.assertIn("归档",self.tags(self.a))


class FrequentUsageTests(unittest.TestCase):
    """Frequency-ranked folder shortcuts reuse the existing bounded visit table."""

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=app.Store(Path(self.tmp.name)/"folderhub.db")
        root=self.store.create({"title":"项目","node_type":"root"})
        self.a=self.store.create({"title":"A","node_type":"leaf","parent_id":root,"folder_path":r"D:\\A"})
        self.b=self.store.create({"title":"B","node_type":"leaf","parent_id":root,"folder_path":r"D:\\B"})
        self.c=self.store.create({"title":"C","node_type":"leaf","parent_id":root,"folder_path":r"D:\\C"})

    def test_count_ranking_is_distinct_from_recency_and_pinning(self):
        for _ in range(5):
            self.store.record_open(self.a)
        for _ in range(3):
            self.store.record_open(self.b)
        self.store.record_open(self.c)
        self.assertEqual([row["node_id"] for row in self.store.frequent()],
                         [self.a,self.b,self.c])
        self.assertEqual([row["open_count"] for row in self.store.frequent()],
                         [5,3,1])
        self.assertEqual([row["node_id"] for row in self.store.recent()],
                         [self.c,self.b,self.a])
        self.store.set_recent_pin(self.c,True)
        self.assertEqual(self.store.frequent()[0]["node_id"],self.a)
        self.assertEqual([row["node_id"] for row in self.store.frequent(limit=1)],[self.a])

    def test_bad_limits_deletion_and_history_clear(self):
        for bad in (True,False,0,-1,201,"30",None):
            with self.subTest(bad=bad),self.assertRaises(app.UserError):
                self.store.frequent(bad)
        self.store.record_open(self.a)
        self.store.record_open(self.b)
        self.store.delete(self.a)
        self.assertEqual([row["node_id"] for row in self.store.frequent()],[self.b])
        self.store.clear_recent()
        self.assertEqual(self.store.frequent(),[])

    def test_read_only_http_endpoint(self):
        server=app.FolderServer(("127.0.0.1",0),self.store)
        worker=threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.store.record_open(self.a)
        conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=5)
        conn.request("GET","/api/frequent",
                     headers={"Host":f"127.0.0.1:{server.server_port}"})
        response=conn.getresponse()
        self.assertEqual(response.status,200)
        self.assertEqual(json.loads(response.read())["items"][0]["node_id"],self.a)
        conn.close()
        conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=5)
        conn.request("POST","/api/frequent",body="{}",headers={
            "Host":f"127.0.0.1:{server.server_port}",
            "X-FolderHub-Token":server.token,"Content-Type":"application/json"})
        response=conn.getresponse()
        self.assertEqual(response.status,405)
        response.read()
        conn.close()



class FolderGroupOpenTests(unittest.TestCase):
    """One-click groups open saved IDs only, never client-provided filesystem paths."""

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=app.Store(Path(self.tmp.name)/'db'/'folderhub.db')
        root=self.store.create({"title":"研究","node_type":"root"})
        self.good=self.store.create({"title":"数据","node_type":"leaf","parent_id":root,
                                     "folder_path":r"D:\\Data"})
        self.bad=self.store.create({"title":"结果","node_type":"leaf","parent_id":root,
                                    "folder_path":r"D:\\Results"})
        self.store.preferences.save({'folderGroups':[{
            'name':'量化研究','members':[self.good,self.bad]}]})

    def test_group_continues_after_failed_explorer_and_records_success_only(self):
        def try_open(path):
            if path == r"D:\\Results":
                raise app.UserError("磁盘暂不可访问")
        with patch.object(app,"open_in_explorer",side_effect=try_open) as opened:
            result=self.store.open_folder_group("量化研究")
        self.assertEqual(opened.call_count,2)
        self.assertEqual((result["opened"],result["failed"]),(1,1))
        self.assertEqual([row["ok"] for row in result["results"]],[True,False])
        self.assertEqual(result["results"][1]["error"],"磁盘暂不可访问")
        self.assertEqual(self.store.frequent()[0]["node_id"],self.good)
        self.assertEqual(len(self.store.frequent()),1)

    def test_removed_module_does_not_abort_remaining_opens(self):
        self.store.delete(self.good)
        with patch.object(app,"open_in_explorer",return_value=None) as launched:
            result=self.store.open_folder_group("量化研究")
        self.assertEqual(result["opened"],1)
        self.assertEqual(result["failed"],1)
        self.assertIn("已删除",result["results"][0]["error"])
        launched.assert_called_once_with(r"D:\\Results")

    def test_name_or_missing_group_is_rejected(self):
        for name in ("不存在",True,[],None,""):
            with self.subTest(name=name),self.assertRaises(app.UserError):
                self.store.open_folder_group(name)

    def test_second_group_open_request_is_rejected_while_busy(self):
        server=app.FolderServer(("127.0.0.1",0),self.store)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def post():
            conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=5)
            headers={"Host":f"127.0.0.1:{server.server_port}",
                     "Content-Type":"application/json",
                     "X-FolderHub-Token":server.token}
            conn.request("POST","/api/groups/open",json.dumps({"name":"量化研究"}),headers)
            resp=conn.getresponse();status=resp.status;payload=json.loads(resp.read())
            conn.close();return status,payload
        with (server._group_open_lock,
              patch.object(app,"open_in_explorer",return_value=None) as launched):
            status,payload=post()
            self.assertEqual(status,400)
            self.assertIn("正在打开",payload["error"])
            launched.assert_not_called()
        with patch.object(app,"open_in_explorer",return_value=None):
            self.assertEqual(post()[0],200)

    def test_group_endpoint_is_authenticated_and_rejects_raw_paths(self):
        server=app.FolderServer(("127.0.0.1",0),self.store)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def post(body,token=True):
            conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=5)
            headers={"Host":f"127.0.0.1:{server.server_port}",
                     "Content-Type":"application/json"}
            if token:headers["X-FolderHub-Token"]=server.token
            conn.request("POST","/api/groups/open",json.dumps(body),headers)
            resp=conn.getresponse();status=resp.status;data=json.loads(resp.read())
            conn.close();return status,data
        with patch.object(app,"open_in_explorer",return_value=None) as launched:
            self.assertEqual(post({"name":"量化研究"},False)[0],403)
            self.assertEqual(post({"name":"不存在","path":r"C:\\Private"})[0],400)
            status,data=post({"name":"量化研究","path":r"C:\\Private"})
        self.assertEqual(status,200)
        self.assertEqual(data["opened"],2)
        self.assertEqual(launched.call_count,2)
        self.assertEqual(self.store.frequent()[0]["open_count"],1)
