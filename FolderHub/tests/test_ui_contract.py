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

    def test_migration_suggestion_workflow_contract(self):
        for control in ('pathSuggestedRoot','pathSuggest','pathSuggestSummary','pathSuggestList'):
            self.assertIn(f'id="{control}"',self.html)
            self.assertIn(control,self.js)
        self.assertIn('"/api/paths/suggest"',self.js)
        self.assertIn('function suggestPaths()',self.js)
        self.assertIn('function clearPathSuggestions(',self.js)
        self.assertIn('async function acceptPathSuggestion(event)',self.js)
        self.assertIn('await previewPaths(); // Read-only',self.js)
        self.assertNotIn('await applyPaths(); // Read-only',self.js)
        self.assertIn('.path-suggestion',self.css)

    def test_path_health_repair_and_export_contract(self):
        self.assertIn('id="pathExport"', self.html)
        self.assertIn('data-path-action="locate"', self.js)
        self.assertIn('data-path-action="edit"', self.js)
        self.assertIn('data-path-action="more"', self.js)
        self.assertIn('function actOnPathHealth(event)', self.js)
        self.assertIn('function exportMissingPaths()', self.js)
        self.assertIn('function csvPathCell(value)', self.js)
        self.assertIn('clearPathHealthResults("模块已更改', self.js)
        self.assertIn('$("#pathHealthList").addEventListener("click",actOnPathHealth)', self.js)
        self.assertIn('.path-row-actions', self.css)

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
        self.assertIn('${listContext}${tagChips}</button>',self.js)
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

    def test_indexed_navigation_progressive_render_and_focus(self):
        self.assertIn('function rebuildNodeIndex()',self.js)
        self.assertIn('const byId = id => nodeById.get(id)',self.js)
        self.assertIn('const children = id => childrenByParent.get(id??null) || []',self.js)
        self.assertIn('rebuildNodeIndex();',self.js)
        self.assertIn('function render(skipNav=false)',self.js)
        self.assertIn('const page=display.slice(0,state.renderLimit)',self.js)
        self.assertIn('state.visibleIds=page.map(n=>n.id)',self.js)
        self.assertIn('data-action="load-more"',self.js)
        self.assertIn('case "load-more":',self.js)
        self.assertIn('state.renderLimit=Math.ceil((state.searchKeyboardIndex+1)/100)*100',self.js)
        self.assertIn('render(true);',self.js)
        self.assertIn('.entries .load-more',self.css)
        self.assertIn('entry-card:focus-visible',self.css)
        self.assertIn('全选已显示模块',self.html)

    def test_open_folder_does_not_rebuild_the_navigation(self):
        start=self.js.index('async function openFolder(id)')
        body=self.js[start:self.js.index('\nasync function removeNode(id)',start)]
        self.assertIn('classList.add("is-opening")',body)
        self.assertIn('classList.remove("is-opening")',body)
        self.assertNotIn('state.openingIds.add(id);render()',body)
        self.assertIn('if(["recent","frequent"].includes(state.view)&&!state.search.trim())render(true)',body)

    def test_highlight_locate_and_focus_restoration(self):
        self.assertIn("function highlightSearch(value,query)",self.js)
        self.assertIn("class=\"search-hit\"",self.js)
        self.assertIn("function locateNode(id)",self.js)
        self.assertIn("data-action=\"locate\"",self.js)
        self.assertIn('case "locate":locateNode(id);break;',self.js)
        self.assertIn("const limit=Math.ceil((index+1)/100)*100",self.js)
        self.assertIn('restoreCardFocus(id,"favorite")',self.js)
        self.assertIn('restoreCardFocus(id,"pin")',self.js)
        self.assertIn(".search-hit",self.css)
        self.assertIn(".entry-card.is-located",self.css)
        self.assertIn('display=children(null);sectionTitle="根模块";',self.js)

    def test_browser_history_and_deep_link_navigation(self):
        self.assertIn('function routeFromLocation()',self.js)
        self.assertIn('function routeUrl(view,id=null)',self.js)
        self.assertIn('function navigationSnapshot()',self.js)
        self.assertIn('function rememberNavigation()',self.js)
        self.assertIn('function startBrowserNavigation()',self.js)
        self.assertIn('function restoreBrowserNavigation()',self.js)
        self.assertIn('window.addEventListener("popstate",restoreBrowserNavigation)',self.js)
        self.assertIn('startBrowserNavigation();',self.js)
        self.assertIn('window.history.pushState(',self.js)
        self.assertIn('window.history.replaceState(',self.js)
        self.assertIn('window.history.scrollRestoration="manual"',self.js)
        self.assertIn('if(view==="node"&&!byId(id)){view="all";id=null}',self.js)
        self.assertIn('if(!fromHistory)rememberNavigation()',self.js)
        self.assertIn('state.search=fromHistory&&typeof saved?.search==="string"',self.js)
        self.assertIn('render(true);rememberNavigation();',self.js)
        self.assertNotIn('encodeURIComponent(state.search)',self.js)
        self.assertIn('display=children(null);sectionTitle="根模块";',self.js)

    def test_quick_palette_navigation_and_accessibility(self):
        for item in ("quickOpenBtn","quickLayer","quickInput","quickResults","quickClose"):
            self.assertIn('id="'+item+'"',self.html)
            self.assertIn(item,self.js)
        # Descriptive help is static HTML, not a JavaScript-controlled element.
        self.assertIn('id="quickHelp"',self.html)
        self.assertIn('aria-keyshortcuts="Control+Shift+P"',self.html)
        self.assertIn('role="combobox"',self.html)
        self.assertIn('role="listbox"',self.html)
        self.assertIn('function quickCandidates(query="")',self.js)
        self.assertIn('function renderQuickPalette()',self.js)
        self.assertIn('function quickLaunch(index)',self.js)
        self.assertIn('function bindQuickPalette()',self.js)
        self.assertIn('bindQuickPalette();',self.js)
        self.assertIn('event.key==="ArrowDown"',self.js)
        self.assertIn('event.key==="Enter"',self.js)
        self.assertIn('if(quickPalette.open)return;',self.js)
        self.assertIn('const seen=new Set(),results=[];',self.js)
        self.assertIn('.quick-result.is-active',self.css)
        self.assertIn('.quick-dialog',self.css)

    def test_tags_edit_filter_and_search(self):
        for control in ("tagCount","tagFilters","entryTags"):
            self.assertIn(f'id="{control}"',self.html)
        self.assertIn('data-view="tags"',self.html)
        self.assertIn('function renderTagFilters()',self.js)
        self.assertIn('function chooseTag(tag)',self.js)
        self.assertIn('data-tag-filter=',self.js)
        self.assertIn('(node.tags||[]).join(" ").toLocaleLowerCase()',self.js)
        self.assertIn('tags:$("#entryTags").value.split(',self.js)
        self.assertIn('const label=(node.tags||[]).length?',self.js)
        self.assertIn('tag:state.view==="tags"?state.activeTag:null',self.js)
        self.assertIn('.tag-choice.active',self.css)
        self.assertIn('display=children(null);sectionTitle="根模块";',self.js)

    def test_tag_maintenance_controls_and_api_calls(self):
        self.assertIn('id="bulkTagAdd"',self.html)
        self.assertIn('id="bulkTagRemove"',self.html)
        self.assertIn('function parseBulkTags(text)',self.js)
        self.assertIn('async function batchTags(action)',self.js)
        self.assertIn('async function renameCurrentTag()',self.js)
        self.assertIn('data-tag-rename="1"',self.js)
        self.assertIn('"/api/tags/batch"',self.js)
        self.assertIn('"/api/tags/rename"',self.js)
        self.assertIn('state.activeTag=state.tagSelection.length===1?state.tagSelection[0]:null;',self.js)
        self.assertIn('bulkTagAdd","bulkTagRemove"',self.js)
        self.assertIn('.tag-filters .tag-manage',self.css)

    def test_boolean_tag_combinations_and_history(self):
        self.assertIn('function filterTaggedNodes(nodes,includes,excludes,mode="any")',self.js)
        self.assertIn('function updateTagFilterMode(mode,value)',self.js)
        self.assertIn('data-tag-match="any"',self.js)
        self.assertIn('data-tag-match="all"',self.js)
        self.assertIn('data-tag-pick="exclude"',self.js)
        self.assertIn('data-tag-clear="1"',self.js)
        self.assertIn('tagSelection:state.view==="tags"?[...state.tagSelection]:[]',self.js)
        self.assertIn('tagExcluded:state.view==="tags"?[...state.tagExcluded]:[]',self.js)
        self.assertIn('tagMatchMode:state.tagMatchMode',self.js)
        self.assertIn('filterTaggedNodes(state.nodes,state.tagSelection,state.tagExcluded,state.tagMatchMode)',self.js)
        self.assertIn('.tag-filter-toolbar',self.css)
        self.assertIn('.tag-choice.excluded',self.css)

    def test_saved_smart_views_are_portable_and_usable(self):
        self.assertIn('id="smartViewSection"',self.html)
        self.assertIn('id="smartViewNav"',self.html)
        self.assertIn('function renderSavedViews()',self.js)
        self.assertIn('function openSmartView(index)',self.js)
        self.assertIn('async function editSavedViews(action)',self.js)
        self.assertIn('data-smart-action="save"',self.js)
        self.assertIn('data-smart-action="rename"',self.js)
        self.assertIn('data-smart-action="delete"',self.js)
        self.assertIn('savedViews:state.savedViews.map',self.js)
        self.assertIn('state.savedViews=Array.isArray(saved.savedViews)',self.js)
        self.assertIn('smartView:state.view==="tags"?state.activeSmartView:null',self.js)
        self.assertIn('.saved-view-section',self.css)
        self.assertIn('display=children(null);sectionTitle="根模块";',self.js)

    def test_saved_views_survive_history_and_tag_rename(self):
        self.assertIn('const restoredSmartView=fromHistory&&view==="tags"?',self.js)
        self.assertIn('const keepTag=tag=>typeof tag==="string"',self.js)
        self.assertIn('state.activeSmartView=restoredSmartView?.name||null;',self.js)
        self.assertIn('else {renderSavedViews();renderFolderGroups()}',self.js)
        self.assertIn('const rewritten=state.savedViews.map(view=>{',self.js)
        self.assertIn('state.savedViews=rewritten;',self.js)

    def test_saved_views_keep_unassigned_tags_removable(self):
        self.assertIn('const previouslySelected=state.tagSelection.includes(tag)',self.js)
        self.assertIn('subset.push(row||[tag,0]);',self.js)

    def test_frequent_access_is_distinct_from_recent(self):
        self.assertIn('data-view="frequent"',self.html)
        self.assertIn('id="frequentCount"',self.html)
        self.assertIn('"/api/frequent"',self.js)
        self.assertIn('state.frequent=frequent.items',self.js)
        self.assertIn('state.frequent.map(item=>byId(item.node_id)).filter(Boolean)',self.js)
        self.assertIn('sectionTitle="常用文件夹 · 按累计打开次数排序"',self.js)
        self.assertIn('for(const visit of state.frequent)add(byId(visit.node_id))',self.js)
        self.assertIn('state.recent=[];state.frequent=[];',self.js)
        self.assertIn('display=children(null);sectionTitle="根模块";',self.js)

    def test_saved_folder_groups_and_result_dialog(self):
        for control in ("folderGroupSection","folderGroupNav","folderGroupCount",
                        "bulkSaveGroup","groupResultLayer","groupResultSummary",
                        "groupResultRows","groupResultClose","groupResultDone"):
            self.assertIn(f'id="{control}"',self.html)
        self.assertIn('function renderFolderGroups()',self.js)
        self.assertIn('async function saveSelectedFolderGroup()',self.js)
        self.assertIn('async function openFolderGroup(index)',self.js)
        self.assertIn('async function renameFolderGroup(index)',self.js)
        self.assertIn('async function deleteFolderGroup(index)',self.js)
        self.assertIn('"/api/groups/open"',self.js)
        self.assertIn('folderGroups:state.folderGroups.map',self.js)
        self.assertIn('state.folderGroups=Array.isArray(saved.folderGroups)',self.js)
        self.assertIn('data-group-open=',self.js)
        self.assertIn('data-group-rename=',self.js)
        self.assertIn('data-group-delete=',self.js)
        self.assertIn('renderFolderGroups();',self.js)
        self.assertIn('display=children(null);sectionTitle="根模块";',self.js)
        self.assertIn('.group-report-row.failure',self.css)

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
