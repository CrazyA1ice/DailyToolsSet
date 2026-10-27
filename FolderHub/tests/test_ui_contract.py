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

    def test_root_only_home_and_custom_covers(self):
        self.assertNotIn('class="summary"',self.html)
        self.assertLess(self.html.index('id="search"'), self.html.index('class="content"'))
        self.assertIn('display=children(null);sectionTitle="根模块";',self.js)
        self.assertIn('display=searchAll(searching)',self.js)
        for piece in ('card-cover', 'cover-image','cover-emoji','showCovers','data-show-covers'):
            self.assertIn(piece,self.js+self.css)

    def test_drag_sort_is_sibling_only_and_accessible(self):
        self.assertIn('function reorderIds(ids, moved, anchor, after=false)', self.js)
        self.assertIn('function canReorder()', self.js)
        self.assertIn('dragstart', self.js)
        self.assertIn('dragover', self.js)
        self.assertIn('dragend', self.js)
        self.assertIn('ArrowUp', self.js)
        self.assertIn('ArrowDown', self.js)
        self.assertIn('"/api/order"', self.js)
        self.assertIn('data-drag=', self.js)
        self.assertIn('drag-before', self.css)
        self.assertIn('drag-after', self.css)

    def test_bulk_and_context_menu_contracts(self):
        for name in ("selectModeBtn","bulkBar","bulkCount","bulkSelectAll",
                     "bulkFavorite","bulkUnfavorite","bulkDelete","bulkCancel",
                     "cardContextMenu"):
            self.assertIn(f'id="{name}"',self.html)
            self.assertIn(name,self.js)
        self.assertIn('function batchAction(action)',self.js)
        self.assertIn('"/api/batch"',self.js)
        self.assertIn('function openCardMenu(id,x,y)',self.js)
        self.assertIn('contextmenu',self.js)
        self.assertIn('data-action=\"menu\"',self.js)
        self.assertIn('aria-pressed',self.js)
        self.assertIn('role="menu"',self.html)
        self.assertIn('.entry-card.is-selected',self.css)
        self.assertIn('.card-context-menu',self.css)

    def test_recycle_bin_and_undo_interface(self):
        for item in ("trashCount", "specialNav", "entries"):
            self.assertIn(f'id="{item}"', self.html)
        self.assertIn('data-view="trash"', self.html)
        self.assertIn('function restoreTrash(id)', self.js)
        self.assertIn('function purgeTrash(id)', self.js)
        self.assertIn('function trashCard(item)', self.js)
        self.assertIn('"/api/trash"', self.js)
        self.assertIn('data-trash-action="restore"', self.js)
        self.assertIn('data-trash-action="purge"', self.js)
        self.assertIn('toast-action', self.js)
        self.assertIn('.trash-card', self.css)
        self.assertIn('.toast-action', self.css)

    def test_cover_personalization_options(self):
        for key in ('coverHeight', 'coverFit'):
            self.assertIn(f'data-pref="{key}"', self.html)
            self.assertIn(f'root.dataset.{key}=', self.js)
        self.assertIn('data-cover-fit="contain"', self.css)
        self.assertIn('data-cover-height="tall"', self.css)

    def test_portable_backup_settings_controls(self):
        for control in ('settingsTabStorage', 'settingsPanelStorage', 'storageMetrics',
                        'storageRefresh', 'storageBackup', 'storageWarning'):
            self.assertIn(f'id="{control}"', self.html)
        for control in ('storageMetrics', 'storageRefresh', 'storageBackup', 'storageWarning'):
            self.assertIn(control, self.js)
        self.assertIn('["launch","appearance","storage","paths"]', self.js)
        self.assertIn('function refreshStorage()', self.js)
        self.assertIn('function downloadPortableBackup()', self.js)
        self.assertIn('/api/storage/status', self.js)
        self.assertIn('/api/storage/backup', self.js)
        self.assertIn('.storage-metrics', self.css)

    def test_path_migration_settings(self):
        for control in ('settingsTabPaths', 'settingsPanelPaths', 'pathPrefixFrom',
                        'pathPrefixTo', 'pathPreview', 'pathApply', 'pathCheck',
                        'pathHealthSummary', 'pathPlanSummary'):
            self.assertIn(f'id="{control}"', self.html)
        for control in ('pathPrefixFrom', 'pathPrefixTo', 'pathPreview', 'pathApply',
                        'pathCheck', 'pathHealthSummary', 'pathPlanSummary'):
            self.assertIn(control, self.js)
        for endpoint in ('/api/paths/check', '/api/paths/preview', '/api/paths/apply'):
            self.assertIn(endpoint, self.js)
        self.assertIn('.path-results', self.css)

    def test_recent_usage_nav_and_controls(self):
        self.assertIn('data-view="recent"',self.html)
        self.assertIn('id="recentCount"',self.html)
        self.assertIn('"/api/recent"',self.js)
        self.assertIn('function clearRecentHistory()',self.js)
        self.assertIn('data-action="clear-recent"',self.js)
        self.assertIn('state.recent.map(item=>byId(item.node_id)).filter(Boolean)',self.js)
        self.assertIn('display=children(null);sectionTitle="根模块";',self.js)

    def test_search_keyboard_and_recent_pin_contracts(self):
        self.assertIn('aria-keyshortcuts="Control+K Meta+K"', self.html)
        self.assertIn('state.searchKeyboardIndex',self.js)
        self.assertIn('e.key==="ArrowDown"',self.js)
        self.assertIn('"ArrowUp"',self.js)
        self.assertIn('e.key==="Enter"',self.js)
        self.assertIn('function toggleRecentPin(id)',self.js)
        self.assertIn('/api/recent/pin',self.js)
        self.assertIn('keyboard-active',self.css)
        self.assertIn('data-action="pin"',self.js)
        self.assertIn('display=children(null);sectionTitle="根模块";',self.js)

    def test_list_view_spacing_and_density_controls(self):
        # Covers in compact mode must never use the grid-mode negative margin.
        self.assertIn('data-pref="listDensity" data-value="compact"',self.html)
        self.assertIn('data-pref="listDensity" data-value="normal"',self.html)
        self.assertIn('data-pref="listDensity" data-value="relaxed"',self.html)
        self.assertIn('root.dataset.listDensity=preferences.listDensity',self.js)
        self.assertIn('html[data-density="compact"] .entries.list .entry-card .card-cover',self.css)
        self.assertIn('html[data-density="compact"] .entries.list .entry-card {',self.css)
        self.assertIn('margin:0;',self.css.split(
            'html[data-density="compact"] .entries.list .entry-card .card-cover {',1)[1].split('}',1)[0])
        self.assertIn('padding:var(--list-pad-y) var(--list-pad-x)',self.css)
        self.assertIn('data-action="edit"',self.css)
        self.assertIn('focus-within',self.css)
        self.assertGreater(self.css.index('/* V2.6 - List view layout.'),
                           self.css.index('margin-left:-15px;margin-right:-15px'))

    def test_list_metadata_copy_path_and_no_action_overlap(self):
        # Search lineage and visit counts should survive in list view.
        self.assertIn('const contextText=state.search?',self.js)
        self.assertIn('const listContext=state.layout==="list" && contextText?',self.js)
        self.assertIn('${listContext}</button>',self.js)
        self.assertIn('state.layout!=="list" && recentText',self.js)
        self.assertIn('data-action="copy-path"',self.js)
        self.assertIn('async function copyFolderPath(id)',self.js)
        self.assertIn('case "copy-path":await copyFolderPath(id);break;',self.js)
        self.assertIn('.entries.list .card-primary .list-card-context',self.css)
        self.assertIn('@media(max-width:1200px)',self.css)
        responsive=self.css.split('/* V2.7 — Show search breadcrumb/recent history',1)[1]
        self.assertIn('grid-row:2;',responsive)
        self.assertIn('grid-row:3;',responsive)
        self.assertIn('flex-wrap:wrap;',responsive)

    def test_presentation_settings_are_portable(self):
        self.assertIn('async function loadProjectSettings()', self.js)
        self.assertIn('async function persistProjectSettings()', self.js)
        self.assertIn('"/api/preferences"', self.js)
        self.assertIn('projectSettingsReady', self.js)
        self.assertIn('initialExpanded', self.js)
        self.assertIn('state.layout', self.js)
        self.assertIn('function legacyBrowserSettings()', self.js)
        self.assertNotIn('localStorage.setItem(', self.js)

    def test_customization_options_and_persistence(self):
        for pref in ("font", "density", "sidebar", "columns", "accent", "coverHeight", "coverFit"):
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
