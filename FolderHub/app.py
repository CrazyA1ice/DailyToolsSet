"""FolderHub: a dependency-free, local-only Windows folder dashboard."""
from __future__ import annotations

import argparse
import zipfile
import base64
import binascii
from contextlib import contextmanager
import json
import hashlib
import re
import shutil
import tempfile
from threading import RLock
from time import monotonic
import ntpath
import os
from pathlib import Path
import secrets
import sqlite3
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import webbrowser
import startup
import explorer_window
import path_management
from preferences_store import PreferencesStore, PreferenceError

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
PORTABLE_DATA = ROOT / "data"
PORTABLE_UPLOADS = ROOT / "uploads"
IMAGE_FILE_RE = re.compile(r"^uploads/[a-f0-9]{64}\.(png|jpg|webp)$")
IMAGE_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
MAX_REQUEST = 2 * 1024 * 1024
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_REQUEST = 3 * 1024 * 1024
MAX_IMPORT_REQUEST = 32 * 1024 * 1024
ALLOWED_ICONS = frozenset(("folder", "book", "code", "chart", "database", "image", "briefcase", "school", "music", "video", "archive", "star"))
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


def validate_icon(value):
    if not isinstance(value, str) or value not in ALLOWED_ICONS:
        raise UserError("请选择支持的模块图标")
    return value


def decode_image(data_url):
    """Decode an uploaded data URL, refusing SVG or mismatched MIME signatures."""
    if not isinstance(data_url, str) or len(data_url) > MAX_IMAGE_REQUEST:
        raise UserError("图片过大，单张图片不能超过 2 MB")
    if ";base64," not in data_url:
        raise UserError("图片必须是 PNG、JPG 或 WebP")
    header, encoded = data_url.split(",", 1)
    expected = {"data:image/png;base64": ("image/png", b"\x89PNG\r\n\x1a\n"),
                "data:image/jpeg;base64": ("image/jpeg", b"\xff\xd8\xff"),
                "data:image/webp;base64": ("image/webp", b"RIFF")}
    if header not in expected or not encoded or len(encoded) > ((MAX_IMAGE_BYTES+2)//3)*4 + 4:
        raise UserError("图片格式不支持或文件过大（支持 PNG/JPG/WebP，最多 2 MB）")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise UserError("图片编码无效")
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise UserError("图片必须小于或等于 2 MB")
    mime, signature = expected[header]
    if not raw.startswith(signature) or (mime == "image/webp" and (len(raw) < 12 or raw[8:12] != b"WEBP")):
        raise UserError("图片内容与文件格式不匹配")
    if mime == "image/png" and (len(raw) < 24 or raw[12:16] != b"IHDR"):
        raise UserError("PNG 图片文件不完整")
    return mime, raw


def encode_image(mime, raw):
    return {"mime": mime, "base64": base64.b64encode(raw).decode("ascii")}


def decode_backup_image(value):
    if not isinstance(value, dict) or not isinstance(value.get("mime"), str) or not isinstance(value.get("base64"), str):
        raise UserError("备份中的图片记录无效")
    return decode_image(f"data:{value['mime']};base64,{value['base64']}")


def validate_parent(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise UserError("上级模块 ID 无效")
    return value


class Store:
    def __init__(self, db_path: Path, uploads_dir: Path | None = None):
        self.db_path = Path(db_path)
        self.preferences = PreferencesStore(self.db_path.parent / "preferences.json")
        self.uploads_dir = Path(uploads_dir) if uploads_dir is not None else self.db_path.parent / "uploads"
        self._image_lock = RLock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    folder_path TEXT,
                    node_type TEXT NOT NULL DEFAULT 'group',
                    icon TEXT NOT NULL DEFAULT 'folder',
                    favorite INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id,sort_order,id);
                CREATE TABLE IF NOT EXISTS node_visits (
                    node_id INTEGER PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
                    open_count INTEGER NOT NULL DEFAULT 0,
                    last_opened_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_node_visits_time ON node_visits(last_opened_at DESC);
                CREATE TABLE IF NOT EXISTS node_images (
                    node_id INTEGER PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
                    mime_type TEXT NOT NULL,
                    image_path TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trash_batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deleted_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    selected_count INTEGER NOT NULL,
                    item_count INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trash_nodes (
                    batch_id INTEGER NOT NULL REFERENCES trash_batches(id) ON DELETE CASCADE,
                    node_id INTEGER NOT NULL,
                    parent_id INTEGER,
                    title TEXT NOT NULL,
                    folder_path TEXT,
                    node_type TEXT NOT NULL,
                    icon TEXT NOT NULL,
                    favorite INTEGER NOT NULL,
                    sort_order INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    image_mime TEXT,
                    image_path TEXT,
                    PRIMARY KEY(batch_id,node_id)
                );
            """)
            # Schema changes are transactional, including old node-type migration.
            db.execute("BEGIN IMMEDIATE")
            cols = {row["name"] for row in db.execute("PRAGMA table_info(nodes)")}
            if "icon" not in cols:
                db.execute("ALTER TABLE nodes ADD COLUMN icon TEXT NOT NULL DEFAULT 'folder'")
            if "node_type" not in cols:
                db.execute("ALTER TABLE nodes ADD COLUMN node_type TEXT NOT NULL DEFAULT 'group'")
                # Existing records may have category paths: keep every path untouched.
                db.execute("""UPDATE nodes SET node_type = CASE
                    WHEN parent_id IS NULL THEN 'root'
                    WHEN EXISTS(SELECT 1 FROM nodes AS child WHERE child.parent_id = nodes.id) THEN 'group'
                    WHEN folder_path IS NOT NULL AND folder_path != '' THEN 'leaf'
                    ELSE 'group' END""")
            self._migrate_legacy_images(db)

    def _image_file(self, relative_path):
        """Only allow content-addressed filenames under the configured uploads directory."""
        if not isinstance(relative_path, str) or not IMAGE_FILE_RE.fullmatch(relative_path):
            raise UserError("数据库中的图片相对路径无效")
        return self.uploads_dir / relative_path.split("/", 1)[1]

    def _write_image(self, mime, raw):
        """Write the cover before storing its relative name in SQLite; never trust user filenames."""
        if mime not in IMAGE_EXT or len(raw) > MAX_IMAGE_BYTES:
            raise UserError("不支持的图片格式或图片过大")
        relative = f"uploads/{hashlib.sha256(raw).hexdigest()}.{IMAGE_EXT[mime]}"
        target = self._image_file(relative)
        if not target.is_file():
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(dir=self.uploads_dir, prefix=".incoming-", delete=False) as output:
                    temp_path = Path(output.name)
                    output.write(raw)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temp_path, target)
            finally:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)
        return relative

    def _read_image(self, relative_path):
        try:
            return self._image_file(relative_path).read_bytes()
        except FileNotFoundError:
            raise UserError("封面图片文件丢失，请检查 uploads 文件夹或恢复完整备份")

    def _migrate_legacy_images(self, db):
        """Convert BOTH active and recycle-bin image BLOBs to relative file paths.

        The entire database schema change is transactional. Previously written file
        objects remain harmless if the database transaction is rolled back.
        """
        image_columns = {r["name"] for r in db.execute("PRAGMA table_info(node_images)")}
        if "image_data" in image_columns:
            db.execute("""CREATE TABLE node_images_portable (
                node_id INTEGER PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
                mime_type TEXT NOT NULL, image_path TEXT NOT NULL, updated_at TEXT NOT NULL)""")
            for row in db.execute("SELECT node_id,mime_type,image_data,updated_at FROM node_images"):
                filename = self._write_image(row["mime_type"], bytes(row["image_data"]))
                db.execute("INSERT INTO node_images_portable VALUES(?,?,?,?)",
                           (row["node_id"], row["mime_type"], filename, row["updated_at"]))
            db.execute("DROP TABLE node_images")
            db.execute("ALTER TABLE node_images_portable RENAME TO node_images")
        trash_columns = {r["name"] for r in db.execute("PRAGMA table_info(trash_nodes)")}
        if "image_data" in trash_columns:
            db.execute("""CREATE TABLE trash_nodes_portable (
                batch_id INTEGER NOT NULL REFERENCES trash_batches(id) ON DELETE CASCADE,
                node_id INTEGER NOT NULL, parent_id INTEGER, title TEXT NOT NULL,
                folder_path TEXT, node_type TEXT NOT NULL, icon TEXT NOT NULL,
                favorite INTEGER NOT NULL, sort_order INTEGER NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                image_mime TEXT, image_path TEXT, PRIMARY KEY(batch_id,node_id))""")
            for row in db.execute("SELECT * FROM trash_nodes"):
                image_path = (self._write_image(row["image_mime"],bytes(row["image_data"]))
                              if row["image_data"] is not None else None)
                db.execute("""INSERT INTO trash_nodes_portable VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                           (row["batch_id"],row["node_id"],row["parent_id"],row["title"],
                            row["folder_path"],row["node_type"],row["icon"],row["favorite"],
                            row["sort_order"],row["created_at"],row["updated_at"],
                            row["image_mime"],image_path))
            db.execute("DROP TABLE trash_nodes")
            db.execute("ALTER TABLE trash_nodes_portable RENAME TO trash_nodes")

    def _prune_unreferenced_images(self):
        """Remove unreferenced generated covers, preserving all trash references."""
        with self._image_lock:
            with self.connect() as db:
                referenced = {r[0] for r in db.execute("SELECT image_path FROM node_images")}
                referenced.update(r[0] for r in db.execute(
                    "SELECT image_path FROM trash_nodes WHERE image_path IS NOT NULL"))
            for path in self.uploads_dir.iterdir():
                if path.is_file() and IMAGE_FILE_RE.fullmatch("uploads/" + path.name):
                    if "uploads/" + path.name not in referenced:
                        path.unlink(missing_ok=True)

    def storage_status(self):
        """Read-only inventory of the portable database and its referenced covers."""
        with self._image_lock:
            with self.connect() as db:
                active = db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
                trash = db.execute("SELECT COUNT(*) FROM trash_batches").fetchone()[0]
                refs = {r[0] for r in db.execute("SELECT image_path FROM node_images")}
                refs.update(r[0] for r in db.execute(
                    "SELECT image_path FROM trash_nodes WHERE image_path IS NOT NULL"))
            missing = 0
            for relative in refs:
                try:
                    if not self._image_file(relative).is_file():
                        missing += 1
                except UserError:
                    missing += 1
            unused = sum(1 for f in self.uploads_dir.iterdir()
                         if f.is_file() and IMAGE_FILE_RE.fullmatch("uploads/" + f.name)
                         and "uploads/" + f.name not in refs)
            return {"active_modules": active, "trash_batches": trash,
                    "cover_files": len(refs), "missing_covers": missing,
                    "unused_covers": unused, "backup_ready": missing == 0}

    def make_portable_backup(self):
        """Build a complete consistent SQLite + cover ZIP; caller removes returned temp path.

        SQLite's backup API makes a coherent database snapshot even in WAL mode.
        Hold the cover lock until all referenced assets are packed, preventing
        concurrent cover replacement/pruning during the backup.
        """
        with self._image_lock:
            db_temp = None
            zip_temp = None
            try:
                fd, name = tempfile.mkstemp(dir=self.db_path.parent, prefix=".backup-db-", suffix=".db")
                os.close(fd)
                db_temp = Path(name)
                with self.connect() as source, sqlite3.connect(db_temp) as target:
                    source.backup(target)
                with sqlite3.connect(db_temp) as snapshot:
                    refs = {row[0] for row in snapshot.execute("SELECT image_path FROM node_images")}
                    refs.update(row[0] for row in snapshot.execute(
                        "SELECT image_path FROM trash_nodes WHERE image_path IS NOT NULL"))
                    if snapshot.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise UserError("数据库完整性检查未通过，已取消完整备份")
                covers = []
                for relative in sorted(refs):
                    path = self._image_file(relative)
                    if not path.is_file():
                        raise UserError("有封面文件丢失，请先检查 data/ 和 uploads/，未生成不完整的备份")
                    covers.append((relative, path))
                fd, name = tempfile.mkstemp(dir=self.db_path.parent, prefix=".backup-zip-", suffix=".zip")
                os.close(fd)
                zip_temp = Path(name)
                with zipfile.ZipFile(zip_temp, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                    archive.write(db_temp, 'data/folderhub.db')
                    archive.writestr('data/preferences.json', self.preferences.snapshot_bytes())
                    for relative, path in covers:
                        archive.write(path, relative)
                    archive.writestr('README-RESTORE.txt',
                        'FolderHub complete portable backup.\n'
                        'Stop FolderHub before restoring.\n'
                        'Extract the data/ and uploads/ folders into FolderHub/.\n'
                        'data/preferences.json stores the theme, layout and sidebar preferences.\n'
                        'Make a copy of existing data/ and uploads/ BEFORE replacing them.\n'
                        'Folder paths stored in the database may not exist on another PC.\n')
                return zip_temp
            except Exception:
                if zip_temp is not None:
                    zip_temp.unlink(missing_ok=True)
                raise
            finally:
                if db_temp is not None:
                    db_temp.unlink(missing_ok=True)

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

    def recent(self, limit=30):
        """Most recently opened linked folders. No original files are inspected."""
        if type(limit) is not int or not 1 <= limit <= 200:
            raise UserError("最近使用记录数量无效")
        with self.connect() as db:
            return [dict(row) for row in db.execute("""
                SELECT v.node_id, v.open_count, v.last_opened_at
                FROM node_visits AS v
                JOIN nodes AS n ON n.id = v.node_id
                WHERE n.folder_path IS NOT NULL AND n.folder_path != ''
                ORDER BY v.last_opened_at DESC, v.node_id DESC
                LIMIT ?""", (limit,))]

    def record_open(self, node_id):
        """Record only successful Explorer launches; deleted nodes cascade automatically."""
        with self.connect() as db:
            self.require(db, node_id)
            db.execute("""
                INSERT INTO node_visits(node_id,open_count,last_opened_at)
                VALUES(?,1,?)
                ON CONFLICT(node_id) DO UPDATE SET
                    open_count = MIN(node_visits.open_count + 1, 2147483647),
                    last_opened_at = excluded.last_opened_at
            """, (node_id, datetime.now(timezone.utc).isoformat(timespec="microseconds")))
            # Bound history size even when thousands of distinct folders are opened.
            db.execute("""
                DELETE FROM node_visits WHERE node_id IN (
                    SELECT node_id FROM node_visits
                    ORDER BY last_opened_at DESC, node_id DESC LIMIT -1 OFFSET 200
                )""")

    def clear_recent(self):
        """Clear usage history only; never alter modules or real folders."""
        with self.connect() as db:
            result = db.execute("DELETE FROM node_visits")
        return {"ok": True, "cleared": result.rowcount}

    def all(self):
        with self.connect() as db:
            rows = db.execute("""SELECT n.*, (i.node_id IS NOT NULL) AS has_image
                FROM nodes n LEFT JOIN node_images i ON i.node_id = n.id
                ORDER BY n.sort_order,n.id""").fetchall()
            return [dict(r) | {"favorite": bool(r["favorite"]), "has_image": bool(r["has_image"])} for r in rows]

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
        icon = validate_icon(data.get("icon", "folder"))
        validate_structure(node_type, parent, path)
        stamp = now()
        with self.connect() as db:
            self.check_parent(db, None, parent)
            result = db.execute("""INSERT INTO nodes
                (parent_id,title,folder_path,node_type,icon,favorite,sort_order,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?)""", (parent,title,path,node_type,icon,
                int(bool(data.get("favorite",False))),self.next_order(db,parent),stamp,stamp))
            return result.lastrowid

    def update(self, node_id, data):
        with self.connect() as db:
            original = self.require(db, node_id)
            title = validate_title(data.get("title", original["title"]))
            path = validate_path(data.get("folder_path", original["folder_path"]))
            parent = validate_parent(data.get("parent_id", original["parent_id"]))
            node_type = validate_node_type(data.get("node_type", original["node_type"]))
            icon = validate_icon(data.get("icon", original["icon"]))
            validate_structure(node_type, parent, path, existing=original)
            self.check_parent(db, node_id, parent)
            if node_type == "leaf" and db.execute(
                "SELECT 1 FROM nodes WHERE parent_id=? LIMIT 1", (node_id,)).fetchone():
                raise UserError("该模块已有子模块，不能直接改为叶子模块，请先移动或移除下级模块")
            favorite = bool(data.get("favorite", original["favorite"]))
            order = original["sort_order"] if parent == original["parent_id"] else self.next_order(db,parent)
            db.execute("""UPDATE nodes SET parent_id=?,title=?,folder_path=?,node_type=?,
                icon=?,favorite=?,sort_order=?,updated_at=? WHERE id=?""",
                (parent,title,path,node_type,icon,int(favorite),order,now(),node_id))

    @staticmethod
    def _trash_delete(db, ids):
        """Snapshot a complete subtree before deleting its navigation records.

        Metadata and relative image paths move atomically into a local recycle bin.
        No real directories or files are changed.
        """
        selected = list(ids)
        rows = db.execute("SELECT * FROM nodes ORDER BY sort_order,id").fetchall()
        by_id = {row["id"]: row for row in rows}
        if not selected or any(node_id not in by_id for node_id in selected):
            raise UserError("所选模块有部分不存在，请刷新页面后重试")
        branches = {}
        for row in rows:
            branches.setdefault(row["parent_id"], []).append(row["id"])
        to_delete = set(selected)
        queue = list(selected)
        for node_id in queue:
            for child_id in branches.get(node_id, ()):
                if child_id not in to_delete:
                    to_delete.add(child_id)
                    queue.append(child_id)
        title = by_id[selected[0]]["title"]
        if len(selected) > 1:
            title += f" 等 {len(selected)} 项"
        result = db.execute("""INSERT INTO trash_batches(deleted_at,title,selected_count,item_count)
            VALUES(?,?,?,?)""", (now(),title,len(selected),len(to_delete)))
        batch_id = result.lastrowid
        ordered_ids = sorted(to_delete)
        for start in range(0, len(ordered_ids), 300):
            chunk = ordered_ids[start:start+300]
            placeholder = ",".join("?" for _ in chunk)
            backups = db.execute(f"""SELECT n.*, i.mime_type AS image_mime,
                i.image_path AS image_path FROM nodes n
                LEFT JOIN node_images i ON i.node_id=n.id
                WHERE n.id IN ({placeholder})""", chunk).fetchall()
            db.executemany("""INSERT INTO trash_nodes(batch_id,node_id,parent_id,title,folder_path,
                node_type,icon,favorite,sort_order,created_at,updated_at,image_mime,image_path)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", [
                (batch_id,r["id"],r["parent_id"],r["title"],r["folder_path"],r["node_type"],
                 r["icon"],r["favorite"],r["sort_order"],r["created_at"],r["updated_at"],
                 r["image_mime"],r["image_path"]) for r in backups])
        # Only delete the selected roots: SQLite cascades to descendants/images.
        # Existing children have already been captured in trash_nodes above.
        for start in range(0, len(selected), 300):
            chunk = selected[start:start+300]
            placeholder = ",".join("?" for _ in chunk)
            db.execute(f"DELETE FROM nodes WHERE id IN ({placeholder})", chunk)
        return {"ok": True, "trash_id": batch_id, "deleted": len(to_delete)}

    def delete(self, node_id):
        with self.connect() as db:
            self.require(db,node_id)
            return self._trash_delete(db, [node_id])

    def trash_list(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("""SELECT id,deleted_at,title,
                selected_count,item_count FROM trash_batches ORDER BY id DESC LIMIT 200""")]

    def restore_trash(self, trash_id):
        if type(trash_id) is not int or trash_id < 1:
            raise UserError("回收站记录 ID 无效")
        with self.connect() as db:
            batch = db.execute("SELECT id FROM trash_batches WHERE id=?",(trash_id,)).fetchone()
            if batch is None:
                raise UserError("回收站记录不存在或已经恢复")
            rows = db.execute("SELECT * FROM trash_nodes WHERE batch_id=?",(trash_id,)).fetchall()
            pending = {r["node_id"]: r for r in rows}
            if not pending:
                raise UserError("回收站记录为空")
            for node_id,row in pending.items():
                if db.execute("SELECT 1 FROM nodes WHERE id=?", (node_id,)).fetchone():
                    raise UserError("原模块 ID 已被其他模块使用，无法直接恢复。请先备份现有数据")
                parent = row["parent_id"]
                if parent is not None and parent not in pending:
                    old_parent = db.execute("SELECT node_type FROM nodes WHERE id=?",(parent,)).fetchone()
                    if old_parent is None:
                        raise UserError("上级模块已不在目录中，请先恢复所属上级模块")
                    if old_parent["node_type"] == "leaf":
                        raise UserError("上级模块现在是叶子模块，不能恢复子模块")
            while pending:
                ready = [n for n,r in pending.items() if r["parent_id"] not in pending]
                if not ready:
                    raise UserError("回收站层级数据无效")
                for node_id in ready:
                    row = pending.pop(node_id)
                    db.execute("""INSERT INTO nodes(id,parent_id,title,folder_path,node_type,icon,
                        favorite,sort_order,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (row["node_id"],row["parent_id"],row["title"],row["folder_path"],
                         row["node_type"],row["icon"],row["favorite"],row["sort_order"],
                         row["created_at"],row["updated_at"]))
                    if row["image_mime"] is not None:
                        self._read_image(row["image_path"])  # Refuse to restore a broken cover.
                        db.execute("""INSERT INTO node_images(node_id,mime_type,image_path,updated_at)
                            VALUES(?,?,?,?)""",(node_id,row["image_mime"],row["image_path"],now()))
            db.execute("DELETE FROM trash_batches WHERE id=?",(trash_id,))
            return {"ok": True, "restored": len(rows)}

    def purge_trash(self, trash_id):
        if type(trash_id) is not int or trash_id < 1:
            raise UserError("回收站记录 ID 无效")
        with self._image_lock:
            with self.connect() as db:
                result = db.execute("DELETE FROM trash_batches WHERE id=?",(trash_id,))
                if not result.rowcount:
                    raise UserError("回收站记录不存在或已清除")
            self._prune_unreferenced_images()
        return {"ok": True}

    def batch(self, action, ids):
        """Atomic changes to navigation entries only; never touches actual folders."""
        if action not in ("favorite", "unfavorite", "delete"):
            raise UserError("不支持的批量操作")
        if (not isinstance(ids, list) or not 1 <= len(ids) <= 200
                or any(type(n) is not int or n < 1 for n in ids)
                or len(set(ids)) != len(ids)):
            raise UserError("请选择 1 至 200 个不重复的有效模块")
        placeholders = ",".join("?" for _ in ids)
        with self.connect() as db:
            found = {r[0] for r in db.execute(
                f"SELECT id FROM nodes WHERE id IN ({placeholders})", ids)}
            if found != set(ids):
                raise UserError("所选模块有部分不存在，请刷新页面后重试")
            if action == "delete":
                result = self._trash_delete(db, ids)
                return {**result, "changed": len(ids)}
            value = 1 if action == "favorite" else 0
            db.execute(f"UPDATE nodes SET favorite=?,updated_at=? WHERE id IN ({placeholders})",
                       [value, now(), *ids])
        return {"ok": True, "changed": len(ids)}

    def save_image(self, node_id, data_url):
        mime, raw = decode_image(data_url)
        with self._image_lock:
            with self.connect() as db:
                self.require(db, node_id)
                relative_path = self._write_image(mime, raw)
                db.execute("""INSERT INTO node_images(node_id,mime_type,image_path,updated_at) VALUES (?,?,?,?)
                    ON CONFLICT(node_id) DO UPDATE SET mime_type=excluded.mime_type,
                    image_path=excluded.image_path,updated_at=excluded.updated_at""",
                    (node_id,mime,relative_path,now()))
                db.execute("UPDATE nodes SET updated_at=? WHERE id=?",(now(),node_id))
            self._prune_unreferenced_images()

    def remove_image(self, node_id):
        with self._image_lock:
            with self.connect() as db:
                self.require(db, node_id)
                db.execute("DELETE FROM node_images WHERE node_id=?",(node_id,))
                db.execute("UPDATE nodes SET updated_at=? WHERE id=?",(now(),node_id))
            self._prune_unreferenced_images()

    def get_image(self, node_id):
        with self._image_lock:
            with self.connect() as db:
                row=db.execute("SELECT mime_type,image_path FROM node_images WHERE node_id=?",(node_id,)).fetchone()
            return (row["mime_type"], self._read_image(row["image_path"])) if row else None

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
        with self._image_lock:
            with self.connect() as db:
                images={str(row["node_id"]):encode_image(row["mime_type"],self._read_image(row["image_path"]))
                    for row in db.execute("SELECT node_id,mime_type,image_path FROM node_images")}
            return {"format":"FolderHub","version":3,"exported_at":now(),"nodes":self.all(),"images":images}

    def import_backup(self, payload):
        if (not isinstance(payload,dict) or payload.get("format")!="FolderHub"
            or payload.get("version") not in (1,2,3) or not isinstance(payload.get("nodes"),list)):
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
                "type": n.get("node_type") if payload["version"] in (2,3) else None,
                "icon": validate_icon(n.get("icon", "folder"))
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
        backup_images={}
        if payload["version"] == 3:
            incoming=payload.get("images",{})
            if not isinstance(incoming,dict) or len(incoming)>len(prepared):
                raise UserError("备份图片列表无效")
            for key,value in incoming.items():
                if not isinstance(key,str) or not key.isascii() or not key.isdecimal() or int(key) not in prepared:
                    raise UserError("备份图片引用了不存在的模块")
                backup_images[int(key)] = decode_backup_image(value)
        # Validate and write all cover files before touching existing navigation data.
        with self._image_lock:
            prepared_images = {node_id:(mime,self._write_image(mime, raw))
                               for node_id,(mime,raw) in backup_images.items()}
            self._apply_import(prepared, prepared_images)
            self._prune_unreferenced_images()

    def _apply_import(self, prepared, prepared_images):
        with self.connect() as db:
            db.execute("DELETE FROM nodes")
            pending = dict(prepared)
            while pending:
                progressed = False
                for node_id, n in list(pending.items()):
                    if n["parent"] is None or n["parent"] not in pending:
                        db.execute("""INSERT INTO nodes
                            (id,parent_id,title,folder_path,node_type,icon,favorite,sort_order,created_at,updated_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?)""", (node_id,n["parent"],n["title"],
                            n["path"],n["type"],n["icon"],n["favorite"],n["order"],now(),now()))
                        del pending[node_id]
                        progressed = True
                if not progressed:
                    raise UserError("备份结构无效")
            for node_id, (mime, image_path) in prepared_images.items():
                db.execute("INSERT INTO node_images(node_id,mime_type,image_path,updated_at) VALUES (?,?,?,?)",
                           (node_id,mime,image_path,now()))


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
        self._backup_ticket_lock = RLock()
        self._backup_ticket = None
        self._backup_ticket_until = 0.0


    def issue_backup_ticket(self):
        """Short-lived one-time download authorization, issued by a CSRF-protected POST."""
        with self._backup_ticket_lock:
            self._backup_ticket = secrets.token_urlsafe(32)
            self._backup_ticket_until = monotonic() + 60
            return self._backup_ticket

    def consume_backup_ticket(self, supplied):
        with self._backup_ticket_lock:
            valid = (isinstance(supplied, str) and self._backup_ticket is not None
                     and monotonic() <= self._backup_ticket_until
                     and secrets.compare_digest(supplied, self._backup_ticket))
            if valid:
                self._backup_ticket = None  # replay and cross-site GET requests cannot download
                self._backup_ticket_until = 0.0
            return valid


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

    def reply_download(self, source_path):
        """Stream a temporary ZIP to the browser without loading it all into RAM."""
        source_path = Path(source_path)
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", 'attachment; filename="folderhub-portable-backup.zip"')
        self.send_header("Content-Length", str(source_path.stat().st_size))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        with source_path.open("rb") as source:
            shutil.copyfileobj(source, self.wfile, length=1024 * 1024)

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

    def request_json(self, limit=MAX_REQUEST):
        if self.headers.get("Content-Type","").split(";")[0].lower()!="application/json":
            raise UserError("请求必须是 JSON")
        try:
            length=int(self.headers.get("Content-Length","0"))
        except ValueError:
            raise UserError("请求长度无效")
        if length<0 or length>limit:
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
            if path=="/api/preferences":
                if method=="GET":
                    return self.reply(200,self.server.store.preferences.get())
                if method in ("PUT","POST"):
                    data=self.request_json(128 * 1024)
                    result=self.server.store.preferences.save(
                        data.get("settings"),only_if_missing=method=="POST")
                    return self.reply(200,result)
                return self.reply(405,{"error":"不支持的请求方法"})
            if method=="GET" and path=="/api/startup":
                return self.reply(200,startup.status())
            if method=="POST" and path=="/api/startup":
                data=self.request_json()
                return self.reply(200,startup.set_enabled(data.get("enabled")))
            if method=="GET" and path=="/api/storage/status":
                return self.reply(200,self.server.store.storage_status())
            if method=="POST" and path=="/api/storage/backup-ticket":
                self.request_json()
                return self.reply(200,{"ticket":self.server.issue_backup_ticket()})
            if method=="GET" and path=="/api/storage/backup":
                tickets = parse_qs(urlparse(self.path).query).get("ticket", [])
                if len(tickets)!=1 or not self.server.consume_backup_ticket(tickets[0]):
                    return self.reply(403,{"error":"请从 FolderHub 设置页重新点击完整备份"})
                filename = self.server.store.make_portable_backup()
                try:
                    return self.reply_download(filename)
                finally:
                    filename.unlink(missing_ok=True)
            if method=="GET" and path=="/api/nodes":
                return self.reply(200,{"nodes":self.server.store.all()})
            if path=="/api/recent":
                if method=="GET":
                    return self.reply(200,{"items":self.server.store.recent()})
                if method=="DELETE":
                    self.request_json()
                    return self.reply(200,self.server.store.clear_recent())
                return self.reply(405,{"error":"不支持的请求方法"})
            if method=="GET" and path=="/api/trash":
                return self.reply(200,{"items":self.server.store.trash_list()})
            if path.startswith("/api/trash/"):
                parts=path.strip("/").split("/")
                if len(parts)==4 and parts[2].isdigit() and parts[3]=="restore" and method=="POST":
                    self.request_json()
                    return self.reply(200,self.server.store.restore_trash(int(parts[2])))
                if len(parts)==3 and parts[2].isdigit() and method=="DELETE":
                    self.request_json()
                    return self.reply(200,self.server.store.purge_trash(int(parts[2])))
                return self.reply(404,{"error":"未知接口"})
            if method=="GET" and path=="/api/export":
                return self.reply(200,self.server.store.export(),disposition='attachment; filename="folderhub-backup.json"')
            if method=="POST" and path=="/api/nodes":
                node_id=self.server.store.create(self.request_json())
                return self.reply(201,{"id":node_id})
            if method=="POST" and path=="/api/batch":
                data=self.request_json()
                return self.reply(200,self.server.store.batch(data.get("action"),data.get("ids")))
            if method=="POST" and path=="/api/order":
                data=self.request_json()
                self.server.store.order(data.get("parent_id"),data.get("ids"))
                return self.reply(200,{"ok":True})
            if method=="POST" and path=="/api/import":
                self.server.store.import_backup(self.request_json(MAX_IMPORT_REQUEST))
                return self.reply(200,{"ok":True})
            if method=="POST" and path=="/api/paths/check":
                self.request_json()
                return self.reply(200,path_management.check_health(self.server.store))
            if method=="POST" and path=="/api/paths/preview":
                data=self.request_json()
                return self.reply(200,path_management.preview(self.server.store,data.get("source"),data.get("target")))
            if method=="POST" and path=="/api/paths/apply":
                data=self.request_json()
                return self.reply(200,path_management.apply(self.server.store,data.get("source"),data.get("target"),data.get("fingerprint")))
            if method=="POST" and path=="/api/pick-folder":
                self.request_json()
                return self.reply(200,{"path":choose_folder()})
            if path.startswith("/api/nodes/"):
                pieces=path.strip("/").split("/")
                if len(pieces) not in (3,4) or not pieces[2].isdigit():
                    return self.reply(404,{"error":"未知接口"})
                node_id=int(pieces[2])
                if method=="GET" and len(pieces)==4 and pieces[3]=="image":
                    img=self.server.store.get_image(node_id)
                    if img is None:
                        return self.reply(404,{"error":"没有设置模块图片"})
                    return self.reply(200,img[1],content_type=img[0])
                if method=="POST" and len(pieces)==4 and pieces[3]=="image":
                    data=self.request_json(MAX_IMAGE_REQUEST)
                    self.server.store.save_image(node_id,data.get("data_url"))
                    return self.reply(200,{"ok":True})
                if method=="DELETE" and len(pieces)==4 and pieces[3]=="image":
                    self.request_json()
                    self.server.store.remove_image(node_id)
                    return self.reply(200,{"ok":True})
                if method=="PATCH" and len(pieces)==3:
                    self.server.store.update(node_id,self.request_json())
                    return self.reply(200,{"ok":True})
                if method=="DELETE" and len(pieces)==3:
                    return self.reply(200,self.server.store.delete(node_id))
                if method=="POST" and len(pieces)==4 and pieces[3]=="open":
                    self.request_json()
                    with self.server.store.connect() as db:
                        node=self.server.store.require(db,node_id)
                        folder=node["folder_path"]
                    if not folder:
                        raise UserError("这个模块尚未绑定文件夹")
                    open_in_explorer(folder)
                    # The folder was handed to Explorer; a history-write failure must
                    # not incorrectly tell the user that opening itself failed.
                    try:
                        self.server.store.record_open(node_id)
                    except sqlite3.Error as exc:
                        print("[FolderHub] usage history could not be saved:",repr(exc),file=sys.stderr)
                    return self.reply(200,{"ok":True})
            if method=="GET" and path in ("/","/index.html","/app.js","/styles.css","/favicon.svg"):
                name="index.html" if path=="/" else path[1:]
                types={"index.html":"text/html; charset=utf-8","app.js":"application/javascript; charset=utf-8","styles.css":"text/css; charset=utf-8","favicon.svg":"image/svg+xml"}
                return self.reply(200,(STATIC / name).read_bytes(),types[name])
            return self.reply(404,{"error":"页面或接口不存在"})
        except (UserError, PreferenceError, startup.StartupError, path_management.PathRuleError) as exc:
            return self.reply(400,{"error":str(exc)})
        except (OSError,sqlite3.Error) as exc:
            print("[FolderHub] error:",repr(exc),file=sys.stderr)
            return self.reply(500,{"error":"操作失败，请检查文件夹权限或数据库状态"})

    def do_GET(self): self.serve("GET")
    def do_POST(self): self.serve("POST")
    def do_PUT(self): self.serve("PUT")
    def do_PATCH(self): self.serve("PATCH")
    def do_DELETE(self): self.serve("DELETE")


def data_directory():
    """New default: portable local data, next to source code."""
    override = os.environ.get("FOLDERHUB_DATA_DIR")
    return Path(override).expanduser() if override else PORTABLE_DATA


def legacy_data_directory():
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "DailyToolsSet" / "FolderHub"
    return Path.home() / ".local" / "share" / "DailyToolsSet" / "FolderHub"


def migrate_legacy_database(destination_dir: Path, source_dir: Path | None = None):
    """One-time, non-destructive copy from old AppData to portable data/.

    SQLite's backup API includes committed WAL changes. Never overwrite an existing
    destination and never remove the original database.
    """
    source = Path(source_dir) if source_dir is not None else legacy_data_directory()
    old = source / "folderhub.db"
    new = Path(destination_dir) / "folderhub.db"
    if new.exists() or not old.is_file() or old.resolve() == new.resolve():
        return False
    new.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=new.parent,prefix=".migrate-",suffix=".db",delete=False) as tmp:
            temporary = Path(tmp.name)
        # Open in read-only mode: the source is retained intact for rollback.
        uri = old.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as source_db, sqlite3.connect(temporary) as dest_db:
            source_db.backup(dest_db)
            if dest_db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise UserError("旧数据库完整性检查失败，迁移已中止")
        if new.exists():
            return False
        os.replace(temporary,new)
        temporary = None
        return True
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
    # Explicit custom data locations are never silently populated from AppData.
    default_location = not os.environ.get("FOLDERHUB_DATA_DIR") and args.data_dir.resolve()==PORTABLE_DATA.resolve()
    if default_location and migrate_legacy_database(args.data_dir):
        print("旧版 AppData 数据库已安全复制到项目 data/；原数据库保留不动", flush=True)
    uploads = PORTABLE_UPLOADS if default_location else args.data_dir / "uploads"
    store=Store(args.data_dir/"folderhub.db", uploads_dir=uploads)
    try:
        server=FolderServer(("127.0.0.1",args.port),store)
    except OSError as exc:
        print(f"启动失败：端口 {args.port} 已被占用或不可用：{exc}",file=sys.stderr)
        return 1
    url=f"http://127.0.0.1:{server.server_port}/"
    print("FolderHub 已启动：",url,flush=True)
    print("数据库位置：",store.db_path,flush=True)
    print("图片文件夹：",store.uploads_dir,flush=True)
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
