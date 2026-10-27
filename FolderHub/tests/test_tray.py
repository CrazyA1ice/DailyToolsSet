"""Regression tests for the Windows-only tray controller's portable service lifecycle.

These tests run on Windows and non-Windows without creating an actual tray icon.
The Win32 tray UI itself still requires manual testing in Windows Explorer.
"""
from pathlib import Path
import json
from io import BytesIO
import base64
import subprocess
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch, MagicMock
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tray
import startup


class TrayServiceTests(TestCase):

    def test_owned_server_can_start_restart_and_stop_cleanly(self):
        with tempfile.TemporaryDirectory() as directory:
            svc = tray.ServiceController(port=0, data_dir=Path(directory))
            try:
                svc.start()
                self.assertIsNotNone(svc.server)
                self.assertEqual(svc.status, "运行中")
                with urlopen(svc.url, timeout=3) as response:
                    self.assertEqual(response.status, 200)
                svc.restart()
                self.assertEqual(svc.status, "运行中")
                self.assertIsNotNone(svc.server)
                with urlopen(svc.url, timeout=3) as response:
                    self.assertEqual(response.status, 200)
            finally:
                svc.stop()
            self.assertIsNone(svc.server)
            self.assertIsNone(svc.thread)
            self.assertEqual(svc.status, "已停止")

    def test_external_running_service_is_never_stopped_by_tray(self):
        svc = tray.ServiceController(port=8765)
        with patch.object(tray, "server_is_folderhub", return_value=True):
            svc.start()
        self.assertTrue(svc.external)
        self.assertIsNone(svc.server)
        with self.assertRaises(RuntimeError):
            svc.restart()
        svc.stop()
        self.assertTrue(svc.external)

    def test_startup_command_uses_pythonw_and_tray_wrapper(self):
        with (patch.object(startup, "supported", return_value=True),
              patch.object(startup.sys, "executable", "C:/Python/python.exe"),
              patch.object(startup.Path, "is_file", return_value=True)):

            command = startup.launch_command()
        self.assertIn("pythonw.exe", command)
        self.assertIn("start_silent.pyw", command)
        self.assertIn("--no-browser", command)
        self.assertNotIn("cmd.exe", command)

    def test_quick_entry_builder_filters_duplicates_and_escapes_titles(self):
        nodes=[
            {'id':1,'title':'Research & Notes','folder_path':'C:/Research','favorite':True},
            {'id':2,'title':'Old','folder_path':'C:/Old','favorite':False},
            {'id':3,'title':'Unbound','folder_path':None,'favorite':True},
            {'id':4,'title':'Folder','folder_path':'D:/Folder','favorite':False},
        ]
        items=tray.build_quick_entries(
            nodes,[{'node_id':1},{'node_id':2},{'node_id':2},
                   {'node_id':3},{'node_id':4},{'node_id':999}],
            [{'name':'论文 & 项目'},{'name':'开发'}])
        actionable=[(x['kind'],x['target']) for x in items if x['kind']!='heading']
        self.assertEqual(actionable,[
            ('folder',1),('folder',2),('folder',4),
            ('workspace','论文 & 项目'),('workspace','开发')])
        self.assertEqual(items[1]['label'],'Research && Notes')
        self.assertEqual(tray.safe_menu_title(' A\n & B '),'A && B')
        self.assertTrue(all('folder_path' not in item for item in items))

    def test_v51_quick_menu_includes_files_and_websites_without_raw_targets(self):
        nodes=[
            {"id":3,"title":"论文PDF","node_type":"leaf","folder_path":None,
             "resource_kind":"file","resource_target":r"D:\Research\paper.pdf"},
            {"id":4,"title":"项目网页","node_type":"leaf","folder_path":None,
             "resource_kind":"url","resource_target":"https://example.org/"},
            {"id":5,"title":"草稿分类","node_type":"group","folder_path":None},
            {"id":6,"title":"未设置地址","node_type":"leaf","resource_kind":"url",
             "resource_target":None},
            {"id":7,"title":"原有目录","node_type":"leaf",
             "folder_path":r"D:\Research","resource_kind":"folder"},
        ]
        entries=tray.build_quick_entries(nodes,[],[])
        actions=[item for item in entries if item["kind"]=="folder"]
        self.assertEqual([x["target"] for x in actions],[3,4,7])
        self.assertTrue(actions[0]["label"].startswith("📄 "))
        self.assertTrue(actions[1]["label"].startswith("🌐 "))
        self.assertEqual(actions[2]["label"],"原有目录")
        self.assertTrue(all("resource_target" not in item and "folder_path" not in item
                            for item in entries))
        self.assertFalse(any("https://" in item["label"] for item in entries))

    def test_v51_large_folder_library_keeps_document_and_web_shortcuts_visible(self):
        nodes=[{"id":n,"title":"Folder "+str(n),"folder_path":r"C:\Data",
                "resource_kind":"folder"} for n in range(1,101)]
        nodes.extend([
            {"id":101,"title":"Main PDF","node_type":"leaf",
             "resource_kind":"file","resource_target":r"C:\Data\report.pdf"},
            {"id":102,"title":"Notes","node_type":"leaf",
             "resource_kind":"file","resource_target":r"C:\Data\notes.txt"},
            {"id":103,"title":"Wiki","node_type":"leaf",
             "resource_kind":"url","resource_target":"https://example.org/"},
        ])
        entries=tray.build_quick_entries(nodes,[],[])
        ids=[item["target"] for item in entries if item["kind"]=="folder"]
        self.assertEqual(len(ids),8)
        self.assertEqual(ids[:5],[1,2,3,4,5])
        self.assertEqual(ids[-3:],[101,102,103])
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(len(nodes),103)

    def test_quick_entry_limits_and_does_not_mutate_input(self):
        nodes=[{'id':i,'title':str(i),'folder_path':'C:/X','favorite':i<=12}
               for i in range(1,41)]
        items=tray.build_quick_entries(nodes,[{'node_id':i} for i in range(1,41)],
                                      [{'name':str(i)} for i in range(20)])
        commands=[x for x in items if x['kind']!='heading']
        self.assertEqual(len(commands),16)
        self.assertEqual([x['target'] for x in commands[:8]],list(range(1,9)))
        self.assertEqual(len([x for x in commands if x['kind']=='workspace']),8)
        self.assertEqual(nodes[0]['title'],'1')
        self.assertLessEqual(len(tray.safe_menu_title('&'*200)),47)

    def test_hotkey_register_unregister_and_collision_tolerance(self):
        with tempfile.TemporaryDirectory() as folder:
            service=tray.ServiceController(data_dir=Path(folder))
            window=tray.WindowsTray.__new__(tray.WindowsTray)
            window.hwnd=123
            window.controller=service
            window.user32=MagicMock()
            window.user32.RegisterHotKey.return_value=1
            window.hotkey_registered=False
            window._register_hotkey()
            window.user32.RegisterHotKey.assert_called_once_with(
                123,tray.HOTKEY_ID,tray.HOTKEY_MODIFIERS|window.MOD_NOREPEAT,
                tray.HOTKEY_VK)
            window._remove_hotkey()
            window.user32.UnregisterHotKey.assert_called_once_with(123,tray.HOTKEY_ID)
            window.user32.RegisterHotKey.return_value=0
            window._register_hotkey()
            self.assertFalse(window.hotkey_registered)
            self.assertEqual(window.user32.UnregisterHotKey.call_count,1)

    def test_quick_folder_open_uses_existing_authorized_node_api(self):
        svc=tray.ServiceController(port=9876)
        called=[]
        def fake(request,timeout=None):
            called.append(request)
            if isinstance(request,str):
                self.assertEqual(request,'http://127.0.0.1:9876/api/config')
                return BytesIO(b'{"platform":"win32","token":"test-token"}')
            self.assertEqual(request.get_method(),'POST')
            self.assertEqual(request.full_url,'http://127.0.0.1:9876/api/nodes/12/open')
            self.assertEqual(request.data,b'{}')
            self.assertEqual(request.get_header('X-folderhub-token'),'test-token')
            return BytesIO(b'{"ok":true}')
        with patch.object(tray,'urlopen',side_effect=fake):
            self.assertTrue(svc.open_quick_folder(12)['ok'])
        self.assertEqual(len(called),2)
        with patch.object(tray,'urlopen') as fetch:
            with self.assertRaises(ValueError):svc.open_quick_folder('12')
            fetch.assert_not_called()

    def test_native_popup_dispatches_by_id_and_encodes_workspace_name(self):
        controller=MagicMock()
        controller.quick_entries.return_value=[
            {'kind':'heading','label':'★ 收藏'},
            {'kind':'folder','target':7,'label':'Folder'},
            {'kind':'heading','label':'▣ 工作区'},
            {'kind':'workspace','target':'论文 & 项目','label':'论文 && 项目'}]
        window=tray.WindowsTray.__new__(tray.WindowsTray)
        window.controller=controller
        window.hwnd=123
        window.user32=MagicMock()
        window.user32.CreatePopupMenu.return_value=321
        window._message=MagicMock()
        window.user32.TrackPopupMenu.return_value=tray.QUICK_ENTRY_BASE
        window._show_quick_menu()
        controller.open_quick_folder.assert_called_once_with(7)
        window.user32.TrackPopupMenu.return_value=tray.QUICK_ENTRY_BASE+1
        window._show_quick_menu()
        controller.open_quick_workspace.assert_called_once_with('论文 & 项目')
        window.user32.DestroyMenu.assert_called_with(321)
        with patch.object(tray.webbrowser,'open') as browser:
            tray.ServiceController(port=8765).open_quick_workspace('论文 & 项目')
        browser.assert_called_once_with(
            'http://127.0.0.1:8765/#workspace/%E8%AE%BA%E6%96%87%20%26%20%E9%A1%B9%E7%9B%AE')

    def test_external_service_snapshot_uses_one_bounded_read_only_endpoint(self):
        svc=tray.ServiceController(port=9876)
        svc.external=True
        calls=[]
        def fake(url,timeout=None):
            calls.append(url)
            self.assertEqual(url,'http://127.0.0.1:9876/api/quick-menu')
            return BytesIO(b'{"nodes":[{"id":5,"title":"Folder","resource_kind":"folder",'
                           b'"node_type":"leaf","has_target":true}],'
                           b'"workspaces":[{"name":"Lab"}]}')
        with patch.object(tray,'server_is_folderhub',return_value=True) as identity, \
             patch.object(tray,'urlopen',side_effect=fake):
            items=svc.quick_entries()
        self.assertEqual([x['kind'] for x in items],
                         ['heading','folder','heading','workspace'])
        self.assertEqual(len(calls),1)
        identity.assert_called_once_with(9876)

    def test_v56_tray_falls_back_only_when_old_service_has_no_menu_api(self):
        svc=tray.ServiceController(port=9876)
        svc.external=True
        calls=[]
        def fake(url,timeout=None):
            calls.append(url)
            if url.endswith('/api/quick-menu'):
                raise tray.HTTPError(url,404,'Old version',{},BytesIO(b''))
            if url.endswith('/api/nodes'):
                return BytesIO(b'{"nodes":[{"id":5,"title":"Folder",'
                               b'"folder_path":"D:/Folder"}]}')
            if url.endswith('/api/preferences'):
                return BytesIO(b'{"settings":{"workspaces":[{"name":"Lab"}]}}')
            raise AssertionError(url)
        with patch.object(tray,'server_is_folderhub',return_value=True), \
             patch.object(tray,'urlopen',side_effect=fake):
            items=svc.quick_entries()
        self.assertEqual([item['kind'] for item in items],
                         ['heading','folder','heading','workspace'])
        self.assertEqual(len(calls),3)
        # A non-404 error is not a reason to silently use stale fallback data.
        def unavailable(url,timeout=None):
            raise tray.HTTPError(url,503,'Service unavailable',{},BytesIO(b''))
        with patch.object(tray,'server_is_folderhub',return_value=True), \
             patch.object(tray,'urlopen',side_effect=unavailable):
            with self.assertRaises(tray.HTTPError):
                svc.quick_entries()

    def test_v56_bounded_quick_snapshot_equivalent_to_full_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            store=tray.app.Store(Path(directory)/'data'/'folderhub.db')
            # Bulk insert mirrors a large portable tree, without expensive
            # single-record CRUD loops or any live Explorer interactions.
            rows=[]
            for index in range(1600):
                rows.append(('Folder '+str(index),'leaf',r'D:\Data',
                             'folder',None,index%17))
            for index in range(12):
                rows.append(('PDF '+str(index),'leaf',None,'file',
                             rf'D:\Docs\report{index}.pdf',index%17))
                rows.append(('Web '+str(index),'leaf',None,'url',
                             f'https://example.org/{index}',index%17))
            rows.extend([
                ('Unlinked PDF','leaf',None,'file',None,0),
                ('Unlinked Folder','leaf',None,'folder',None,0),
                ('Group URL','group',None,'url','https://example.org',0),
            ])
            with store.connect() as db:
                db.executemany("""INSERT INTO nodes
                    (title,node_type,folder_path,resource_kind,resource_target,
                     sort_order,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,'2026-01-01','2026-01-01')""",rows)
            expected=tray.build_quick_entries(store.all(),[],[])
            with patch.object(store,'all',side_effect=AssertionError(
                    'menu snapshot must never read entire tree')):
                minimal=store.quick_menu_nodes()
            result=tray.build_quick_entries(minimal,[],[])
            self.assertEqual(result,expected)
            self.assertLessEqual(len(minimal),24)
            self.assertTrue(all(item['has_target'] is True for item in minimal))
            self.assertTrue(all('folder_path' not in item and
                                'resource_target' not in item and
                                'tags' not in item for item in minimal))
            self.assertEqual(len([item for item in result
                                  if item['kind']=='folder']),8)
            # A completed write must be visible on the very next shortcut.
            first_id=minimal[0]['id']
            with store.connect() as db:
                db.execute("UPDATE nodes SET title=? WHERE id=?",
                           ("Renamed shortcut", first_id))
            self.assertEqual(tray.build_quick_entries(
                store.quick_menu_nodes(),[],[]),
                tray.build_quick_entries(store.all(),[],[]))

    def test_owned_tray_uses_bounded_snapshot_not_store_all(self):
        with tempfile.TemporaryDirectory() as directory:
            svc=tray.ServiceController(data_dir=Path(directory),port=0)
            svc.start()
            try:
                with patch.object(svc.server.store,'all',
                                  side_effect=AssertionError('full scan')) as full:
                    entries=svc.quick_entries()
                self.assertEqual(entries,[])
                full.assert_not_called()
            finally:
                svc.stop()

    def test_windows_message_handler_routes_global_hotkey(self):
        window=tray.WindowsTray.__new__(tray.WindowsTray)
        window.hwnd=123
        window._show_quick_menu=MagicMock()
        window.user32=MagicMock()
        window.taskbar_created=99
        result=window._window_proc(123,window.WM_HOTKEY,tray.HOTKEY_ID,0)
        self.assertEqual(result,0)
        window._show_quick_menu.assert_called_once_with()
        window._show_quick_menu.reset_mock()
        window._window_proc(123,window.WM_HOTKEY,tray.HOTKEY_ID+1,0)
        window._show_quick_menu.assert_not_called()

    def test_explorer_path_probe_uses_bounded_powershell_only_for_hwnd(self):
        expected=r'C:\Work\研究'
        observed=[]
        def runner(args,**kwargs):
            observed.append((args,kwargs))
            output=base64.b64encode(expected.encode('utf-16-le'))
            return subprocess.CompletedProcess(args,0,output,b'')
        value=tray.explorer_directory_for_hwnd(123456,run=runner)
        self.assertEqual(value,expected)
        args,opts=observed[0]
        self.assertEqual(args[:3],['powershell.exe','-NoProfile','-NonInteractive'])
        self.assertEqual(args[3],'-EncodedCommand')
        script=base64.b64decode(args[4]).decode('utf-16-le')
        self.assertIn('$target = [long]123456',script)
        self.assertIn('Shell.Application',script)
        self.assertIn('Test-Path -LiteralPath',script)
        self.assertEqual(opts['timeout'],7)
        self.assertEqual(opts['stdin'],subprocess.DEVNULL)
        with self.assertRaises(ValueError):
            tray.explorer_directory_for_hwnd('123456',run=runner)
        self.assertEqual(len(observed),1)

    def test_explorer_probe_rejects_missing_virtual_and_failed_windows(self):
        for stdout,code in ((b'',0),
                            (base64.b64encode('::{virtual}'.encode('utf-16-le')),0),
                            (b'invalid base64!',0),(b'',1)):
            with self.subTest(output=stdout,code=code):
                def runner(args,**kwargs):
                    return subprocess.CompletedProcess(args,code,stdout,b'')
                with self.assertRaises(RuntimeError):
                    tray.explorer_directory_for_hwnd(55,run=runner)
        def timeout(args,**kwargs):
            raise subprocess.TimeoutExpired(args,7)
        with self.assertRaises(RuntimeError):
            tray.explorer_directory_for_hwnd(55,run=timeout)

    def test_capture_authenticates_existing_local_api_and_never_embeds_path_in_url(self):
        controller=tray.ServiceController(port=9999)
        seen=[]
        folder=r'D:\项目\机器学习'
        def mocked_urlopen(request,timeout=None):
            seen.append(request)
            if isinstance(request,str):
                self.assertEqual(request,'http://127.0.0.1:9999/api/config')
                return BytesIO(b'{"platform":"win32","token":"valid-token"}')
            self.assertEqual(request.full_url,'http://127.0.0.1:9999/api/quick-capture')
            self.assertEqual(request.get_method(),'POST')
            self.assertEqual(request.get_header('X-folderhub-token'),'valid-token')
            self.assertEqual(json.loads(request.data.decode('utf-8')),{'folder_path':folder})
            return BytesIO(b'{"id":17,"created":true}')
        with patch.object(tray,'urlopen',side_effect=mocked_urlopen):
            result=controller.capture_current_directory(folder)
        self.assertEqual(result['id'],17)
        self.assertEqual(len(seen),2)
        for invalid in ('relative/folder', None, 'D:\\bad\npath'):
            with self.subTest(path=repr(invalid)):
                with self.assertRaises(ValueError),patch.object(tray,'urlopen') as remote:
                    controller.capture_current_directory(invalid)
                    remote.assert_not_called()

    def test_capture_requires_explicit_yes_before_writing(self):
        window=tray.WindowsTray.__new__(tray.WindowsTray)
        window.hwnd=123
        window.user32=MagicMock()
        window.controller=MagicMock()
        window._message=MagicMock()
        window._capture_explorer_directory=MagicMock(return_value=r'C:\Work\Project')
        window.user32.MessageBoxW.return_value=7  # no (default)
        window._capture_current_folder()
        window.controller.capture_current_directory.assert_not_called()
        window.user32.MessageBoxW.return_value=6  # yes
        window.controller.capture_current_directory.return_value={'created':True,'id':7}
        window._capture_current_folder()
        window.controller.capture_current_directory.assert_called_once_with(r'C:\Work\Project')

    def test_single_configurable_shortcut_is_persistent(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'hotkey.json'
            self.assertEqual(tray.read_hotkey(target),tray.DEFAULT_HOTKEY)
            tray.save_hotkey(target,'Ctrl+Alt+Shift+Q')
            self.assertEqual(tray.read_hotkey(target),'Ctrl+Alt+Shift+Q')
            with self.assertRaises(ValueError):
                tray.save_hotkey(target,'Win+X')
            self.assertEqual(tray.read_hotkey(target),'Ctrl+Alt+Shift+Q')
            target.write_text('{bad}',encoding='utf-8')
            self.assertEqual(tray.read_hotkey(target),tray.DEFAULT_HOTKEY)

    def test_config_change_re_registers_only_one_global_hotkey(self):
        with tempfile.TemporaryDirectory() as folder:
            window=tray.WindowsTray.__new__(tray.WindowsTray)
            window.hwnd=123
            window.controller=tray.ServiceController(data_dir=Path(folder))
            window.user32=MagicMock()
            window.user32.RegisterHotKey.return_value=1
            window.hotkey_registered=False
            window._message=MagicMock()
            window._register_hotkey()
            window._set_hotkey('Ctrl+Alt+Shift+S')
            self.assertEqual(window.hotkey_choice,'Ctrl+Alt+Shift+S')
            self.assertEqual(tray.read_hotkey(window.controller.hotkey_file),
                             'Ctrl+Alt+Shift+S')
            self.assertEqual(window.user32.UnregisterHotKey.call_count,1)
            self.assertEqual(window.user32.RegisterHotKey.call_count,2)
            self.assertNotIn('CAPTURE_HOTKEY_ID',Path(tray.__file__).read_text(encoding='utf-8'))

    def test_single_hotkey_shows_action_list_and_capture_is_explicit(self):
        window=tray.WindowsTray.__new__(tray.WindowsTray)
        window.hwnd=123
        window.controller=MagicMock()
        window.controller.quick_entries.return_value=[]
        window.user32=MagicMock()
        window.user32.GetForegroundWindow.return_value=234
        window.user32.CreatePopupMenu.return_value=55
        window.user32.TrackPopupMenu.return_value=tray.MENU_CAPTURE
        window._capture_current_folder=MagicMock()
        window._show_quick_menu()
        window._capture_current_folder.assert_called_once_with(234)
        self.assertIn('MB_TOPMOST',Path(tray.__file__).read_text(encoding='utf-8'))
        self.assertIn('MB_SETFOREGROUND',Path(tray.__file__).read_text(encoding='utf-8'))
