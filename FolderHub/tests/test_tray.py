"""Regression tests for the Windows-only tray controller's portable service lifecycle.

These tests run on Windows and non-Windows without creating an actual tray icon.
The Win32 tray UI itself still requires manual testing in Windows Explorer.
"""
from pathlib import Path
import json
import sys
import tempfile
from unittest import TestCase
from unittest.mock import patch
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
