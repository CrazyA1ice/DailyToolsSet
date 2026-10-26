"""FolderHub: a dependency-free, local-only Windows folder dashboard."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import ntpath
import os
from pathlib import Path
import secrets
import sqlite3
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import webbrowser
import startup
import explorer_window

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
MAX_REQUEST = 2 * 1024 * 1024
NODE_TYPES = ("root", "group", "leaf")


class UserError(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_title(value):
    if not isinstance(value, str):
        raise UserError("名称必须是文字")
    value = value.strip()
    if not value or len(value) > 100:
        raise UserError("名称不能为空，也不能超过 100 个字符")
    return value


def validate_path(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise UserError("文件夹路径必须是文字")
    value = value.strip().strip('"')
    if not value:
        return None
    if len(value) > 2048 or "\x00" in value or "\n" in value or "\r" in value:
        raise UserError("文件夹路径无效")
    if not (ntpath.isabs(value) or os.path.isabs(value)):
        raise UserError("文件夹必须使用绝对路径，如 D:\\Projects\\Example")
    return value


def validate_node_type(value):
    if value not in NODE_TYPES or not isinstance(value, str):
        raise UserError("模块类型必须是根模块、普通模块或叶子模块")
    return value


def inferred_type(parent, path, has_children=False):
    """Compatibility for v1 data and backups: keep linked category nodes intact."""
    if parent is None:
        return "root"
    return "group" if has_children or not path else "leaf"


def validate_structure(node_type, parent, path, *, existing=None):
    """New/edited nodes obey strict types. Unchanged legacy category paths survive updates."""
    if (node_type == "root") != (parent is None):
        raise UserError("根模块只能位于顶层；普通模块和叶子模块必须设置上级模块")
    if node_type == "leaf" and not path:
        raise UserError("叶子模块必须关联一个实际文件夹")
    if node_type != "leaf" and path:
        legacy_unchanged = (existing is not None and existing["node_type"] == node_type
                            and existing["folder_path"] == path)
        if not legacy_unchanged:
            raise UserError("根模块和普通模块仅用于分类，请在叶子模块关联文件夹")


def validate_parent(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise UserError("上级模块 ID 无效")
    return value


class Store:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    folder_path TEXT,
                    node_type TEXT NOT NULL DEFAULT 'group',
                    favorite INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id,sort_order,id);
            """)
            cols = {row["name"] for row in db.execute("PRAGMA table_info(nodes)")}
            if "node_type" not in cols:
                db.execute("ALTER TABLE nodes ADD COLUMN node_type TEXT NOT NULL DEFAULT 'group'")
                # Existing records may have category paths: keep every path untouched.
                db.execute("""UPDATE nodes SET node_type = CASE
                    WHEN parent_id IS NULL THEN 'root'
                    WHEN EXISTS(SELECT 1 FROM nodes AS child WHERE child.parent_id = nodes.id) THEN 'group'
                    WHEN folder_path IS NOT NULL AND folder_path != '' THEN 'leaf'
                    ELSE 'group' END""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=15)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("PRAGMA busy_timeout = 15000")
            with db:
                yield db
        finally:
            db.close()

    def all(self):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM nodes ORDER BY sort_order,id").fetchall()
            return [dict(r) | {"favorite": bool(r["favorite"])} for r in rows]

    @staticmethod
    def require(db, node_id):
        row = db.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
        if row is None:
            raise UserError("模块不存在或已被删除")
        return row

    @staticmethod
    def check_parent(db, node_id, parent_id):
        if parent_id is None:
            return
        target = Store.require(db, parent_id)
        if target["node_type"] == "leaf":
            raise UserError("叶子模块不能拥有子模块，请选择根模块或普通模块作为上级")
        current = parent_id
        while current is not None:
            if current == node_id:
                raise UserError("不能把模块移动到自身或其下级模块中")
            row = db.execute("SELECT parent_id FROM nodes WHERE id=?", (current,)).fetchone()
            current = row["parent_id"] if row else None

    @staticmethod
    def next_order(db, parent_id):
        return db.execute("SELECT COALESCE(MAX(sort_order),-1)+1 FROM nodes WHERE parent_id IS ?", (parent_id,)).fetchone()[0]

    def create(self, data):
        title = validate_title(data.get("title"))
        path = validate_path(data.get("folder_path"))
        parent = validate_parent(data.get("parent_id"))
        node_type = validate_node_type(data.get("node_type", inferred_type(parent, path)))
        validate_structure(node_type, parent, path)
        stamp = now()
        with self.connect() as db:
            self.check_parent(db, None, parent)
            result = db.execute("""INSERT INTO nodes
                (parent_id,title,folder_path,node_type,favorite,sort_order,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?)""", (parent,title,path,node_type,
                int(bool(data.get("favorite",False))),self.next_order(db,parent),stamp,stamp))
            return result.lastrowid

    def update(self, node_id, data):
        with self.connect() as db:
            original = self.require(db, node_id)
            title = validate_title(data.get("title", original["title"]))
            path = validate_path(data.get("folder_path", original["folder_path"]))
            parent = validate_parent(data.get("parent_id", original["parent_id"]))
            node_type = validate_node_type(data.get("node_type", original["node_type"]))
            validate_structure(node_type, parent, path, existing=original)
            self.check_parent(db, node_id, parent)
            if node_type == "leaf" and db.execute(
                "SELECT 1 FROM nodes WHERE parent_id=? LIMIT 1", (node_id,)).fetchone():
                raise UserError("该模块已有子模块，不能直接改为叶子模块，请先移动或移除下级模块")
            favorite = bool(data.get("favorite", original["favorite"]))
            order = original["sort_order"] if parent == original["parent_id"] else self.next_order(db,parent)
            db.execute("""UPDATE nodes SET parent_id=?,title=?,folder_path=?,node_type=?,
                favorite=?,sort_order=?,updated_at=? WHERE id=?""",
                (parent,title,path,node_type,int(favorite),order,now(),node_id))

    def delete(self, node_id):
        with self.connect() as db:
            self.require(db,node_id)
            db.execute("DELETE FROM nodes WHERE id=?",(node_id,))

    def order(self, parent_id, node_ids):
        parent_id = validate_parent(parent_id)
        if not isinstance(node_ids,list) or any(type(i)!=int or i<1 for i in node_ids):
            raise UserError("排序参数无效")
        with self.connect() as db:
            current = [r[0] for r in db.execute("SELECT id FROM nodes WHERE parent_id IS ?",(parent_id,))]
            if len(current)!=len(node_ids) or set(current)!=set(node_ids):
                raise UserError("排序列表必须包含该层的所有模块")
            for position, node_id in enumerate(node_ids):
                db.execute("UPDATE nodes SET sort_order=?,updated_at=? WHERE id=?",(position,now(),node_id))

    def export(self):
        return {"format":"FolderHub","version":2,"exported_at":now(),"nodes":self.all()}

    def import_backup(self, payload):
        if (not isinstance(payload,dict) or payload.get("format")!="FolderHub"
            or payload.get("version") not in (1,2) or not isinstance(payload.get("nodes"),list)):
            raise UserError("不是兼容的 FolderHub 备份文件")
        raw = payload["nodes"]
        if len(raw)>20000:
            raise UserError("备份包含过多模块")
        prepared = {}
        for n in raw:
            if not isinstance(n,dict) or type(n.get("id"))!=int or n["id"]<1 or n["id"] in prepared:
                raise UserError("备份存在重复或非法 ID")
            parent = validate_parent(n.get("parent_id"))
            order = n.get("sort_order",0)
            if type(order)!=int or order<0:
                raise UserError("备份排序字段无效")
            prepared[n["id"]] = {
                "parent": parent, "title": validate_title(n.get("title")),
                "path": validate_path(n.get("folder_path")),
                "favorite": int(bool(n.get("favorite",False))), "order": order,
                "type": n.get("node_type") if payload["version"]==2 else None
            }
        child_parents = {n["parent"] for n in prepared.values() if n["parent"] is not None}
        for node_id, n in prepared.items():
            if n["parent"] is not None and n["parent"] not in prepared:
                raise UserError("备份引用了不存在的上级模块")
            checked = set()
            curr = node_id
            while curr is not None:
                if curr in checked:
                    raise UserError("备份存在循环嵌套")
                checked.add(curr)
                curr = prepared[curr]["parent"]
        for node_id, n in prepared.items():
            if n["type"] is None and payload["version"]==1:
                n["type"] = inferred_type(n["parent"],n["path"],node_id in child_parents)
            n["type"] = validate_node_type(n["type"])
            # Imported legacy categories may retain linked paths, without changing real files.
            validate_structure(n["type"],n["parent"],n["path"],existing={
                "node_type":n["type"], "folder_path":n["path"]})
            if n["type"]=="leaf" and node_id in child_parents:
                raise UserError("备份中叶子模块包含子模块")
            if n["parent"] is not None and prepared[n["parent"]]["type"]=="leaf":
                raise UserError("备份中叶子模块不能作为上级")
        with self.connect() as db:
            db.execute("DELETE FROM nodes")
            pending = dict(prepared)
            while pending:
                progressed = False
                for node_id, n in list(pending.items()):
                    if n["parent"] is None or n["parent"] not in pending:
                        db.execute("""INSERT INTO nodes
                            (id,parent_id,title,folder_path,node_type,favorite,sort_order,created_at,updated_at)
                            VALUES (?,?,?,?,?,?,?,?,?)""", (node_id,n["parent"],n["title"],
                            n["path"],n["type"],n["favorite"],n["order"],now(),now()))
                        del pending[node_id]
                        progressed = True
                if not progressed:
                    raise UserError("备份结构无效")


def open_in_explorer(path):
    if os.name != "nt":
        raise UserError("调用系统资源管理器仅支持 Windows；当前操作系统不是 Windows")
    if not os.path.isdir(path):
        raise UserError("文件夹不存在或当前无法访问，请检查路径和磁盘连接")
    explorer_window.open_and_focus(path)  # Best effort foreground; never pins Always-on-top.


def choose_folder():
    if os.name != "nt":
        raise UserError("选择文件夹窗口目前仅支持 Windows")
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        raise UserError("当前 Python 缺少 tkinter，请手动填写文件夹路径")
    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
        return filedialog.askdirectory(parent=root,title="选择要关联的文件夹",mustexist=True) or None
    finally:
        root.destroy()


class FolderServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    def __init__(self, address, store):
        super().__init__(address, Handler)
        self.store = store
        self.token = secrets.token_urlsafe(32)


class Handler(BaseHTTPRequestHandler):
    server: FolderServer
    def log_message(self, fmt, *args):
        print("[FolderHub]", fmt % args)

    def reply(self, status, data, content_type="application/json; charset=utf-8", disposition=None):
        payload = json.dumps(data,ensure_ascii=False).encode("utf-8") if content_type.startswith("application/json") else data
        self.send_response(status)
        self.send_header("Content-Type",content_type)
        self.send_header("Content-Length",str(len(payload)))
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("X-Frame-Options", "DENY")
        if disposition:
            self.send_header("Content-Disposition",disposition)
        self.end_headers()
        self.wfile.write(payload)

    def check_host(self):
        host = self.headers.get("Host", "")
        return host in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")

    def authorized(self):
        origin = self.headers.get("Origin")
        if origin:
            u = urlparse(origin)
            if u.scheme!="http" or u.netloc not in (f"127.0.0.1:{self.server.server_port}",f"localhost:{self.server.server_port}"):
                return False
        return secrets.compare_digest(self.headers.get("X-FolderHub-Token", ""), self.server.token)

    def request_json(self):
        if self.headers.get("Content-Type","").split(";")[0].lower()!="application/json":
            raise UserError("请求必须是 JSON")
        try:
            length=int(self.headers.get("Content-Length","0"))
        except ValueError:
            raise UserError("请求长度无效")
        if length<0 or length>MAX_REQUEST:
            raise UserError("请求数据过大")
        try:
            payload=json.loads(self.rfile.read(length))
        except (ValueError,UnicodeError):
            raise UserError("JSON 格式不正确")
        if not isinstance(payload,dict):
            raise UserError("JSON 请求必须是对象")
        return payload

    def serve(self, method):
        if not self.check_host():
            return self.reply(403,{"error":"访问地址不被允许"})
        path = urlparse(self.path).path
        if method!="GET" and not self.authorized():
            return self.reply(403,{"error":"安全验证失败，请刷新页面"})
        try:
            if method=="GET" and path=="/api/config":
                return self.reply(200,{"token":self.server.token,"platform":sys.platform})
            if method=="GET" and path=="/api/startup":
                return self.reply(200,startup.status())
            if method=="POST" and path=="/api/startup":
                data=self.request_json()
                return self.reply(200,startup.set_enabled(data.get("enabled")))
            if method=="GET" and path=="/api/nodes":
                return self.reply(200,{"nodes":self.server.store.all()})
            if method=="GET" and path=="/api/export":
                return self.reply(200,self.server.store.export(),disposition='attachment; filename="folderhub-backup.json"')
            if method=="POST" and path=="/api/nodes":
                node_id=self.server.store.create(self.request_json())
                return self.reply(201,{"id":node_id})
            if method=="POST" and path=="/api/order":
                data=self.request_json()
                self.server.store.order(data.get("parent_id"),data.get("ids"))
                return self.reply(200,{"ok":True})
            if method=="POST" and path=="/api/import":
                self.server.store.import_backup(self.request_json())
                return self.reply(200,{"ok":True})
            if method=="POST" and path=="/api/pick-folder":
                self.request_json()
                return self.reply(200,{"path":choose_folder()})
            if path.startswith("/api/nodes/"):
                pieces=path.strip("/").split("/")
                if len(pieces) not in (3,4) or not pieces[2].isdigit():
                    return self.reply(404,{"error":"未知接口"})
                node_id=int(pieces[2])
                if method=="PATCH" and len(pieces)==3:
                    self.server.store.update(node_id,self.request_json())
                    return self.reply(200,{"ok":True})
                if method=="DELETE" and len(pieces)==3:
                    self.server.store.delete(node_id)
                    return self.reply(200,{"ok":True})
                if method=="POST" and len(pieces)==4 and pieces[3]=="open":
                    self.request_json()
                    with self.server.store.connect() as db:
                        node=self.server.store.require(db,node_id)
                        folder=node["folder_path"]
                    if not folder:
                        raise UserError("这个模块尚未绑定文件夹")
                    open_in_explorer(folder)
                    return self.reply(200,{"ok":True})
            if method=="GET" and path in ("/","/index.html","/app.js","/styles.css","/favicon.svg"):
                name="index.html" if path=="/" else path[1:]
                types={"index.html":"text/html; charset=utf-8","app.js":"application/javascript; charset=utf-8","styles.css":"text/css; charset=utf-8","favicon.svg":"image/svg+xml"}
                return self.reply(200,(STATIC / name).read_bytes(),types[name])
            return self.reply(404,{"error":"页面或接口不存在"})
        except (UserError, startup.StartupError) as exc:
            return self.reply(400,{"error":str(exc)})
        except (OSError,sqlite3.Error) as exc:
            print("[FolderHub] error:",repr(exc),file=sys.stderr)
            return self.reply(500,{"error":"操作失败，请检查文件夹权限或数据库状态"})

    def do_GET(self): self.serve("GET")
    def do_POST(self): self.serve("POST")
    def do_PATCH(self): self.serve("PATCH")
    def do_DELETE(self): self.serve("DELETE")


def data_directory():
    override=os.environ.get("FOLDERHUB_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if os.name=="nt":
        return Path(os.environ.get("LOCALAPPDATA",str(Path.home()))) / "DailyToolsSet" / "FolderHub"
    return Path.home()/".local"/"share"/"DailyToolsSet"/"FolderHub"


def main():
    parser=argparse.ArgumentParser(description="FolderHub 本地文件导航工具")
    parser.add_argument("--port",type=int,default=8765,help="本地端口，默认 8765")
    parser.add_argument("--no-browser",action="store_true",help="不自动打开浏览器")
    parser.add_argument("--data-dir",type=Path,default=data_directory(),help="数据库目录")
    parser.add_argument("--startup",choices=("enable","disable","status"),
                        help="管理当前用户的 Windows 登录自启动设置，不启动网页服务")
    args=parser.parse_args()
    if not 0<=args.port<=65535:
        parser.error("端口范围必须在 0 到 65535 之间")
    if args.startup:
        try:
            if args.startup == "status":
                result = startup.status()
            else:
                result = startup.set_enabled(args.startup == "enable")
            print(json.dumps(result,ensure_ascii=False))
            return 0
        except (startup.StartupError, OSError) as exc:
            print("操作自启动失败：",exc,file=sys.stderr)
            return 1
    store=Store(args.data_dir/"folderhub.db")
    try:
        server=FolderServer(("127.0.0.1",args.port),store)
    except OSError as exc:
        print(f"启动失败：端口 {args.port} 已被占用或不可用：{exc}",file=sys.stderr)
        return 1
    url=f"http://127.0.0.1:{server.server_port}/"
    print("FolderHub 已启动：",url,flush=True)
    print("数据库位置：",store.db_path,flush=True)
    print("按 Ctrl+C 退出服务。",flush=True)
    if not args.no_browser:
        from threading import Timer
        Timer(0.6,lambda:webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止 FolderHub")
    finally:
        server.server_close()
    return 0


if __name__=="__main__":
    sys.exit(main())
