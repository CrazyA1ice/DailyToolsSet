"""Run the real Everything async UI regression when optional Node.js exists."""
from pathlib import Path
import shutil
import subprocess
import unittest


SCRIPT = Path(__file__).with_name("test_everything_ui_lifecycle.cjs")


class EverythingUiLifecycleTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is optional; static UI contracts still run")
    def test_search_cancellation_and_late_responses(self):
        completed = subprocess.run(
            ["node", str(SCRIPT)],
            cwd=SCRIPT.parent.parent,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(completed.returncode, 0,
                         completed.stdout + "\n" + completed.stderr)
        self.assertIn("4 request paths passed", completed.stdout)


if __name__ == "__main__":
    unittest.main()
