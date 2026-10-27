"""Silent launcher failure must keep diagnostic files inside FolderHub."""
from pathlib import Path
import runpy
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


LAUNCHER = Path(__file__).resolve().parents[1] / "start_silent.pyw"


class SilentLauncherTests(unittest.TestCase):
    def test_failure_log_is_portable_and_does_not_write_to_user_home(self):
        # Run a copy rather than importing the real tray or writing project data.
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "start_silent.pyw"
            script.write_bytes(LAUNCHER.read_bytes())
            fake_tray = types.ModuleType("tray")

            def fail():
                raise RuntimeError("expected simulated startup failure")

            fake_tray.main = fail
            # Avoid a real Win32 message box while still exercising __main__.
            with patch.dict(sys.modules, {"tray": fake_tray}), \
                 patch.object(sys, "platform", "test"), \
                 patch.object(sys, "path", sys.path[:]):
                with self.assertRaisesRegex(RuntimeError, "simulated startup failure"):
                    runpy.run_path(str(script), run_name="__main__")
            logfile = Path(tmp) / "data" / "startup-error.log"
            self.assertTrue(logfile.is_file())
            self.assertIn("expected simulated startup failure",
                          logfile.read_text(encoding="utf-8"))
            self.assertFalse((Path(tmp) / "FolderHub-startup-error.log").exists())


if __name__ == "__main__":
    unittest.main()
