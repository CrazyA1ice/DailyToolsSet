"""Static regression checks for the dependency-free admin interface."""
from html.parser import HTMLParser
from pathlib import Path
import unittest

STATIC = Path(__file__).resolve().parents[1] / "static"


class IdCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if "id" in d:
            self.ids.append(d["id"])


class AdminUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (STATIC / "index.html").read_text(encoding="utf-8")
        cls.js = (STATIC / "app.js").read_text(encoding="utf-8")
        cls.css = (STATIC / "styles.css").read_text(encoding="utf-8")

    def test_controls_have_unique_ids_and_matching_scripts(self):
        parser = IdCollector()
        parser.feed(self.html)
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        for control in ("sidebarToggle", "themeOptions", "showIntroToggle", "showMetricsToggle",
                        "resetAppearance",
                        "search", "entries", "treeNav", "newBtn", "entryForm"):
            self.assertIn(control, parser.ids)
            self.assertIn(control, self.js)

    def test_customization_options_and_persistence(self):
        for pref in ("font", "density", "sidebar", "columns", "accent"):
            self.assertIn(f'data-pref="{pref}"', self.html)
        for theme in ("cloud", "midnight", "forest", "aurora", "sand", "graphite", "system"):
            self.assertIn(f'id:"{theme}"', self.js)
        self.assertIn("settingsTabAppearance", self.html)
        self.assertIn("settingsTabLaunch", self.html)
        self.assertIn("[data-settings-tab]", self.js)
        self.assertIn("folderhub.appearance", self.js)
        self.assertIn("data-sidebar-collapsed", self.css)
        self.assertIn("data-density", self.css)
        self.assertIn("data-columns", self.css)


if __name__ == "__main__":
    unittest.main()
