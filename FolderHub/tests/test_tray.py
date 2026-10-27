"""Regression tests for the Windows-only tray controller's portable service lifecycle.

These tests run on Windows and non-Windows without creating an actual tray icon.
The Win32 tray UI itself still requires manual testing in Windows Explorer.
"""
from pathlib import Path
import json
from io import BytesIO
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

    def test_quick_entry_limits_and_does_not_mutate_input(self):
        nodes=[{'id':i,'title':str(i),'folder_path':'C:/X','favorite':i<=12}
               for i in range(1,41)]
        items=tray.build_quick_entries(nodes,[{'node_id':i} for i in range(1,41)],
                                      [{'name':str(i)} for i in range(20)])
        commands=[x for x in items if x['kind']!='heading']
        self.assertEqual(len(commands),24)
        self.assertEqual([x['target'] for x in commands[:8]],list(range(1,9)))
        self.assertEqual([x['target'] for x in commands[8:16]],list(range(9,17)))
        self.assertEqual(len([x for x in commands if x['kind']=='workspace']),8)
        self.assertEqual(nodes[0]['title'],'1')
        self.assertLessEqual(len(tray.safe_menu_title('&'*200)),47)

    def test_hotkey_register_unregister_and_collision_tolerance(self):
        window=tray.WindowsTray.__new__(tray.WindowsTray)
        window.hwnd=123
        window.user32=MagicMock()
        window.user32.RegisterHotKey.return_value=1
        window.hotkey_registered=False
        window._register_hotkey()
        window.user32.RegisterHotKey.assert_called_once_with(
            123,tray.HOTKEY_ID,tray.HOTKEY_MODIFIERS|window.MOD_NOREPEAT,
            tray.HOTKEY_VK)
        window._remove_hotkey()
        window.user32.UnregisterHotKey.assert_called_once_with(123,tray.HOTKEY_ID)
        self.assertFalse(window.hotkey_registered)
        window.user32.RegisterHotKey.return_value=0
        window._register_hotkey()
        self.assertFalse(window.hotkey_registered)
        window._remove_hotkey()
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

    def test_external_service_snapshot_uses_read_only_endpoints(self):
        svc=tray.ServiceController(port=9876)
        svc.external=True
        calls=[]
        def fake(url,timeout=None):
            calls.append(url)
            if url.endswith('/api/nodes'):
                return BytesIO(b'{"nodes":[{"id":5,"title":"Folder","folder_path":"C:/Folder","favorite":true}]}')
            if url.endswith('/api/recent'):
                return BytesIO(b'{"items":[]}')
            if url.endswith('/api/preferences'):
                return BytesIO(b'{"settings":{"workspaces":[{"name":"Lab"}]}}')
            raise AssertionError(url)
        with patch.object(tray,'server_is_folderhub',return_value=True), \
             patch.object(tray,'urlopen',side_effect=fake):
            items=svc.quick_entries()
        self.assertEqual([x['kind'] for x in items],
                         ['heading','folder','heading','workspace'])
        self.assertEqual(len(calls),3)
        self.assertTrue(all('/api/' in url for url in calls))
