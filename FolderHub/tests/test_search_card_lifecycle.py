"""Optional Node.js regression for search results and keyboard-only DOM updates."""
from pathlib import Path
import shutil
import subprocess
import unittest


SCRIPT = Path(__file__).with_name("test_search_card_lifecycle.cjs")


class SearchCardLifecycleTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is optional; the application needs no Node runtime")
    def test_search_cards_highlight_without_remounting(self):
        run = subprocess.run(
            ["node", str(SCRIPT)],
            cwd=SCRIPT.parent.parent,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(run.returncode, 0, run.stdout + "\n" + run.stderr)
        self.assertIn("400 keyboard moves", run.stdout)
        self.assertIn("indexed lineage passed", run.stdout)


if __name__ == "__main__":
    unittest.main()
