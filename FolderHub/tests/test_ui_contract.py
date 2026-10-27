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

    def test_v51_search_prevents_unsupported_file_imports(self):
        self.assertIn('item.supported!==false',self.js)
        self.assertIn('item.supported===false',self.js)
        self.assertIn('result.unavailable||0',self.js)
        self.assertIn('当前文件类型不支持加入导航',self.js)
        self.assertIn('.everything-result button:disabled',self.css)

    def test_v53_workspace_launch_is_explicit_bounded_and_reported(self):
        for ctrl in ("workspaceLaunchList","workspaceLaunchHint","workspaceLaunchLayer",
                     "workspaceLaunchTitle","workspaceLaunchRows","workspaceLaunchSummary",
                     "workspaceLaunchDone","workspaceLaunchClose"):
            self.assertIn('id="'+ctrl+'"',self.html)
            self.assertIn(ctrl,self.js)
        self.assertIn('function renderWorkspaceLaunchChoices()',self.js)
        self.assertIn('const current={name,description,members:ids,status,links,launch_ids};',self.js)
        self.assertIn('data-action="launch-workspace"',self.js)
        self.assertIn('case "launch-workspace":await launchActiveWorkspace();break;',self.js)
        self.assertIn('"/api/workspaces/launch"',self.js)
        self.assertIn('showWorkspaceLaunchResult(result);',self.js)
        self.assertIn('workspaceDraftLaunchIds.size>=8',self.js)
        self.assertIn('h(item.error||"未知错误")',self.js)
        self.assertIn('.workspace-launch-settings',self.css)

    def test_everything_search_is_optional_local_and_explicit(self):
        for control in ("everythingBtn","everythingLayer","everythingForm",
                        "everythingQuery","everythingResults","everythingStatus","everythingClose"):
            self.assertIn('id="'+control+'"',self.html)
            self.assertIn(control,self.js)
        self.assertIn('function runEverythingSearch(event)',self.js)
        self.assertIn('function chooseEverythingResult(index)',self.js)
        self.assertIn('bindEverything();',self.js)
        self.assertIn('"/api/everything/search?q="+encodeURIComponent(query)',self.js)
        self.assertIn('h(item.path)',self.js)
        self.assertIn('h(item.name)',self.js)
        self.assertIn('editDialog(null,parent.id)',self.js)
        self.assertIn('.everything-result',self.css)

    def test_unified_file_folder_web_resource_editor(self):
        for control in ("entryKindRow","entryResourceKind","entryTargetRow",
                        "entryResourceTarget","entryTargetLabel"):
            self.assertIn('id="'+control+'"',self.html)
            self.assertIn(control,self.js)
        for kind in ('value="folder"','value="file"','value="url"'):
            self.assertIn(kind,self.html)
        self.assertIn('resource_kind:type==="leaf"',self.js)
        self.assertIn('resource_target:type==="leaf"',self.js)
        self.assertIn('n.resource_target',self.js)
        self.assertIn("resourceKind==='file'",self.js)
        self.assertIn("resourceKind==='url'",self.js)
        self.assertIn('$("#entryResourceKind").addEventListener("change",updateEntryType)',self.js)
        self.assertIn('#entryTargetRow',self.css)

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
                     "bulkDelete","bulkCancel",
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

    def test_legacy_trash_and_usage_are_not_in_active_navigation(self):
        for view in ('favorites','recent','frequent','trash'):
            self.assertNotIn('data-view="'+view+'"',self.html)
        self.assertIn('id="specialNav"',self.html)
        self.assertNotIn('"/api/trash"',self.js)
        self.assertNotIn('"/api/recent"',self.js)
        self.assertNotIn('"/api/frequent"',self.js)
        self.assertNotIn('function trashCard(',self.js)
        self.assertNotIn('function restoreTrash(',self.js)
        self.assertIn('const data=await api("/api/nodes")',self.js)

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

    def test_workspace_navigation_and_portable_settings_contract(self):
        self.assertIn('id="workspaceSection"',self.html)
        for control in ('workspaceCount','workspaceNav',
                        'workspaceNew','workspaceLayer','workspaceForm',
                        'workspaceName','workspaceDescription','workspaceMemberSearch',
                        'workspaceMemberList','workspaceMemberSummary','workspaceSave',
                        'bulkSaveWorkspace','workspaceClose','workspaceCancel'):
            self.assertIn(f'id="{control}"',self.html)
            self.assertIn(control,self.js)
        for symbol in ('function renderWorkspaces()', 'function openWorkspaceDialog(',
                       'function renderWorkspaceMembers()', 'async function submitWorkspace(',
                       'async function deleteWorkspace('):
            self.assertIn(symbol,self.js)
        self.assertIn('workspaces:state.workspaces.map(',self.js)
        self.assertIn('state.workspaces=Array.isArray(saved.workspaces)',self.js)
        self.assertIn('#workspace/',self.js)
        self.assertIn('data-workspace-open=',self.js)
        self.assertIn('data-action="edit-workspace"',self.js)
        self.assertIn('workspaceDraftMembers.size>=30',self.js)
        self.assertIn('.workspace-member-list',self.css)
        self.assertIn('.workspace-nav',self.css)

    def test_workspace_v44_status_counts_and_fast_switch_contract(self):
        self.assertIn('function workspaceOverviewCounts(item)', self.js)
        self.assertIn('function renderWorkspaceResources()', self.js)
        self.assertIn('data-workspace-switch', self.js)
        self.assertIn('id="workspaceSwitcher"', self.js)
        self.assertIn('for="workspaceSwitcher"', self.js)
        self.assertIn('item.members.map(id=>byId(id))', self.js)
        self.assertIn('state.workspaces.some(item=>item.name===destination)', self.js)
        self.assertIn('setView("workspace",destination)', self.js)
        self.assertIn('workspace-overview-metrics', self.js)
        self.assertIn('.workspace-overview-metrics', self.css)
        self.assertIn('.workspace-quick-switch', self.css)

    def test_workspace_v44_reorder_links_only_in_draft(self):
        self.assertIn('function movedWorkspaceLinkItems(links,index,direction)', self.js)
        self.assertIn('function moveWorkspaceDraftLink(index,direction)', self.js)
        self.assertIn('data-workspace-link-move=', self.js)
        self.assertIn('data-workspace-step="-1"', self.js)
        self.assertIn('data-workspace-step="1"', self.js)
        self.assertIn('workspaceDraftLinks=next;', self.js)
        begin = self.js.index('function moveWorkspaceDraftLink(index,direction)')
        end = self.js.index('function renderWorkspaceLinkEditor()', begin)
        self.assertNotIn('persistProjectSettings()', self.js[begin:end])
        self.assertIn('.workspace-link-order', self.css)

    def test_workspace_v44_resources_remain_safe_external_links(self):
        begin = self.js.index('function renderWorkspaceResources()')
        end = self.js.index('function renderCrumb()', begin)
        segment = self.js[begin:end]
        self.assertIn('h(link.name)', segment)
        self.assertIn('h(validWorkspaceUrl(link.url))', segment)
        self.assertIn('target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer"',segment)
        self.assertNotIn('fetch(', segment)
        self.assertIn('box.classList.toggle("hidden",!item);', segment)

    def test_workspace_resource_editor_and_portable_schema(self):
        for widget in ('workspaceResources', 'workspaceStatus', 'workspaceLinkAdd',
                       'workspaceLinkList'):
            self.assertIn(f'id="{widget}"', self.html)
            self.assertIn(widget, self.js)
        for code in ('function copyWorkspaceRecord(item)', 'function validWorkspaceUrl(value)',
                     'function validateWorkspaceDraftLinks()', 'function renderWorkspaceResources()',
                     'function renderWorkspaceLinkEditor()'):
            self.assertIn(code, self.js)
        self.assertIn('workspaces:state.workspaces.map(item=>copyWorkspaceRecord(item))',self.js)
        self.assertIn('saved.workspaces.map(item=>copyWorkspaceRecord(item))',self.js)
        self.assertIn('const current={name,description,members:ids,status,links};',self.js)
        self.assertIn('$("#workspaceStatus").value=item.status||"planning"',self.js)
        self.assertIn('renderWorkspaceLinkEditor();',self.js)
        self.assertIn('.workspace-resources',self.css)
        self.assertIn('status:item.status||"planning"',self.js)
        self.assertIn('links:Array.isArray(item.links)',self.js)
        self.assertIn('workspaceDraftLinks=(item.links||[]).map(link=>({...link}));',self.js)
        self.assertIn('copyWorkspaceRecord(w));',self.js)
        self.assertIn('renderWorkspaceResources();',self.js)

    def test_workspace_web_resources_are_explicit_and_safe(self):
        begin=self.js.index('function renderWorkspaceResources()')
        end=self.js.index('function renderCrumb()',begin)
        region=self.js[begin:end]
        self.assertIn('validWorkspaceUrl(link.url)',region)
        self.assertIn('target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer"',region)
        self.assertIn('h(link.name)',region)
        self.assertIn('h(validWorkspaceUrl(link.url))',region)
        self.assertNotIn('fetch(',region)
        self.assertIn('["http:","https:"]',self.js)
        self.assertIn('function validateWorkspaceDraftLinks()',self.js)

    def test_workspace_member_ordering_controls(self):
        for control in ('data-workspace-move=', 'data-workspace-step="1"',
                        'data-workspace-step="-1"'):
            self.assertIn(control, self.js)
        self.assertIn('function movedWorkspaceMemberIds(ids,id,direction)',self.js)
        self.assertIn('function moveWorkspaceDraftMember(id,direction)',self.js)
        self.assertIn('workspaceDraftMembers=new Set(after)',self.js)
        self.assertIn('const ids=[...workspaceDraftMembers];',self.js)
        self.assertIn('workspace.members.map(id=>byId(id)).filter(Boolean)',self.js)
        self.assertIn('.workspace-member-order',self.css)

    def test_workspace_copy_is_draft_until_saved(self):
        self.assertIn('case "copy-workspace":duplicateWorkspace(',self.js)
        self.assertIn('function uniqueWorkspaceCopyName(original)',self.js)
        start=self.js.index('function duplicateWorkspace(index)')
        end=self.js.index('async function deleteWorkspace(index)',start)
        self.assertIn('openWorkspaceDialog(-1,existing)',self.js[start:end])
        self.assertIn('$("#workspaceDescription").value=item.description;',self.js[start:end])
        self.assertNotIn('persistProjectSettings()',self.js[start:end])

    def test_workspace_quick_add_uses_existing_ids_and_validation(self):
        self.assertIn('id="workspacePickerTitle"',self.html)
        self.assertIn('aria-labelledby="workspacePickerTitle"',self.html)
        for control in ('workspacePickerLayer','workspacePickerList',
                        'workspacePickerClose','workspacePickerCancel',
                        'workspacePickerSummary'):
            self.assertIn(f'id="{control}"',self.html)
            self.assertIn(control,self.js)
        self.assertIn('["workspace-add","加入项目工作区…"]',self.js)
        self.assertIn('function openWorkspacePicker(nodeId)',self.js)
        self.assertIn('async function addNodeToWorkspace(index)',self.js)
        self.assertIn('if(!item||!byId(nodeId)||workspaceSaving',self.js)
        self.assertIn('item.members.length>=30',self.js)
        self.assertIn('persistProjectSettings()',self.js)
        self.assertIn('state.workspaces=before;',self.js)
        self.assertIn('.workspace-picker-option',self.css)

    def test_workspace_is_browsable_not_a_bulk_explorer_launcher(self):
        start=self.js.index('function renderWorkspaces()')
        end=self.js.index('function renderCrumb()',start)
        self.assertNotIn('/api/groups/open',self.js[start:end])
        start=self.js.index('async function submitWorkspace(event)')
        end=self.js.index('async function deleteWorkspace(index)',start)
        self.assertIn('persistProjectSettings()',self.js[start:end])
        self.assertNotIn('open_in_explorer',self.js[start:end])
        self.assertIn('display=workspace.members.map(id=>byId(id)).filter(Boolean);',self.js)
        self.assertIn('case "edit-workspace":',self.js)

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

    def test_removed_auxiliary_views_have_no_dom_controls(self):
        for control in ('trashCount','recentCount','frequentCount','favoriteCount',
                        'bulkFavorite','bulkUnfavorite','entryFavorite'):
            self.assertNotIn('id="'+control+'"',self.html)
        self.assertNotIn('function toggleRecentPin(',self.js)
        self.assertNotIn('function favoriteNode(',self.js)
        self.assertIn('display=children(null);sectionTitle="根模块";',self.js)

    def test_search_keyboard_without_pinned_usage_contracts(self):
        self.assertIn('aria-keyshortcuts="Control+K Meta+K"',self.html)
        self.assertIn('state.searchKeyboardIndex',self.js)
        self.assertIn('e.key==="ArrowDown"',self.js)
        self.assertIn('"ArrowUp"',self.js)
        self.assertIn('e.key==="Enter"',self.js)
        self.assertNotIn('data-action="pin"',self.js)
        self.assertIn('keyboard-active',self.css)

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
        self.assertIn('data-action="copy-path"',self.js)
        self.assertIn('async function copyFolderPath(id)',self.js)
        self.assertIn('case "copy-path":await copyFolderPath(id);break;',self.js)
        self.assertIn('.entries.list .card-primary .list-card-context',self.css)
        self.assertIn('@media(max-width:1200px)',self.css)
        responsive=self.css.split('/* V2.7 — Show search breadcrumb/recent history',1)[1]
        self.assertIn('grid-row:2;',responsive)
        self.assertIn('grid-row:3;',responsive)
        self.assertIn('flex-wrap:wrap;',responsive)

    def test_v52_memoized_ancestor_chains_and_search_cache(self):
        self.assertIn('function buildSearchRecords(nodes,lookup)',self.js)
        self.assertIn('const chainCache=new Map();',self.js)
        self.assertIn('const pending=[],visited=new Set();',self.js)
        self.assertIn('searchRecords=buildSearchRecords(state.nodes,nodeById);',self.js)
        self.assertIn('indexedTagCount=tagNames.size;',self.js)
        self.assertIn('$("#tagCount").textContent=indexedTagCount;',self.js)
        self.assertIn('cachedSearch=null;',self.js)
        self.assertIn('if(cachedSearch?.query===query)return cachedSearch.result;',self.js)
        self.assertIn('cachedSearch={query,result};',self.js)

    def test_v52_coalesces_search_keystrokes_without_rebuilding_sidebar(self):
        self.assertIn('function queueSearchRender()',self.js)
        self.assertIn('function flushSearchRender()',self.js)
        self.assertIn('requestAnimationFrame(()=>{',self.js)
        self.assertIn('cancelAnimationFrame(searchRenderFrame);',self.js)
        self.assertIn('state.renderLimit=100;queueSearchRender();',self.js)
        self.assertIn('flushSearchRender();return;',self.js)
        self.assertIn('if(!skipNav)renderNav();',self.js)
        self.assertIn('renderSavedViews(); // Invalidate selected saved-view state',self.js)
        self.assertNotIn('else {renderSavedViews();renderFolderGroups();renderWorkspaces()}',self.js)

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
        self.assertIn('const visibleCount=Math.min(results.length,state.renderLimit);',self.js)
        self.assertIn('old<0?visibleCount-1:',self.js)
        self.assertNotIn('state.renderLimit=Math.ceil((state.searchKeyboardIndex+1)/100)*100',self.js)
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
        self.assertNotIn('/api/recent',body)

    def test_highlight_locate_and_focus_restoration(self):
        self.assertIn("function highlightSearch(value,query)",self.js)
        self.assertIn("class=\"search-hit\"",self.js)
        self.assertIn("function locateNode(id)",self.js)
        self.assertIn("data-action=\"locate\"",self.js)
        self.assertIn('case "locate":locateNode(id);break;',self.js)
        self.assertIn("const limit=Math.ceil((index+1)/100)*100",self.js)
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
        self.assertIn('const seen=new Set();',self.js)
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
        self.assertIn('if(!skipNav)renderNav();',self.js)
        self.assertIn('renderSavedViews(); // Invalidate selected saved-view state',self.js)
        self.assertNotIn('else {renderSavedViews();renderFolderGroups();renderWorkspaces()}',self.js)
        self.assertIn('const rewritten=state.savedViews.map(view=>{',self.js)
        self.assertIn('state.savedViews=rewritten;',self.js)

    def test_saved_views_keep_unassigned_tags_removable(self):
        self.assertIn('const previouslySelected=state.tagSelection.includes(tag)',self.js)
        self.assertIn('subset.push(row||[tag,0]);',self.js)

    def test_quick_palette_is_lightweight_and_bounded(self):
        self.assertIn('function quickCandidates(query="")',self.js)
        self.assertIn('const result=[],seen=new Set();',self.js)
        self.assertIn('if(result.length>=12)break;',self.js)
        self.assertIn('if(node.folder_path||node.resource_target)collect(node);',self.js)
        self.assertNotIn('state.recent',self.js)
        self.assertNotIn('state.frequent',self.js)
        self.assertNotIn('state.trash',self.js)

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

    def test_preference_revision_contract_protects_multiple_browser_tabs(self):
        self.assertIn('let preferencesRevision=null;',self.js)
        self.assertIn('let preferencesConflict=false;',self.js)
        self.assertIn('expected_revision:preferencesRevision',self.js)
        self.assertIn('preferencesRevision=saved.revision;',self.js)
        self.assertIn('preferencesRevision=payload.revision??null;',self.js)
        self.assertIn('preferencesConflict=true;',self.js)
        self.assertIn('pendingSettings=null;',self.js)
        self.assertIn('e.code==="preferences_conflict"',self.js)
        self.assertIn('error.status=response.status;',self.js)
        self.assertIn('if(preferencesConflict)',self.js)

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
