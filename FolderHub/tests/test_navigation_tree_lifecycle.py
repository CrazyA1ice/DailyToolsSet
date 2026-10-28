"""Run the optional dependency-free Node sidebar lifecycle regression."""
from pathlib import Path
import shutil
import subprocess
import unittest


SCRIPT = Path(__file__).with_name("test_navigation_tree_lifecycle.cjs")


class NavigationTreeLifecycleTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is optional; static contracts still run")
    def test_sidebar_highlight_expand_refresh_and_focus(self):
        result = subprocess.run(
            ["node", str(SCRIPT)],
            cwd=SCRIPT.parent.parent,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)
        self.assertIn("400 view changes passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
