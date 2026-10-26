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
        for control in ("sidebarToggle", "themeOptions", "showCoversToggle", "resetAppearance", "sectionHeading",
                        "entryIcon", "entryCoverFile", "pickCover", "removeCover", "entryCoverPreview",
                        "search", "entries", "treeNav", "newBtn", "entryForm"):
            self.assertIn(control, parser.ids)
            self.assertIn(control, self.js)

    def test_home_is_root_only_with_search_in_header(self):
        self.assertNotIn('id="pageTitle"', self.html)
        self.assertNotIn('class="intro"', self.html)
        self.assertNotIn('class="summary"', self.html)
        self.assertNotIn('id="nodeCount"', self.html)
        self.assertLess(self.html.index('id="search"'), self.html.index('<div class="content">'))
        self.assertIn('display=children(null);sectionTitle="根模块";', self.js)
        self.assertIn('$("#sectionHeading").hidden=state.view==="all"&&!searching;', self.js)
        self.assertIn('display=searchAll(searching)', self.js)
        self.assertNotIn('showIntroToggle', self.js)
        self.assertNotIn('showMetricsToggle', self.js)

    def test_root_only_home_and_custom_covers(self):
        self.assertNotIn('class="summary"',self.html)
        self.assertLess(self.html.index('id="search"'), self.html.index('class="content"'))
        self.assertIn('display=children(null);sectionTitle="根模块";',self.js)
        self.assertIn('display=searchAll(searching)',self.js)
        for piece in ('card-cover', 'cover-image','cover-emoji','showCovers','data-show-covers'):
            self.assertIn(piece,self.js+self.css)

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
