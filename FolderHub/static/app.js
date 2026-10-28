"use strict";

const THEMES = [
  {id:"cloud",title:"云白",description:"清爽工作台",colors:["#f5f7ff","#ffffff","#6652d9"]},
  {id:"midnight",title:"午夜",description:"沉浸深色",colors:["#111829","#1c2840","#8e88ff"]},
  {id:"forest",title:"雾森",description:"柔和自然",colors:["#edf6f1","#ffffff","#23846e"]},
  {id:"aurora",title:"极光",description:"薄荷渐变",colors:["#ecf9fc","#ffffff","#277d9b"]},
  {id:"sand",title:"暖沙",description:"温暖纸感",colors:["#faf4e9","#fffcf5","#bc7650"]},
  {id:"graphite",title:"石墨",description:"柔和暗色",colors:["#181b24","#272c38","#97b2e2"]},
  {id:"system",title:"跟随系统",description:"自动适配",colors:["#d6d5e8","#252b42","#7b7ad6"]}
];
// Ant Design Pro-inspired density, typography and workspace customization.
// Project-owned preferences are stored in data/preferences.json; browser values are imported only once.
const ICONS = {
  folder:"📁",book:"📚",code:"💻",chart:"📊",database:"🗃️",image:"🖼️",
  briefcase:"💼",school:"🎓",music:"🎵",video:"🎬",archive:"🗄️",star:"⭐"
};
const PREF_DEFAULTS = Object.freeze({font:"large",density:"comfortable",listDensity:"normal",sidebar:"normal",columns:"auto",accent:"blue",showCovers:true,coverHeight:"normal",coverFit:"cover",sidebarCollapsed:false});
const PREF_ALLOWED = {font:["normal","large","xlarge"],density:["comfortable","compact"],listDensity:["compact","normal","relaxed"],sidebar:["normal","wide"],columns:["auto","2","3","4"],accent:["blue","purple","teal","orange","rose"],coverHeight:["short","normal","tall"],coverFit:["cover","contain"]};
function readPreferences(){
  try {
    const stored=JSON.parse(localStorage.getItem("folderhub.appearance")||"{}");
    if(!stored || typeof stored!=="object" || Array.isArray(stored))return {...PREF_DEFAULTS};
    const result={...PREF_DEFAULTS};
    for(const [key,values] of Object.entries(PREF_ALLOWED))if(values.includes(stored[key]))result[key]=stored[key];
    for(const key of ["sidebarCollapsed","showCovers"])if(typeof stored[key]==="boolean")result[key]=stored[key];
    return result;
  } catch(_){return {...PREF_DEFAULTS}}
}
let preferences={...PREF_DEFAULTS};
function applyPreferences(){
  const root=document.documentElement;
  root.dataset.font=preferences.font;
  root.dataset.density=preferences.density;
  root.dataset.listDensity=preferences.listDensity;
  root.dataset.sidebarWidth=preferences.sidebar;
  root.dataset.columns=preferences.columns;
  root.dataset.accent=preferences.accent;
  root.dataset.sidebarCollapsed=String(preferences.sidebarCollapsed);
  root.dataset.showCovers=String(preferences.showCovers);
  root.dataset.coverHeight=preferences.coverHeight;
  root.dataset.coverFit=preferences.coverFit;
  const trigger=document.querySelector("#sidebarToggle");
  if(trigger)trigger.setAttribute("aria-expanded",String(!preferences.sidebarCollapsed));
}
function updateAppearanceControls(){
  const coverToggle=document.querySelector("#showCoversToggle");if(coverToggle)coverToggle.checked=preferences.showCovers;
  document.querySelectorAll("[data-pref][data-value]").forEach(button=>{
    const active=preferences[button.dataset.pref]===button.dataset.value;
    button.classList.toggle("selected",active);
    button.setAttribute("aria-pressed",String(active));
  });
}
function setPreference(key,value){
  if(Object.hasOwn(PREF_ALLOWED,key) && PREF_ALLOWED[key].includes(value)){
    preferences[key]=value;
    savePreferences();
  }
}
function savePreferences(){
  applyPreferences();updateAppearanceControls();persistProjectSettings();
}
const validTheme = theme => THEMES.some(t=>t.id===theme) ? theme : "cloud";
function getSavedTheme(){try{return validTheme(localStorage.getItem("folderhub.theme") || "cloud")}catch(_){return "cloud"}}
const state = {savedViews:[],folderGroups:[],workspaces:[],activeWorkspace:null,groupBusy:false,activeSmartView:null,openingIds:new Set(),nodes:[], activeTag:null, tagSelection:[], tagExcluded:[], tagMatchMode:"any", tagPickMode:"include", renderLimit:100, searchKeyboardIndex:-1, token:"", view:"all", selected:null, search:"", layout:"grid", editing:null, theme:"cloud", startup:null, expanded:new Set(), treeInitialized:false, pendingCover:null, removeCover:false, draggingId:null, sorting:false,selectMode:false,selectedIds:new Set(),visibleIds:[],batchBusy:false,contextId:null};

/* V3.0 — Native browser history for modules and special views.
   Search text is stored in the current tab's history.state, never in the URL. */
let navigationReady=false;
function routeFromLocation(){
  const hash=window.location.hash;
  if(!hash || hash==="#home")return {view:"all",id:null};
  const match=/^#node\/([1-9]\d*)$/.exec(hash);
  if(match){
    const id=Number(match[1]);
    return Number.isSafeInteger(id)?{view:"node",id}:{view:"all",id:null};
  }
  if(hash.startsWith("#workspace/")){
    try{
      const name=decodeURIComponent(hash.slice("#workspace/".length));
      if(name&&name.length<=40)return {view:"workspace",id:name};
    }catch(_){/* Invalid deep link goes to home. */}
    return {view:"all",id:null};
  }
  const view=hash.slice(1);
  return ["tags"].includes(view)?
    {view,id:null}:{view:"all",id:null};
}
function routeUrl(view,id=null){
  const suffix=view==="node"?`#node/${id}`:view==="workspace"?`#workspace/${encodeURIComponent(id??state.activeWorkspace??"")}`:view==="all"?"":`#${view}`;
  return window.location.pathname+window.location.search+suffix;
}
function navigationSnapshot(){
  return {folderhubRoute:1,view:state.view,
    id:state.view==="node"?state.selected:state.view==="workspace"?state.activeWorkspace:null,
    tag:state.view==="tags"?state.activeTag:null,
    tagSelection:state.view==="tags"?[...state.tagSelection]:[],
    tagExcluded:state.view==="tags"?[...state.tagExcluded]:[],
    tagMatchMode:state.tagMatchMode,
    tagPickMode:state.tagPickMode,
    smartView:state.view==="tags"?state.activeSmartView:null,
    search:state.search,renderLimit:state.renderLimit,
    scrollY:Math.max(0,Math.round(window.scrollY||0))};
}
function rememberNavigation(){
  if(!navigationReady)return;
  window.history.replaceState(navigationSnapshot(),"",routeUrl(state.view,state.selected));
}
function restoredEntry(route){
  const entry=window.history.state;
  return entry?.folderhubRoute===1 && entry.view===route.view &&
    (entry.id??null)===(route.id??null)?entry:null;
}
function restoreBrowserNavigation(){
  if(!navigationReady)return;
  const route=routeFromLocation(),saved=restoredEntry(route);
  setView(route.view,route.id,{fromHistory:true,saved});
  if(route.view!==state.view || (route.id??null)!==(state.selected??null))
    window.history.replaceState(navigationSnapshot(),"",routeUrl(state.view,state.selected));
}
function startBrowserNavigation(){
  if("scrollRestoration" in window.history)window.history.scrollRestoration="manual";
  const route=routeFromLocation(),saved=restoredEntry(route);
  navigationReady=true;
  setView(route.view,route.id,{fromHistory:true,saved});
  const preservedY=Number.isFinite(saved?.scrollY)?saved.scrollY:0;
  window.history.replaceState({...navigationSnapshot(),scrollY:preservedY},"",
    routeUrl(state.view,state.selected));
}

// The server is authoritative. localStorage is read ONLY to migrate a legacy browser once.
let initialExpanded=null;
let projectSettingsReady=false;
let pendingSettings=null;
let settingsWriteInFlight=false;
let settingsWritePromise=null;
let preferencesRevision=null;
let preferencesConflict=false;
const WORKSPACE_STATUS_NAMES={planning:"筹备中",active:"进行中",paused:"已暂停",done:"已完成"};
function copyWorkspaceRecord(item){
  return {name:item.name,description:item.description,members:[...item.members],
    status:item.status||"planning",
    links:Array.isArray(item.links)?item.links.map(link=>({name:link.name,url:link.url})):[],
    launch_ids:Array.isArray(item.launch_ids)?[...item.launch_ids]:[]};
}
function validWorkspaceUrl(value){
  if(typeof value!=="string"||!value||value.length>2048||/[\x00-\x20\x7f\\]/.test(value))return null;
  try{
    const parsed=new URL(value);
    if(!["http:","https:"].includes(parsed.protocol)||!parsed.hostname||
       parsed.username||parsed.password)return null;
    return parsed.href;
  }catch(_){return null}
}
function collectProjectSettings(){
  return {...preferences,theme:state.theme,layout:state.layout,
    expanded:state.treeInitialized?[...state.expanded]:initialExpanded,
    savedViews:state.savedViews.map(view=>({name:view.name,includes:[...view.includes],
      excludes:[...view.excludes],mode:view.mode})),
    folderGroups:state.folderGroups.map(group=>({name:group.name,members:[...group.members]})),
    workspaces:state.workspaces.map(item=>copyWorkspaceRecord(item))};
}
async function persistProjectSettings(){
  if(!projectSettingsReady)return true;
  if(preferencesConflict){
    toast("设置版本未确认，本页已暂停写入；请记录未保存的修改并刷新页面后继续",true);
    return false;
  }
  pendingSettings=collectProjectSettings();
  if(settingsWriteInFlight)return settingsWritePromise;
  settingsWriteInFlight=true;
  settingsWritePromise=(async()=>{
    let success=true;
    try{
      while(pendingSettings){
        const snapshot=pendingSettings;pendingSettings=null;
        try{
          const saved=await mutate("PUT","/api/preferences",
            {settings:snapshot,expected_revision:preferencesRevision});
          preferencesRevision=saved.revision;
        }catch(e){
          success=false;
          // A failed request may have reached the server. Never replay later
          // snapshots using a revision whose outcome is no longer certain.
          preferencesConflict=true;
          pendingSettings=null;
          if(e.code==="preferences_conflict"||e.status===409)
            toast("其他页面已修改设置，已阻止旧配置覆盖。请先记录本页未保存的内容，再刷新页面。",true);
          else
            toast("保存设置失败，无法确认服务器是否已写入。已暂停后续保存，请记录当前修改后刷新页面："+e.message,true);
          break;
        }
      }
    }finally{settingsWriteInFlight=false;settingsWritePromise=null}
    return success;
  })();
  return settingsWritePromise;
}
function legacyBrowserSettings(){
  const settings={...readPreferences(),theme:getSavedTheme(),layout:"grid",expanded:loadTreeState()};
  if(!Array.isArray(settings.expanded)||settings.expanded.length>20000 ||
     settings.expanded.some(n=>!Number.isInteger(n)||n<1)||
     new Set(settings.expanded).size!==settings.expanded.length)settings.expanded=null;
  return settings;
}
async function loadProjectSettings(){
  let payload=await api("/api/preferences");
  if(!payload.configured){
    // POST is a write-once import: another browser's already saved preferences win.
    payload=await mutate("POST","/api/preferences",{settings:legacyBrowserSettings()});
  }
  preferencesRevision=payload.revision??null;
  preferencesConflict=false;
  const saved=payload.settings||{};
  preferences={...PREF_DEFAULTS};
  for(const [key,values] of Object.entries(PREF_ALLOWED))
    if(values.includes(saved[key]))preferences[key]=saved[key];
  for(const key of ["showCovers","sidebarCollapsed"])
    if(typeof saved[key]==="boolean")preferences[key]=saved[key];
  state.theme=validTheme(saved.theme);
  state.layout=saved.layout==="list"?"list":"grid";
  initialExpanded=Array.isArray(saved.expanded)?saved.expanded:null;
  state.savedViews=Array.isArray(saved.savedViews)?saved.savedViews.map(view=>({
    name:view.name,includes:[...view.includes],excludes:[...view.excludes],mode:view.mode
  })):[];
  state.folderGroups=Array.isArray(saved.folderGroups)?saved.folderGroups.map(group=>({
    name:group.name,members:[...group.members]
  })):[];
  state.workspaces=Array.isArray(saved.workspaces)?
    saved.workspaces.map(item=>copyWorkspaceRecord(item)):[];
  projectSettingsReady=true;
  document.documentElement.dataset.theme=state.theme;
  $("#layoutBtn").textContent=state.layout==="grid"?"▦":"☷";
  applyPreferences();updateAppearanceControls();
}
document.documentElement.dataset.theme=state.theme;
applyPreferences();
const $ = (s) => document.querySelector(s);
const h = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function highlightSearch(value,query){
  const content=String(value??"");
  const words=[...new Set(String(query??"").trim().toLocaleLowerCase().split(/\s+/).filter(Boolean))].slice(0,16).sort((a,b)=>b.length-a.length);
  if(!words.length)return h(content);
  const lower=content.toLocaleLowerCase();
  let cursor=0,html="";
  while(cursor<content.length){
    let best=-1,hit="";
    for(const term of words){
      const found=lower.indexOf(term,cursor);
      if(found!==-1&&(best===-1||found<best||(found===best&&term.length>hit.length))){
        best=found;hit=term;
      }
    }
    if(best===-1)break;
    html+=h(content.slice(cursor,best))+`<mark class="search-hit">${h(content.slice(best,best+hit.length))}</mark>`;
    cursor=best+hit.length;
  }
  return html+h(content.slice(cursor));
}
function restoreCardFocus(id,action){
  const card=document.getElementById(`folderhub-entry-${id}`);
  const selector=action===null?".card-primary":`[data-action="${action}"]`;
  const target=card?.querySelector(selector)||
    document.querySelector("#entries .card-primary")||$("#search");
  target?.focus?.({preventScroll:true});
}
let toastTimer;
// Rebuilt only after the server returns new node data. Rendering/searching then
// use O(1) lookups instead of scanning every node for every card/ancestor.
let nodeById = new Map();
let childrenByParent = new Map();
let searchRecords = [];
let indexedTagCount = 0;
let indexedTagNames = new Set();
let cachedSearch = null;
// A changing selection must not remount the entire expanded sidebar tree.
// Only refreshed nodes or a changed expansion state invalidate the markup.
let navTreeDataVersion = 0;
let navTreeRenderedVersion = -1;
let navTreeActiveId = null;
const byId = id => nodeById.get(id);
const sorted = nodes => [...nodes].sort((a,b)=>a.sort_order-b.sort_order || a.id-b.id);
const children = id => childrenByParent.get(id??null) || [];

// Cache each ancestor chain once instead of recomputing its prefix for
// every descendant in large/deep navigation trees. Cycles are bounded.
function buildSearchRecords(nodes,lookup){
  const chainCache=new Map();
  function lineage(node){
    if(chainCache.has(node.id))return chainCache.get(node.id);
    const pending=[],visited=new Set();
    let cursor=node;
    while(cursor&&!chainCache.has(cursor.id)&&!visited.has(cursor.id)){
      pending.push(cursor);
      visited.add(cursor.id);
      cursor=lookup.get(cursor.parent_id);
    }
    let prefix=cursor&&chainCache.has(cursor.id)?chainCache.get(cursor.id):"";
    while(pending.length){
      const part=pending.pop();
      prefix=prefix?prefix+" /"+part.title:part.title;
      chainCache.set(part.id,prefix);
    }
    return chainCache.get(node.id)||"";
  }
  return nodes.map(node=>{
    const own=(node.title+" "+(node.folder_path||node.resource_target||"")).toLocaleLowerCase();
    const full=lineage(node).toLocaleLowerCase();
    return {node,own,body:own+" "+full+" "+(node.tags||[]).join(" ").toLocaleLowerCase()};
  });
}
function rebuildNodeIndex(){
  nodeById = new Map(state.nodes.map(node=>[node.id,node]));
  childrenByParent = new Map();
  const tagNames=new Set();
  for(const node of state.nodes){
    const parent = node.parent_id??null;
    if(!childrenByParent.has(parent))childrenByParent.set(parent,[]);
    childrenByParent.get(parent).push(node);
    for(const tag of node.tags||[])tagNames.add(tag);
  }
  indexedTagNames=tagNames;
  indexedTagCount=tagNames.size;
  for(const nodes of childrenByParent.values())nodes.sort((a,b)=>a.sort_order-b.sort_order || a.id-b.id);
  searchRecords=buildSearchRecords(state.nodes,nodeById);
  cachedSearch=null;
  navTreeDataVersion++;
}

function toast(message, error=false, action=null) {
  const el=$("#toast");
  el.replaceChildren(document.createTextNode(message));
  if(action && typeof action.handler==="function"){
    const button=document.createElement("button");
    button.type="button";button.className="toast-action";
    button.textContent=action.label||"撤销";
    button.addEventListener("click",()=>{clearTimeout(toastTimer);el.className="toast";action.handler()},{once:true});
    el.append(button);
  }
  el.className="toast show"+(error?" error":"");
  clearTimeout(toastTimer);toastTimer=setTimeout(()=>{el.className="toast"},action?9000:3600);
}
async function api(path, options={}) {
  const headers={...(options.headers||{})};
  if (options.method && options.method!=="GET") {
    headers["Content-Type"]="application/json";
    headers["X-FolderHub-Token"]=state.token;
  }
  let response;
  try { response=await fetch(path,{...options,headers}); }
  catch(e) {throw new Error("本地服务连接失败，请启动 FolderHub 后刷新页面");}
  let data;
  try {data=await response.json()} catch(e){throw new Error("服务器响应无效")}
  if(!response.ok){
    const error=new Error(data.error||`操作失败 (${response.status})`);
    error.status=response.status;
    error.code=data.code||null;
    throw error;
  }
  return data;
}
const mutate = (method,path,data={}) => api(path,{method,body:JSON.stringify(data)});
function loadTreeState() {
  try {const saved=localStorage.getItem("folderhub.expanded");return saved===null?null:JSON.parse(saved)}
  catch(_){return null}
}
function saveTreeState(){persistProjectSettings()}
function expandLineage(id){
  let changed=false;
  for(const node of ancestors(id)){
    if(node.node_type!=="leaf"&&!state.expanded.has(node.id)){
      state.expanded.add(node.id);changed=true;
    }
  }
  if(changed){navTreeDataVersion++;saveTreeState();}
}
async function refresh(){
  const data=await api("/api/nodes");
  state.nodes=data.nodes;
  rebuildNodeIndex();
  if(!state.treeInitialized){
    const saved=initialExpanded;
    state.expanded=new Set(Array.isArray(saved)?saved.filter(id=>Number.isInteger(id)):children(null).map(n=>n.id));
    state.treeInitialized=true;
  }
  if(state.view==="node"&&state.selected!==null)expandLineage(state.selected);
  render();
}

function descendants(id) {
  const found=new Set([id]), queue=[id];
  for(let offset=0;offset<queue.length;offset++){
    for(const node of children(queue[offset])){
      if(!found.has(node.id)){found.add(node.id);queue.push(node.id)}
    }
  }
  return found;
}
function ancestors(id) {
  const result=[], visited=new Set();let current=byId(id);
  while(current && !visited.has(current.id)){result.unshift(current);visited.add(current.id);current=byId(current.parent_id)}
  return result;
}
function setView(view,id=null,{fromHistory=false,saved=null}={}){
  // A pending search frame would otherwise redraw a view that was just
  // replaced by navigation within the same event-loop turn.
  if(searchRenderFrame!==null){
    cancelAnimationFrame(searchRenderFrame);
    searchRenderFrame=null;
  }
  if(!fromHistory)rememberNavigation();
  closeCardMenu();exitSelectMode();
  if(view==="node"&&!byId(id)){view="all";id=null}
  if(view==="workspace"&&!state.workspaces.some(item=>item.name===id)){view="all";id=null}
  state.view=view;state.selected=view==="node"?id:null;
  state.activeWorkspace=view==="workspace"?id:null;
  // Reuse the node index: opening a view must not scan every node's tags.
  const available=indexedTagNames;
  const restoredSmartView=fromHistory&&view==="tags"?
    state.savedViews.find(item=>item.name===saved?.smartView):null;
  const previousIncludes=restoredSmartView?restoredSmartView.includes:
    Array.isArray(saved?.tagSelection)?saved.tagSelection:
    (saved?.tag?[saved.tag]:[]);
  const previousExcludes=restoredSmartView?restoredSmartView.excludes:
    (Array.isArray(saved?.tagExcluded)?saved.tagExcluded:[]);
  const keepTag=tag=>typeof tag==="string"&&(Boolean(restoredSmartView)||available.has(tag));
  state.tagSelection=view==="tags"&&fromHistory?
    [...new Set(previousIncludes.filter(keepTag))].slice(0,30):[];
  state.tagExcluded=view==="tags"&&fromHistory?
    [...new Set(previousExcludes.filter(tag=>keepTag(tag)&&!state.tagSelection.includes(tag)))].slice(0,30):[];
  state.tagMatchMode=restoredSmartView?restoredSmartView.mode:
    fromHistory&&saved?.tagMatchMode==="all"?"all":"any";
  state.tagPickMode=fromHistory&&saved?.tagPickMode==="exclude"?"exclude":"include";
  state.activeTag=view==="tags"&&state.tagSelection.length===1?state.tagSelection[0]:null;
  state.activeSmartView=restoredSmartView?.name||null;
  state.search=fromHistory&&typeof saved?.search==="string"?saved.search.slice(0,300):"";
  state.searchKeyboardIndex=-1;
  state.renderLimit=fromHistory&&Number.isSafeInteger(saved?.renderLimit)?
    Math.min(20000,Math.max(100,saved.renderLimit)):100;
  $("#search").value=state.search;
  if(view==="node"&&id!==null)expandLineage(id);
  render();
  if(!navigationReady)return;
  if(fromHistory){
    const y=Number.isFinite(saved?.scrollY)?Math.max(0,Math.min(10000000,saved.scrollY)):0;
    requestAnimationFrame(()=>window.scrollTo({top:y,behavior:"instant"}));
  }else{
    window.history.pushState({...navigationSnapshot(),scrollY:0},"",routeUrl(state.view,state.selected));
    window.scrollTo({top:0,behavior:"instant"});
  }
}

function locateNode(id){
  const node=byId(id);
  if(!node)return;
  const parent=node.parent_id??null;
  const siblings=children(parent),index=siblings.findIndex(item=>item.id===id);
  if(index<0)return;
  const limit=Math.ceil((index+1)/100)*100;
  setView(parent===null?"all":"node",parent);
  if(limit>state.renderLimit){state.renderLimit=limit;render(true);rememberNavigation()}
  requestAnimationFrame(()=>{
    const card=document.getElementById(`folderhub-entry-${id}`);
    if(!card)return;
    card.classList.add("is-located");
    card.scrollIntoView({block:"center",behavior:"auto"});
    restoreCardFocus(id,null);
    window.setTimeout(()=>card.classList.remove("is-located"),3600);
  });
}
const TYPE_LABEL = {root:"根模块",group:"普通模块",leaf:"叶子模块"};
const iconFor = n => ICONS[n.icon] || ICONS.folder;
const coverUrl = n => `/api/nodes/${n.id}/image?v=${encodeURIComponent(n.updated_at||"")}`;

function toggleBranch(id){
  if(state.expanded.has(id))state.expanded.delete(id);else state.expanded.add(id);
  navTreeDataVersion++;
  saveTreeState();renderNav();
  // Keep keyboard focus on the branch toggle after the subtree is replaced.
  $("#treeNav").querySelector('[data-toggle="'+id+'"]')?.focus({preventScroll:true});
}
function renderNav(){
  const roots=children(null);
  $("#rootCount").textContent=roots.length;
  $("#tagCount").textContent=indexedTagCount;
  document.querySelectorAll("#specialNav [data-view]").forEach(el=>el.classList.toggle("active",state.view===el.dataset.view));
  const tree=$("#treeNav");
  if(navTreeRenderedVersion!==navTreeDataVersion){
    const walk=(nodes) => nodes.map(n=>{
      const sub=children(n.id), expand=sub.length>0 && state.expanded.has(n.id), isLeaf=n.node_type==="leaf";
      return `<div class="tree-branch" role="group">
        <div class="tree-row">
          ${sub.length?`<button type="button" class="tree-toggle" data-toggle="${n.id}" aria-expanded="${expand}" aria-label="${expand?'折叠':'展开'} ${h(n.title)}"><span class="tree-chevron ${expand?'is-open':''}">›</span></button>`
            :'<span class="tree-spacer" aria-hidden="true"></span>'}
          <button type="button" class="tree-item" data-node="${n.id}" title="${h(n.title)} (${TYPE_LABEL[n.node_type]||'模块'})">
            <span class="tree-folder" aria-hidden="true">${h(iconFor(n))}</span>
            <span class="tree-text">${h(n.title)}</span>${isLeaf?'<span class="tree-leaf-mark" title="关联的文件夹">↗</span>':''}
          </button>
        </div>${sub.length&&expand?`<div class="tree-children" role="group">${walk(sub)}</div>`:''}
      </div>`;
    }).join("");
    tree.innerHTML=walk(roots);
    navTreeRenderedVersion=navTreeDataVersion;
    navTreeActiveId=null;
  }
  const activeId=state.view==="node"?state.selected:null;
  if(navTreeActiveId!==activeId){
    tree.querySelector(".tree-row.active")?.classList.remove("active");
    if(activeId!==null){
      tree.querySelector('[data-node="'+activeId+'"]')?.closest(".tree-row")?.classList.add("active");
    }
    navTreeActiveId=activeId;
  }
  renderSavedViews();
  renderFolderGroups();
  renderWorkspaces();
}
function renderSavedViews(){
  const list=$("#smartViewNav"),section=$("#smartViewSection");
  section.classList.toggle("hidden",!state.savedViews.length);
  $("#smartViewCount").textContent=String(state.savedViews.length);
  list.innerHTML=state.savedViews.map((view,index)=>{
    const desc=`${view.mode==="all"?"全部匹配":"任一匹配"} · 包含 ${view.includes.length} · 排除 ${view.excludes.length}`;
    return `<button type="button" class="nav-item saved-view-link ${state.view==="tags"&&state.activeSmartView===view.name?"active":""}" data-saved-view="${index}" title="${h(desc)}：${h(view.name)}"><span>◇</span><span class="saved-view-title">${h(view.name)}</span><span class="saved-view-counter">${view.includes.length+view.excludes.length}</span></button>`;
  }).join("");
}
function renderFolderGroups(){
  const section=$("#folderGroupSection"),list=$("#folderGroupNav");
  section.classList.toggle("hidden",!state.folderGroups.length);
  $("#folderGroupCount").textContent=String(state.folderGroups.length);
  list.innerHTML=state.folderGroups.map((group,index)=>{
    const present=group.members.filter(id=>Boolean(byId(id)?.folder_path)).length;
    const desc=`已关联 ${present} / ${group.members.length} 个目录 · 点击打开工作组`;
    return `<div class="folder-group-row">
      <button type="button" class="nav-item folder-group-launch" data-group-open="${index}" title="${h(desc)}" ${state.groupBusy?"disabled":""}><span aria-hidden="true">◈</span><span class="folder-group-name">${h(group.name)}</span><span class="folder-group-members">${present}/${group.members.length}</span></button>
      <button type="button" class="folder-group-command" data-group-rename="${index}" title="重命名 ${h(group.name)}" aria-label="重命名工作组 ${h(group.name)}" ${state.groupBusy?"disabled":""}>✎</button>
      <button type="button" class="folder-group-command" data-group-delete="${index}" title="删除工作组（不删除文件夹）" aria-label="删除工作组 ${h(group.name)}" ${state.groupBusy?"disabled":""}>×</button>
    </div>`;
  }).join("");
}
function renderWorkspaces(){
  $("#workspaceCount").textContent=String(state.workspaces.length);
  $("#workspaceNav").innerHTML=state.workspaces.map((item,index)=>{
    const present=item.members.filter(id=>Boolean(byId(id))).length;
    return `<div class="workspace-nav-row">
      <button type="button" class="nav-item workspace-link ${state.view==="workspace"&&state.activeWorkspace===item.name?"active":""}" data-workspace-open="${index}" title="${h(item.name)} · ${present}/${item.members.length} 个模块">
        <span aria-hidden="true">▣</span><span class="workspace-nav-name">${h(item.name)}</span><span class="workspace-nav-count">${present}/${item.members.length}</span>
      </button>
      <button type="button" class="folder-group-command" data-workspace-edit="${index}" aria-label="编辑工作区 ${h(item.name)}" title="编辑工作区">✎</button>
      <button type="button" class="folder-group-command" data-workspace-delete="${index}" aria-label="删除工作区 ${h(item.name)}" title="删除工作区">×</button>
    </div>`;
  }).join("");
}
function workspaceOverviewCounts(item){
  const members=item.members.map(id=>byId(id));
  return {total:members.length,
    available:members.filter(Boolean).length,
    folders:members.filter(node=>Boolean(node?.folder_path)).length,
    missing:members.filter(node=>!node).length};
}
function renderWorkspaceResources(){
  const box=$("#workspaceResources");
  const active=state.view==="workspace"&&!state.search.trim();
  const item=active?state.workspaces.find(w=>w.name===state.activeWorkspace):null;
  box.classList.toggle("hidden",!item);
  if(!item){box.replaceChildren();return}
  const status=WORKSPACE_STATUS_NAMES[item.status]||WORKSPACE_STATUS_NAMES.planning;
  const links=(item.links||[]).filter(link=>validWorkspaceUrl(link.url));
  const info=workspaceOverviewCounts(item);
  const switcher='<div class="workspace-quick-switch"><label for="workspaceSwitcher">快速切换工作区</label>'
    +'<select id="workspaceSwitcher" data-workspace-switch aria-label="快速切换工作区">'
    +state.workspaces.map(w=>'<option value="'+h(w.name)+'" '+(w.name===item.name?'selected':'')+'>'+h(w.name)+'</option>').join("")
    +'</select></div>';
  const metrics='<div class="workspace-overview-metrics" aria-label="项目概览">'
    +'<span><strong>'+info.available+'</strong> / '+info.total+' 有效模块</span>'
    +'<span><strong>'+info.folders+'</strong> 个绑定目录</span>'
    +(info.missing?'<span class="workspace-missing-count"><strong>'+info.missing+'</strong> 项已失效</span>':"")
    +'</div>';
  box.innerHTML='<div class="workspace-resource-heading"><strong>项目概况</strong>'
    +'<span class="workspace-status-badge" data-workspace-status="'+h(item.status||"planning")+'">'+h(status)+'</span>'
    +'<span class="workspace-resource-empty">'+links.length+' 条资源链接</span></div>'
    +switcher+metrics
    +(links.length?'<nav class="workspace-resource-links" aria-label="项目资源">'
    +links.map(link=>'<a href="'+h(validWorkspaceUrl(link.url))+'" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer" title="'+h(link.url)+'">↗ '+h(link.name)+'</a>').join("")
    +'</nav>':'<span class="workspace-resource-empty">尚未添加资源链接，可点击「编辑工作区」保存论文、仓库、文档等网页入口。</span>');
}
function renderCrumb(){
  const bits=[`<button type="button" data-crumb="all">首页</button>`];
  if(state.search.trim()){
    bits.push('<span>›</span><strong>全局搜索</strong>');
    $("#breadcrumb").innerHTML=bits.join("");return;
  }
  if(state.view==="tags") bits.push(`<span>›</span><strong>标签筛选${state.activeTag?" · "+h(state.activeTag):""}</strong>`);
  if(state.view==="workspace") bits.push(`<span>›</span><strong>项目工作区 · ${h(state.activeWorkspace)}</strong>`);
  if(state.view==="node"){
    for(const n of ancestors(state.selected)){
      bits.push(`<span>›</span><button type="button" data-crumb="${n.id}">${h(n.title)}</button>`);
    }
  }
  $("#breadcrumb").innerHTML=bits.join("");
}
function filterTaggedNodes(nodes,includes,excludes,mode="any"){
  const need=new Set(includes),blocked=new Set(excludes);
  return nodes.filter(node=>{
    const tags=Array.isArray(node.tags)?node.tags:[];
    if(!tags.length)return false;
    if(tags.some(tag=>blocked.has(tag)))return false;
    if(!need.size)return true;
    return mode==="all"?[...need].every(tag=>tags.includes(tag)):
      tags.some(tag=>need.has(tag));
  });
}
function chooseTag(tag){
  const previouslySelected=state.tagSelection.includes(tag)||state.tagExcluded.includes(tag);
  if(tag&&!previouslySelected&&!state.nodes.some(node=>(node.tags||[]).includes(tag)))return;
  state.activeSmartView=null;
  if(state.view!=="tags")setView("tags");
  if(!tag){state.tagSelection=[];state.tagExcluded=[]}
  else{
    const include=state.tagPickMode==="include";
    const selected=include?state.tagSelection:state.tagExcluded;
    const opposite=include?state.tagExcluded:state.tagSelection;
    if(selected.includes(tag))selected.splice(selected.indexOf(tag),1);
    else{
      selected.push(tag);
      if(opposite.includes(tag))opposite.splice(opposite.indexOf(tag),1);
    }
  }
  state.activeTag=state.tagSelection.length===1?state.tagSelection[0]:null;
  state.renderLimit=100;state.searchKeyboardIndex=-1;
  renderSavedViews(); // Invalidate selected saved-view state, not entire sidebar.
  render(true);rememberNavigation();
}
function updateTagFilterMode(mode,value){
  if(state.view!=="tags" || state.search.trim())return;
  state.activeSmartView=null;
  if(mode==="match" && ["any","all"].includes(value))state.tagMatchMode=value;
  if(mode==="pick" && ["include","exclude"].includes(value))state.tagPickMode=value;
  state.renderLimit=100;state.searchKeyboardIndex=-1;
  renderSavedViews();
  render(true);rememberNavigation();
}

/* V3.5 — saved, portable smart filters (no filesystem operations). */
function validateSmartViewName(value){
  if(typeof value!=="string" || !value.trim() || value.trim().length>40 ||
     /[\x00-\x1f\x7f]/.test(value))
    throw new Error("名称必须是 1—40 个字符，不能包含控制字符");
  return value.trim();
}
function smartViewDefinition(name){
  return {name,includes:[...state.tagSelection],excludes:[...state.tagExcluded],
    mode:state.tagMatchMode};
}
function openSmartView(index){
  const view=state.savedViews[index];
  if(!view)return;
  setView("tags");
  // Preserve saved conditions even when an original tag is no longer assigned
  // to any module: they will match again once the label is restored.
  state.tagSelection=[...view.includes];
  state.tagExcluded=[...view.excludes];
  state.tagMatchMode=view.mode;
  state.tagPickMode="include";
  state.activeTag=view.includes.length===1?view.includes[0]:null;
  state.activeSmartView=view.name;
  render();rememberNavigation();
}
async function editSavedViews(action){
  if(state.view!=="tags" || state.search.trim())return;
  const previous=state.savedViews,previousName=state.activeSmartView;
  let changed;
  if(action==="save"){
    if(!state.tagSelection.length&&!state.tagExcluded.length){
      toast("请先选择需要保存的标签条件",true);return;
    }
    const input=prompt("为当前标签组合命名（最多 40 字）：",state.activeSmartView||"");
    if(input===null)return;
    let name;
    try{name=validateSmartViewName(input)}catch(e){toast(e.message,true);return}
    const index=previous.findIndex(view=>view.name.toLocaleLowerCase()===name.toLocaleLowerCase());
    if(index>=0 && !confirm(`智能收藏夹「${previous[index].name}」已存在，覆盖原有筛选条件吗？`))return;
    if(index<0&&previous.length>=24){toast("最多保存 24 个智能收藏夹",true);return}
    changed=previous.map(view=>({...view}));
    if(index>=0)changed[index]=smartViewDefinition(name);
    else changed.push(smartViewDefinition(name));
    state.activeSmartView=name;
  }else if(action==="rename" || action==="delete"){
    const index=previous.findIndex(view=>view.name===state.activeSmartView);
    if(index<0)return;
    changed=previous.map(view=>({...view}));
    if(action==="rename"){
      const input=prompt("智能收藏夹的新名称：",previous[index].name);
      if(input===null)return;
      let name;
      try{name=validateSmartViewName(input)}catch(e){toast(e.message,true);return}
      if(previous.some((view,i)=>i!==index&&view.name.toLocaleLowerCase()===name.toLocaleLowerCase())){
        toast("已有同名智能收藏夹",true);return;
      }
      changed[index]={...changed[index],name};
      state.activeSmartView=name;
    }else{
      if(!confirm(`删除智能收藏夹「${previous[index].name}」？\n不会删除模块、标签或真实文件夹。`))return;
      changed.splice(index,1);
      state.activeSmartView=null;
    }
  }else return;
  state.savedViews=changed;
  const success=await persistProjectSettings();
  if(!success){
    state.savedViews=previous;
    state.activeSmartView=previousName;
    render();return;
  }
  render();rememberNavigation();
  toast(action==="save"?"智能收藏夹已保存":action==="rename"?"智能收藏夹已重命名":"智能收藏夹已删除");
}

function renderTagFilters(){
  const box=$("#tagFilters"),show=state.view==="tags"&&!state.search.trim();
  box.classList.toggle("hidden",!show);if(!show)return;
  const counts=new Map();
  for(const n of state.nodes)for(const tag of n.tags||[])counts.set(tag,(counts.get(tag)||0)+1);
  const ordered=[...counts].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0],"zh-CN"));
  const subset=ordered.slice(0,80);
  const selectedTags=[...state.tagSelection,...state.tagExcluded];
  for(const tag of selectedTags){
    if(subset.some(([name])=>name===tag))continue;
    const row=ordered.find(([name])=>name===tag);
    subset.push(row||[tag,0]);
  }
  const include=state.tagSelection,exclude=state.tagExcluded;
  const mode=state.tagMatchMode, pick=state.tagPickMode;
  const summary=include.length||exclude.length?
    `已包含 ${include.length} 项 · 已排除 ${exclude.length} 项`:
    "当前显示全部已标记模块";
  box.innerHTML=`<div class="tag-filter-toolbar" role="group" aria-label="标签组合筛选模式">
    <span class="tag-filter-label">匹配</span>
    <button type="button" class="tag-mode ${mode==="any"?"active":""}" data-tag-match="any" aria-pressed="${mode==="any"}">任一（OR）</button>
    <button type="button" class="tag-mode ${mode==="all"?"active":""}" data-tag-match="all" aria-pressed="${mode==="all"}">全部（AND）</button>
    <span class="tag-filter-separator" aria-hidden="true"></span>
    <span class="tag-filter-label">选择标签</span>
    <button type="button" class="tag-mode ${pick==="include"?"active":""}" data-tag-pick="include" aria-pressed="${pick==="include"}">＋ 包含</button>
    <button type="button" class="tag-mode ${pick==="exclude"?"active":""}" data-tag-pick="exclude" aria-pressed="${pick==="exclude"}">− 排除（NOT）</button>
    <button type="button" class="tag-mode tag-reset" data-tag-clear="1" ${!include.length&&!exclude.length?"disabled":""}>清空条件</button>
  </div>
  <p class="tag-filter-summary" role="status">${h(summary)} · 点击下方标签可切换当前选择状态。</p>
  <div class="smart-view-actions" role="group" aria-label="智能收藏夹管理">
    <button type="button" class="tag-mode smart-save" data-smart-action="save" ${!include.length&&!exclude.length?"disabled":""}>◇ 保存当前组合</button>
    ${state.activeSmartView?`<span class="smart-active" title="${h(state.activeSmartView)}">已打开：${h(state.activeSmartView)}</span><button type="button" class="tag-mode" data-smart-action="rename">重命名</button><button type="button" class="tag-mode" data-smart-action="delete">删除收藏夹</button>`:""}
  </div>
  <div class="tag-filter-options" role="group" aria-label="标签列表">
    <button type="button" class="tag-choice ${!include.length&&!exclude.length?"active":""}" data-tag-filter="" aria-pressed="${!include.length&&!exclude.length}">全部标签</button>
    ${subset.map(([tag,n])=>{
      const yes=include.includes(tag),no=exclude.includes(tag);
      return `<button type="button" class="tag-choice ${yes?"included active":no?"excluded":""}" data-tag-filter="${h(tag)}" aria-pressed="${yes||no}" title="${yes?"已包含":no?"已排除":"点击以"+(pick==="include"?"包含":"排除")}：${h(tag)}">${no?"−":yes?"✓":"⌗"} ${h(tag)} <span>${n}</span></button>`;
    }).join("")}
  </div>`;
  if(state.tagSelection.length===1 && !state.tagExcluded.length)
    box.insertAdjacentHTML("beforeend",'<button type="button" class="tag-choice tag-manage" data-tag-rename="1" title="重命名或合并所选标签">✎ 重命名/合并</button>');
  if(ordered.length>80)
    box.insertAdjacentHTML("beforeend",'<span class="tag-overflow">仅显示使用较多的 80 个标签，其他标签可通过全局搜索查找</span>');
}
function card(n,reorderable=false,keyboardActive=false){
  const childCount=children(n.id).length;
  const resourceKind=n.resource_kind||'folder';
  const resourceTarget=resourceKind==='folder'?n.folder_path:n.resource_target;
  const resourceLabel=resourceKind==='file'?'文件':resourceKind==='url'?'网页':'文件夹';
  const linked=!!resourceTarget;
  const leaf=n.node_type==="leaf";
  const lineage=ancestors(n.id).map(a=>a.title).join(" / ");
  const contextText=state.search?`所属：${lineage}`:"";
  const listContext=state.layout==="list" && contextText?
    `<span class="list-card-context" title="${h(contextText)}">${highlightSearch(contextText,state.search)}</span>`:"";
  const tags=Array.isArray(n.tags)?n.tags:[];
  const tagChips=tags.length?`<span class="card-tags" title="${h(tags.join("、"))}">${tags.slice(0,3).map(tag=>`<span class="card-tag">⌗ ${state.search?highlightSearch(tag,state.search):h(tag)}</span>`).join("")}${tags.length>3?`<span class="card-tag">+${tags.length-3}</span>`:""}</span>`:"";
  const primaryTitle=leaf?"打开资源":"进入此模块";
  return `<article class="entry-card ${leaf?"is-leaf":"is-container"} ${state.openingIds.has(n.id)?"is-opening":""} ${state.selectedIds.has(n.id)?"is-selected":""} ${keyboardActive?"keyboard-active":""}" id="folderhub-entry-${n.id}" data-id="${n.id}" tabindex="0" aria-label="${h(n.title)}，右键打开快捷菜单">
    <div class="card-cover tone-${n.id%6} ${n.has_image?'with-image':'with-icon'}" aria-hidden="true">
      ${n.has_image?`<img class="cover-image" src="${coverUrl(n)}" loading="lazy" alt="">`:`<span class="cover-emoji">${h(iconFor(n))}</span><span class="cover-decoration"></span>`}
      <span class="cover-type">${(leaf?resourceLabel:TYPE_LABEL[n.node_type]||"模块")}</span>
    </div>
    <div class="card-head"><span class="folder-icon ${linked?'':'unlinked'}">${h(iconFor(n))}</span>
      <div class="card-actions">
        ${state.selectMode?`<button type="button" class="card-select" data-action="select" data-id="${n.id}" aria-pressed="${state.selectedIds.has(n.id)}" aria-label="${state.selectedIds.has(n.id)?'取消选择':'选择'} ${h(n.title)}">${state.selectedIds.has(n.id)?'✓':'○'}</button>`:''}
        ${reorderable && !state.selectMode?`<button type="button" class="small-action sort-grip" draggable="true" data-drag="${n.id}" title="拖动调整同级顺序，也可使用上下箭头键" aria-label="移动 ${h(n.title)}：拖动排序或按上下箭头键">⠿</button>`:""}
        ${!state.selectMode?`<button type="button" class="small-action card-more" title="更多操作" aria-label="更多操作：${h(n.title)}" data-action="menu" data-id="${n.id}">⋯</button>`:''}
        <button title="编辑模块" class="small-action" data-action="edit" data-id="${n.id}">✎</button>
        <button title="移除模块（不会删除真实文件夹）" class="small-action" data-action="delete" data-id="${n.id}">×</button>
      </div>
    </div>
    <button type="button" class="card-primary" data-action="primary" data-id="${n.id}" title="${primaryTitle}">
      <strong>${state.search?highlightSearch(n.title,state.search):h(n.title)}</strong><span class="type-chip ${n.node_type}">${(leaf?resourceLabel:TYPE_LABEL[n.node_type]||'模块')}</span>
      <span class="path" title="${h(resourceTarget||lineage)}">${state.search?highlightSearch(linked?resourceTarget:(leaf?'未设置有效资源':`${childCount} 个子模块`),state.search):h(linked?resourceTarget:(leaf?'未设置有效资源':`${childCount} 个子模块`))}</span>
      ${listContext}${tagChips}</button>
    ${state.search && state.layout!=="list"?`<div class="entry-lineage" title="${h(lineage)}">⌁ ${highlightSearch(lineage,state.search)}</div>`:''}
    <div class="card-bottom"><span class="pill ${linked?'linked':''}">${leaf?`● ${resourceLabel}入口`:`${childCount} 个子模块`}</span>
      <div class="card-links">${state.search && !state.selectMode?`<button type="button" data-action="locate" data-id="${n.id}" title="定位到原目录，不打开文件夹">⌖ 定位</button>`:""}${!leaf?`<button data-action="enter" data-id="${n.id}">进入 ›</button>`:''}
        ${linked?`<button data-action="open" data-id="${n.id}">打开 ↗</button>`:''}
        ${linked && state.layout==="list"?`<button type="button" data-action="copy-path" data-id="${n.id}" title="复制资源地址">复制地址</button>`:''}
        ${!leaf?`<button data-action="child" data-id="${n.id}">＋ 子模块</button>`:''}
      </div></div>
  </article>`;
}
function emptyView(){
  const searching=!!state.search;
  return `<div class="empty-state"><div class="empty-art">${searching?'⌕':'▤'}</div><h3>${searching?'没有找到匹配的文件夹':'还没有模块'}</h3>
    <p>${searching?'换个名称或路径关键词试试':'点击“新建模块”，建立你的第一层文件夹导航。'}</p>
    ${searching?'':`<button class="primary-btn" data-action="empty-create">＋ 创建模块</button>`}</div>`;
}
// Coalesce bursts of browser input events into one frame. Keyboard navigation
// can flush the pending frame synchronously, preserving its focus semantics.
let searchRenderFrame=null;
function flushSearchRender(){
  if(searchRenderFrame!==null){
    cancelAnimationFrame(searchRenderFrame);
    searchRenderFrame=null;
  }
  render(true);rememberNavigation();
}
function queueSearchRender(){
  if(searchRenderFrame!==null)return;
  searchRenderFrame=requestAnimationFrame(()=>{
    searchRenderFrame=null;
    render(true);rememberNavigation();
  });
}
function searchAll(term){
  const query=String(term).trim().toLocaleLowerCase();
  if(!query)return [];
  if(cachedSearch?.query===query)return cachedSearch.result;
  const words=query.split(/\s+/).filter(Boolean);
  const result=searchRecords.filter(item=>words.every(word=>item.body.includes(word)))
    .sort((a,b)=>{
      const aOwn=words.every(word=>a.own.includes(word))?0:1;
      const bOwn=words.every(word=>b.own.includes(word))?0:1;
      return aOwn-bOwn || a.node.title.localeCompare(b.node.title,"zh-CN");
    }).map(item=>item.node);
  cachedSearch={query,result};
  return result;
}
function render(skipNav=false){
  if((state.view==="node" && !byId(state.selected)) ||
     (state.view==="workspace"&&!state.workspaces.some(item=>item.name===state.activeWorkspace))){
    state.view="all";state.selected=null;state.activeWorkspace=null;
    if(navigationReady)window.history.replaceState(navigationSnapshot(),"",routeUrl("all"));
  }
  // Selection, layout and keystrokes change cards, not side navigation.
  if(!skipNav)renderNav();
  renderCrumb();
  renderWorkspaceResources();
  renderTagFilters();
  $("#newBtn").hidden=state.view==="workspace"&&!state.search.trim();
  $("#selectModeBtn").hidden=false;
  let display,sectionTitle;
  const searching=state.search.trim();
  if(searching){display=searchAll(searching);sectionTitle="全局搜索结果";}
  else if(state.view==="tags"){
    display=sorted(filterTaggedNodes(state.nodes,state.tagSelection,state.tagExcluded,state.tagMatchMode));
    sectionTitle=state.tagSelection.length||state.tagExcluded.length?"组合标签筛选":"全部已标记模块";
  }
  else if(state.view==="node"){
    const node=byId(state.selected);
    display=node.node_type==="leaf"?[node]:children(state.selected);
    sectionTitle=node.node_type==="leaf"?"当前文件夹":"下级模块";
  }
  else if(state.view==="workspace"){
    const workspace=state.workspaces.find(item=>item.name===state.activeWorkspace);
    display=workspace.members.map(id=>byId(id)).filter(Boolean);
    sectionTitle=workspace.name;
  } else{display=children(null);sectionTitle="根模块";}
  $("#sectionHeading").hidden=state.view==="all"&&!searching;
  $("#sectionTitle").textContent=sectionTitle;
  $("#sectionMeta").textContent=state.view==="workspace"&&!searching?
    (()=>{
      const item=state.workspaces.find(w=>w.name===state.activeWorkspace);
      const missing=item.members.length-display.length;
      return (item.description||"项目工作区 · 集中浏览，不会自动打开多个文件夹")+
        (missing?" · "+missing+" 个成员已删除，请编辑工作区修复":"");
    })():
    state.view==="tags"&&!searching?
    `跨目录匹配 ${display.length} 个模块 · 包含 ${state.tagSelection.length} 个，排除 ${state.tagExcluded.length} 个标签（${state.tagMatchMode==="all"?"AND":"OR"}）` :
    `共 ${display.length} 个项目 · ${searching?'搜索覆盖整个目录树，结果显示完整所属层级':'叶子模块直接打开文件资源管理器'}`;
  const canAddChild=state.view==="node"&&!searching&&byId(state.selected)?.node_type!=="leaf";
  $("#newBtnText").textContent=canAddChild?"新建子模块":"新建根模块";
  $("#searchHint").textContent=searching?`${display.length} 项结果`:"Ctrl K";
  $("#sectionOperations").innerHTML=state.view==="workspace"&&!searching?
    '<button type="button" data-action="launch-workspace" '+(workspaceLaunchBusy?'disabled':'')+'>▶ 一键启动</button><button type="button" data-action="edit-workspace">编辑工作区</button><button type="button" data-action="copy-workspace">复制工作区</button>':
    state.view==="node"&&!searching?
    `<button data-action="edit-current">编辑当前模块</button>`:
    "";
  $("#entries").className="entries"+(state.layout==="list"?" list":"");
  const reorderable=!state.selectMode && !searching && (state.view==="all" || (state.view==="node" && byId(state.selected)?.node_type!=="leaf"));
  const page=display.slice(0,state.renderLimit);
  state.visibleIds=page.map(n=>n.id);
  if(!searching || state.searchKeyboardIndex >= display.length)state.searchKeyboardIndex=-1;
  $("#entries").classList.toggle("selection-mode",state.selectMode);
  $("#entries").innerHTML=display.length?page.map((n,index)=>card(n,reorderable,Boolean(searching)&&index===state.searchKeyboardIndex)).join("")+
    (display.length>page.length?`<div class="load-more"><span>已显示 ${page.length} / ${display.length} 项</span><button type="button" class="outline-btn" data-action="load-more">加载更多模块 ↓</button></div>`:""):
      emptyView();
  updateBatchBar();
}

// Reorder only siblings. Favorites and global search are intentionally read-only lists.
function canReorder(){
  return !state.selectMode && !state.search.trim() && (state.view==="all" ||
    (state.view==="node" && byId(state.selected)?.node_type!=="leaf"));
}
function reorderIds(ids, moved, anchor, after=false){
  const origin=ids.indexOf(moved), target=ids.indexOf(anchor);
  if(origin<0||target<0||origin===target)return ids.slice();
  const result=ids.slice();
  result.splice(origin,1);
  result.splice(result.indexOf(anchor)+(after?1:0),0,moved);
  return result;
}
function clearDragState(){
  state.draggingId=null;
  document.querySelectorAll("#entries .drag-origin, #entries .drag-before, #entries .drag-after")
    .forEach(el=>el.classList.remove("drag-origin","drag-before","drag-after"));
}
function dropAfter(card,event){
  const rect=card.getBoundingClientRect();
  return state.layout==="list" ? event.clientY>=rect.top+rect.height/2 :
    (event.clientY<rect.top+rect.height*.25 ? false :
      event.clientY>rect.bottom-rect.height*.25 ? true : event.clientX>=rect.left+rect.width/2);
}
async function saveSortOrder(nextIds,focusId=null){
  if(state.sorting||!canReorder())return;
  const parentId=state.view==="all"?null:state.selected;
  const existing=children(parentId).map(n=>n.id);
  if(nextIds.length!==existing.length || nextIds.every((id,i)=>id===existing[i]))return;
  state.sorting=true;
  try{
    await mutate("POST","/api/order",{parent_id:parentId,ids:nextIds});
    await refresh();
    if(focusId!==null)document.querySelector(`#entries [data-drag="${focusId}"]`)?.focus();
    toast("顺序已保存");
  }catch(e){toast("排序失败："+e.message,true);await refresh().catch(()=>{});}
  finally{state.sorting=false}
}
async function moveOne(id,direction){
  if(!canReorder())return;
  const parent=state.view==="all"?null:state.selected;
  const ids=children(parent).map(n=>n.id),from=ids.indexOf(id),to=from+direction;
  if(from<0||to<0||to>=ids.length)return;
  return saveSortOrder(reorderIds(ids,id,ids[to],direction>0),id);
}
function bindSorting(){
  const entries=$("#entries");
  entries.addEventListener("dragstart",event=>{
    const grip=event.target.closest("[data-drag]");
    if(!grip||!canReorder()||state.sorting){event.preventDefault();return}
    state.draggingId=Number(grip.dataset.drag);
    if(event.dataTransfer){event.dataTransfer.effectAllowed="move";event.dataTransfer.setData("text/plain",String(state.draggingId));}
    grip.closest(".entry-card")?.classList.add("drag-origin");
  });
  entries.addEventListener("dragover",event=>{
    if(state.draggingId===null||!canReorder())return;
    const card=event.target.closest(".entry-card"),id=Number(card?.dataset.id);
    if(!card||id===state.draggingId||!children(state.view==="all"?null:state.selected).some(n=>n.id===id))return;
    event.preventDefault();
    if(event.dataTransfer)event.dataTransfer.dropEffect="move";
    entries.querySelectorAll(".drag-before,.drag-after").forEach(el=>el.classList.remove("drag-before","drag-after"));
    card.classList.add(dropAfter(card,event)?"drag-after":"drag-before");
  });
  entries.addEventListener("drop",event=>{
    const card=event.target.closest(".entry-card"),moved=state.draggingId;
    if(!card||moved===null||!canReorder()){clearDragState();return}
    event.preventDefault();
    const anchor=Number(card.dataset.id),after=dropAfter(card,event);
    const ids=children(state.view==="all"?null:state.selected).map(n=>n.id);
    clearDragState();
    if(anchor!==moved)saveSortOrder(reorderIds(ids,moved,anchor,after));
  });
  entries.addEventListener("dragend",clearDragState);
  entries.addEventListener("keydown",event=>{
    const grip=event.target.closest("[data-drag]");
    if(!grip||!canReorder()||!["ArrowUp","ArrowDown"].includes(event.key))return;
    event.preventDefault();
    moveOne(Number(grip.dataset.drag),event.key==="ArrowUp"?-1:1);
  });
}

function updateEntryType(){
  const t=$("#entryType").value;
  const parentSelect=$("#entryParent");
  if(t==="root")parentSelect.value="";
  else if(!parentSelect.value){
    const first=parentSelect.querySelector('option[value]:not([value=""])');
    if(first)parentSelect.value=first.value;
  }
  parentSelect.disabled=t==="root";
  $("#entryParentRow").classList.toggle("hidden",t==="root");
  const node=state.editing===null?null:byId(state.editing);
  const hasLegacyPath=!!node?.folder_path && node.node_type!=="leaf" && node.node_type===t;
  const kind=$("#entryResourceKind").value;
  $("#entryKindRow").classList.toggle("hidden",t!=="leaf");
  $("#entryTargetRow").classList.toggle("hidden",t!=="leaf"||kind==="folder");
  $("#entryPathRow").classList.toggle("hidden",!(t==="leaf"&&kind==="folder")&&!hasLegacyPath);
  $("#entryPathRequired").textContent=t==="leaf"&&kind==="folder"?"（必填）":hasLegacyPath?"（旧版路径，仅保留使用）":"";
  $("#entryPath").required=t==="leaf"&&kind==="folder";
  $("#entryResourceTarget").required=t==="leaf"&&kind!=="folder";
  $("#entryTargetLabel").textContent=kind==="file"?"本地文件绝对路径":"网页 URL";
  $("#entryResourceTarget").placeholder=kind==="file"?"例如 D:\\Research\\paper.pdf":"https://example.com/";
  $("#entryTypeHelp").textContent=t==="root"?"顶层分类，只能建在目录最上层。":
    t==="group"?"用于继续划分子模块，可无限嵌套。":
    "最末级文件夹入口：必须关联一个文件夹，不能添加子模块。";
}
function editDialog(id=null,parentId=undefined){
  state.editing=id;
  const node=id===null?null:byId(id);
  const defaultParent=node?node.parent_id:(parentId!==undefined?parentId:(state.view==="node"&&byId(state.selected)?.node_type!=="leaf"?state.selected:null));
  if(!node && defaultParent!==null && byId(defaultParent)?.node_type==="leaf"){
    toast("叶子模块不能添加子模块",true);return;
  }
  $("#dialogTitle").textContent=node?"编辑模块":"新建模块";
  $("#entryName").value=node?.title||"";
  $("#entryPath").value=node?.folder_path||"";
  $("#entryResourceKind").value=node?.resource_kind||"folder";
  $("#entryResourceTarget").value=node?.resource_target||"";
  $("#entryTags").value=(node?.tags||[]).join("，");
  $("#entryIcon").value=node?.icon||"folder";
  state.pendingCover=null;state.removeCover=false;
  $("#entryCoverFile").value="";
  syncCoverPreview();
  $("#entryType").value=node?.node_type||(defaultParent===null?"root":"group");
  const disabled = node?descendants(node.id):new Set();
  const options=[`<option value="">顶级目录（仅根模块）</option>`];
  const walk=(nodes,depth)=>nodes.forEach(n=>{
    if(disabled.has(n.id)||n.node_type==="leaf")return;
    options.push(`<option value="${n.id}">${h("　".repeat(depth)+n.title)}</option>`);
    walk(children(n.id),depth+1);
  });walk(children(null),0);
  $("#entryParent").innerHTML=options.join("");
  $("#entryParent").value=defaultParent===null?"":String(defaultParent);
  updateEntryType();
  $("#dialogLayer").classList.remove("hidden");
  $("#entryName").focus();
}
function closeDialog(){ $("#dialogLayer").classList.add("hidden");state.editing=null;state.pendingCover=null;state.removeCover=false; }
function syncCoverPreview(){
  const preview=$("#entryCoverPreview"), node=state.editing===null?null:byId(state.editing);
  const url=state.pendingCover||(node?.has_image&&!state.removeCover?coverUrl(node):null);
  if(url){preview.replaceChildren();const img=document.createElement("img");img.src=url;img.alt="模块封面预览";preview.appendChild(img);}
  else {preview.replaceChildren();const glyph=document.createElement("span");glyph.textContent=ICONS[$("#entryIcon").value]||ICONS.folder;glyph.className="cover-preview-emoji";preview.appendChild(glyph);}
  $("#removeCover").disabled=!url;
}
async function handleCoverFile(file){
  if(!file)return;
  if(!["image/jpeg","image/png","image/webp"].includes(file.type)){toast("只支持 PNG、JPG、WebP 图片",true);return}
  if(file.size>2*1024*1024){toast("单张图片不能超过 2 MB",true);return}
  try{
    const dataUrl=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(file)});
    state.pendingCover=dataUrl;state.removeCover=false;syncCoverPreview();
  }catch(_){toast("读取图片失败，请重新选择",true)}
}

async function submitDialog(event){
  event.preventDefault();
  const type=$("#entryType").value;
  const payload={title:$("#entryName").value,node_type:type,icon:$("#entryIcon").value,
    folder_path:(type==="leaf"&&$("#entryResourceKind").value==="folder") ||
      (type!=="leaf"&&!$("#entryPathRow").classList.contains("hidden"))?$("#entryPath").value:null,
    resource_kind:type==="leaf"?$("#entryResourceKind").value:"folder",
    resource_target:type==="leaf"&&$("#entryResourceKind").value!=="folder"?$("#entryResourceTarget").value:null,
    parent_id:type==="root"?null:($("#entryParent").value?Number($("#entryParent").value):null),
    tags:$("#entryTags").value.split(/[,，;；\n]+/).map(x=>x.trim()).filter(Boolean)};
  const button=$("#submitEntry");button.disabled=true;
  try {
    const savedId=state.editing;
    let created;
    if(savedId!==null)await mutate("PATCH",`/api/nodes/${savedId}`,payload);
    else created=await mutate("POST","/api/nodes",payload);
    const actualId=savedId??created.id;
    // Keep current node edits if image upload fails so the cover can be retried.
    if(state.pendingCover)await mutate("POST",`/api/nodes/${actualId}/image`,{data_url:state.pendingCover});
    else if(state.removeCover&&savedId!==null)await mutate("DELETE",`/api/nodes/${actualId}/image`,{});
    closeDialog();clearPathHealthResults("模块已更改，建议重新检查关联路径。");
    clearPathSuggestions("模块已更改，请重新分析路径迁移建议。");
    await refresh();
    if(savedId!==null)expandLineage(savedId);
    else if(type==="root"&&created?.id)state.expanded.add(created.id);
    else if(created?.id)expandLineage(created.id);
    saveTreeState();render();toast("模块已保存");
  }catch(e){toast(e.message,true)}finally{button.disabled=false}
}
async function openFolder(id){
  if(state.openingIds.has(id))return;
  state.openingIds.add(id);
  // Keep DOM nodes, keyboard focus and scroll position stable while Explorer
  // launches instead of rebuilding the whole sidebar and card grid twice.
  document.getElementById(`folderhub-entry-${id}`)?.classList.add("is-opening");
  try{
    await mutate("POST",`/api/nodes/${id}/open`);
    toast((byId(id)?.resource_kind||"folder")==="folder"?
      "已向 Windows 资源管理器发送打开指令":"已发送资源打开指令");
  }catch(e){toast(e.message,true)}
  finally{
    state.openingIds.delete(id);
    document.getElementById(`folderhub-entry-${id}`)?.classList.remove("is-opening");
  }
}
async function removeNode(id){
  const node=byId(id);if(!node)return;
  const count=descendants(id).size-1;
  if(!confirm("从导航中移除「"+node.title+"」"+(count?"及 "+count+" 个子模块":"")+
    "？\n\n不会影响磁盘文件夹。建议提前下载完整备份。"))return;
  try{
    await mutate("DELETE",`/api/nodes/${id}`);
    await refresh();
    toast("导航记录已移除，磁盘文件未受影响");
  }catch(e){toast(e.message,true)}
}
async function act(action,id){
  switch(action){
    case "primary":{if(state.selectMode){toggleSelected(id);break}const n=byId(id);if(n?.node_type==="leaf")await openFolder(id);else setView("node",id);break}
    case "select":toggleSelected(id);break;
    case "menu":{const card=[...document.querySelectorAll("#entries .entry-card")].find(x=>Number(x.dataset.id)===id);const bounds=card?.getBoundingClientRect();if(bounds)openCardMenu(id,bounds.right-235,bounds.top+42);break}
    case "open":await openFolder(id);break;
    case "locate":locateNode(id);break;
    case "copy-path":await copyFolderPath(id);break;
    case "enter":setView("node",id);break;
    case "child":if(byId(id)?.node_type!=="leaf")editDialog(null,id);else toast("叶子模块不能拥有子模块",true);break;
    case "edit":editDialog(id);break;
    case "delete":await removeNode(id);break;
    case "empty-create":editDialog();break;
    case "edit-current":editDialog(state.selected);break;
    case "launch-workspace":await launchActiveWorkspace();break;
    case "edit-workspace":openWorkspaceDialog(state.workspaces.findIndex(item=>item.name===state.activeWorkspace));break;
    case "copy-workspace":duplicateWorkspace(state.workspaces.findIndex(item=>item.name===state.activeWorkspace));break;
    case "load-more":{
      const previous=state.visibleIds.length;
      state.renderLimit+=100;
      render(true);rememberNavigation();
      const firstNew=state.visibleIds[previous];
      if(firstNew!==undefined)
        document.getElementById(`folderhub-entry-${firstNew}`)?.querySelector(".card-primary")?.focus({preventScroll:true});
      break;
    }
  }
}
// Bulk selection is limited to the current visible list, including search results.
function closeCardMenu(){
  const menu=$("#cardContextMenu");
  if(!menu)return;
  menu.classList.add("hidden");menu.replaceChildren();state.contextId=null;
}
function exitSelectMode(){
  state.selectMode=false;state.selectedIds.clear();closeCardMenu();
}
function toggleSelected(id){
  if(!state.selectMode||!state.visibleIds.includes(id)||state.batchBusy)return;
  if(state.selectedIds.has(id))state.selectedIds.delete(id);
  else if(state.selectedIds.size>=200){toast("一次最多选择 200 个模块",true);return}
  else state.selectedIds.add(id);
  render(true);
}

/* V4.1 — A workspace is a browsable collection of module IDs, separate from
   folder groups that bulk-open 2–8 Windows Explorer windows. */
let editingWorkspaceIndex=-1;
let workspaceDraftMembers=new Set();
let workspaceDraftLaunchIds=new Set();
let workspaceDraftLinks=[];
let workspaceLaunchBusy=false;
let workspaceSaving=false;
function validateWorkspaceName(value){
  const name=String(value??"").trim();
  if(!name||Array.from(name).length>40||/[\x00-\x1f\x7f]/.test(name))
    throw new Error("工作区名称必须是 1—40 字，不能包含控制字符");
  return name;
}
function movedWorkspaceMemberIds(ids,id,direction){
  const next=ids.slice(),index=next.indexOf(id),destination=index+direction;
  if((direction!==-1&&direction!==1)||index<0||destination<0||destination>=next.length)return next;
  [next[index],next[destination]]=[next[destination],next[index]];
  return next;
}
function moveWorkspaceDraftMember(id,direction){
  const before=[...workspaceDraftMembers],after=movedWorkspaceMemberIds(before,id,direction);
  if(before.every((value,index)=>value===after[index]))return;
  workspaceDraftMembers=new Set(after);
  renderWorkspaceMembers();
  $("#workspaceMemberList").querySelector('[data-workspace-move="'+id+'"][data-workspace-step="'+direction+'"]')?.focus();
}
function renderWorkspaceMembers(){
  const needle=$("#workspaceMemberSearch").value.trim().toLocaleLowerCase();
  const selected=[...workspaceDraftMembers];
  const matches=node=>!needle||(node.title+" "+(node.folder_path||"")+" "+ancestors(node.id).map(p=>p.title).join(" ")).toLocaleLowerCase().includes(needle);
  const remaining=state.nodes.filter(node=>!workspaceDraftMembers.has(node.id)&&matches(node)).sort((a,b)=>a.id-b.id);
  const page=remaining.slice(0,120);
  const checked=selected.map((id,index)=>{
    const node=byId(id);
    const label=node?node.title:"已删除模块 #"+id;
    const context=node?(ancestors(node.id).map(x=>x.title).join(" / ")||node.folder_path||"根模块"):"取消勾选以移除失效引用";
    return '<div class="workspace-member-row workspace-chosen-row '+(node?"":"workspace-member-missing")+'">'
      +'<label class="workspace-member-label"><input type="checkbox" data-workspace-member="'+id+'" checked><span>'+h(label)+'<small>'+h(context)+'</small></span></label>'
      +'<div class="workspace-member-order"><button type="button" data-workspace-move="'+id+'" data-workspace-step="-1" aria-label="将 '+h(label)+' 上移" title="上移" '+(index===0?"disabled":"")+'>↑</button>'
      +'<button type="button" data-workspace-move="'+id+'" data-workspace-step="1" aria-label="将 '+h(label)+' 下移" title="下移" '+(index===selected.length-1?"disabled":"")+'>↓</button></div></div>';
  });
  const available=page.map(node=>{
    const context=ancestors(node.id).map(x=>x.title).join(" / ")||node.folder_path||"根模块";
    return '<label class="workspace-member-row workspace-member-label"><input type="checkbox" data-workspace-member="'+node.id+'" '+(selected.length>=30?"disabled":"")+'>'
      +'<span>'+h(node.title)+'<small>'+h(context)+'</small></span></label>';
  });
  $("#workspaceMemberList").innerHTML=
    (checked.length?'<p class="workspace-member-heading">已选成员 · 顺序即工作区显示顺序</p>'+checked.join(""):"")
    +'<p class="workspace-member-heading">可添加模块</p>'
    +(available.length?available.join(""):'<p class="settings-note">没有其他匹配的模块。</p>')
    +(remaining.length>page.length?'<p class="settings-note">仅显示前 120 个匹配模块，请继续输入关键词缩小范围。</p>':"");
  $("#workspaceMemberSummary").textContent="已选择 "+selected.length+"/30 个模块；可添加候选 "+remaining.length+" 个。";
  for(const id of workspaceDraftLaunchIds)if(!workspaceDraftMembers.has(id))workspaceDraftLaunchIds.delete(id);
  renderWorkspaceLaunchChoices();
}
function renderWorkspaceLaunchChoices(){
  const ids=[...workspaceDraftMembers].filter(id=>byId(id)?.node_type==="leaf");
  const chosen=ids.filter(id=>workspaceDraftLaunchIds.has(id));
  $("#workspaceLaunchHint").textContent="已选 "+chosen.length+"/8 项；按工作区成员顺序依次打开。仅打开已勾选的文件夹、文件或网页。";
  $("#workspaceLaunchList").innerHTML=ids.length?ids.map(id=>{
    const node=byId(id),checked=workspaceDraftLaunchIds.has(id);
    const disabled=!checked&&chosen.length>=8;
    const kind=node.resource_kind==="url"?"网页":node.resource_kind==="file"?"文件":"文件夹";
    return '<label class="workspace-member-row workspace-launch-choice"><input type="checkbox" data-workspace-launch="'+id+'" '
      +(checked?'checked ':'')+(disabled?'disabled ':'')+'>'
      +'<span>'+h(node.title)+'<small>'+h(kind)+'</small></span></label>';
  }).join(""):'<p class="settings-note">选择工作区中的叶子模块后，可设置一键启动清单。</p>';
}
function showWorkspaceLaunchResult(data){
  $("#workspaceLaunchSummary").textContent="工作区「"+data.workspace+"」：成功 "+data.succeeded+" / "+data.attempted+" 项";
  $("#workspaceLaunchRows").innerHTML=data.results.map(item=>
    '<div class="group-report-row"><span>'+h(item.title)+'</span><span>'
      +(item.ok?'<strong>✓ 已发送打开请求</strong>':'<strong>✕ 启动失败</strong><small>'+h(item.error||"未知错误")+'</small>')
      +'</span></div>').join("");
  $("#workspaceLaunchLayer").classList.remove("hidden");
  $("#workspaceLaunchDone").focus();
}
function closeWorkspaceLaunchResult(){
  $("#workspaceLaunchLayer").classList.add("hidden");
}
async function launchActiveWorkspace(){
  if(workspaceLaunchBusy||state.view!=="workspace"||!state.activeWorkspace)return;
  const item=state.workspaces.find(w=>w.name===state.activeWorkspace);
  if(!item)return;
  const ids=item.launch_ids||[];
  if(!ids.length){toast("请先编辑工作区，在「一键启动清单」勾选需要打开的资源",true);return}
  // Confirm a frozen snapshot: a second tab may edit names, types, paths or
  // launch order while this page is open. The backend must match every field.
  const expectedItems=ids.map(id=>{
    const node=byId(id);
    const kind=node?.resource_kind||"folder";
    return {id,title:node?.title??null,kind:node?kind:null,
      target:node?(kind==="folder"?node.folder_path??null:node.resource_target??null):null};
  });
  const names=expectedItems.map(item=>item.title||"已删除模块 #"+item.id);
  if(!confirm("即将依次打开 "+ids.length+" 项资源：\n"+names.join("\n")
      +"\n\n只启动已选择的资源，不修改文件。是否继续？"))return;
  workspaceLaunchBusy=true;
  render(true);
  try{
    const result=await mutate("POST","/api/workspaces/launch",{name:item.name,expected_items:expectedItems});
    showWorkspaceLaunchResult(result);
  }catch(error){toast("启动工作区失败："+error.message,true)}
  finally{workspaceLaunchBusy=false;render(true)}
}
function movedWorkspaceLinkItems(links,index,direction){
  const next=links.map(link=>({...link})),target=index+direction;
  if(!Number.isInteger(index)||![-1,1].includes(direction)||
     index<0||index>=next.length||target<0||target>=next.length)return next;
  [next[index],next[target]]=[next[target],next[index]];
  return next;
}
function moveWorkspaceDraftLink(index,direction){
  const next=movedWorkspaceLinkItems(workspaceDraftLinks,index,direction);
  if(index<0||index>=workspaceDraftLinks.length||index+direction<0||
     index+direction>=workspaceDraftLinks.length||![-1,1].includes(direction))return;
  workspaceDraftLinks=next;
  renderWorkspaceLinkEditor();
  $("#workspaceLinkList").querySelector('[data-workspace-link-move="'+(index+direction)+'"][data-workspace-step="'+direction+'"]')?.focus();
}
function renderWorkspaceLinkEditor(){
  $("#workspaceLinkAdd").disabled=workspaceDraftLinks.length>=8;
  $("#workspaceLinkList").innerHTML=workspaceDraftLinks.map((link,index)=>
    '<div class="workspace-link-row">'
    +'<input type="text" maxlength="60" data-workspace-link-name="'+index+'" aria-label="资源名称 '+(index+1)+'" placeholder="例如：GitHub项目" value="'+h(link.name)+'">'
    +'<input type="url" maxlength="2048" data-workspace-link-url="'+index+'" aria-label="资源链接 '+(index+1)+'" placeholder="https://example.com/" value="'+h(link.url)+'">'
    +'<div class="workspace-link-order">'
    +'<button type="button" data-workspace-link-move="'+index+'" data-workspace-step="-1" aria-label="资源 '+(index+1)+' 上移" '+(index===0?'disabled':'')+'>↑</button>'
    +'<button type="button" data-workspace-link-move="'+index+'" data-workspace-step="1" aria-label="资源 '+(index+1)+' 下移" '+(index===workspaceDraftLinks.length-1?'disabled':'')+'>↓</button>'
    +'<button type="button" data-workspace-link-remove="'+index+'" aria-label="删除第 '+(index+1)+' 条资源">移除</button>'
    +'</div></div>').join("");
}
function validateWorkspaceDraftLinks(){
  if(workspaceDraftLinks.length>8)throw new Error("最多添加8条网页资源");
  const seen=new Set();
  return workspaceDraftLinks.map((link,index)=>{
    const name=link.name.trim(),url=link.url.trim();
    if(!name||Array.from(name).length>60||/[\x00-\x1f\x7f]/.test(name))
      throw new Error("第"+(index+1)+"条资源名称无效（1—60字）");
    const safeUrl=validWorkspaceUrl(url);
    if(!safeUrl)throw new Error("第"+(index+1)+"条资源必须是完整的 HTTP/HTTPS 地址，不能包含空白或账号密码");
    if(seen.has(safeUrl.toLocaleLowerCase()))throw new Error("资源链接不能重复");
    seen.add(safeUrl.toLocaleLowerCase());
    return {name,url:safeUrl};
  });
}
function openWorkspaceDialog(index=-1,initialMembers=null){
  if(workspaceSaving)return;
  const record=index>=0?state.workspaces[index]:null;
  if(index>=0&&!record)return;
  editingWorkspaceIndex=record?index:-1;
  workspaceDraftMembers=new Set(record?record.members:
    (initialMembers||[]).filter(id=>byId(id)).slice(0,30));
  workspaceDraftLaunchIds=new Set(record?.launch_ids||[]);
  $("#workspaceDialogTitle").textContent=record?"编辑项目工作区":"新建项目工作区";
  $("#workspaceName").value=record?.name||"";
  $("#workspaceDescription").value=record?.description||"";
  $("#workspaceStatus").value=record?.status||"planning";
  workspaceDraftLinks=(record?.links||[]).map(link=>({...link}));
  renderWorkspaceLinkEditor();
  $("#workspaceMemberSearch").value="";
  renderWorkspaceMembers();
  $("#workspaceLayer").classList.remove("hidden");
  $("#workspaceName").focus();
}
function closeWorkspaceDialog(){
  if(workspaceSaving)return;
  $("#workspaceLayer").classList.add("hidden");
  editingWorkspaceIndex=-1;
  workspaceDraftMembers=new Set();
  workspaceDraftLaunchIds=new Set();
  workspaceDraftLinks=[];
}
async function submitWorkspace(event){
  event.preventDefault();
  if(workspaceSaving)return;
  let name;
  try{name=validateWorkspaceName($("#workspaceName").value)}catch(e){toast(e.message,true);return}
  const description=$("#workspaceDescription").value;
  if(description.length>240||/[\x00-\x09\x0b-\x1f\x7f]/.test(description)){
    toast("项目说明不能超过 240 字或包含控制字符",true);return;
  }
  const ids=[...workspaceDraftMembers];
  if(ids.length<1||ids.length>30||ids.some(id=>!byId(id))){
    toast("请关联 1—30 个现有模块；如有失效模块，请先取消选择",true);return;
  }
  if(state.workspaces.some((item,i)=>i!==editingWorkspaceIndex&&item.name.toLocaleLowerCase()===name.toLocaleLowerCase())){
    toast("已有同名工作区",true);return;
  }
  if(editingWorkspaceIndex<0&&state.workspaces.length>=20){
    toast("最多保存20个工作区",true);return;
  }
  const status=$("#workspaceStatus").value;
  if(!WORKSPACE_STATUS_NAMES[status]){toast("请选择有效的项目状态",true);return}
  let links;
  try{links=validateWorkspaceDraftLinks()}catch(error){toast(error.message,true);return}
  const previous=state.workspaces;
  const updated=previous.map(item=>copyWorkspaceRecord(item));
  const launch_ids=ids.filter(id=>workspaceDraftLaunchIds.has(id));
  if(launch_ids.length>8||launch_ids.some(id=>byId(id)?.node_type!=="leaf")){
    toast("启动清单最多8项，且只能包含叶子资源",true);return;
  }
  const current={name,description,members:ids,status,links,launch_ids};
  if(editingWorkspaceIndex<0)updated.push(current);
  else updated[editingWorkspaceIndex]=current;
  workspaceSaving=true;
  $("#workspaceSave").disabled=true;
  state.workspaces=updated;
  try{
    if(!await persistProjectSettings()){
      state.workspaces=previous;render();return;
    }
    workspaceSaving=false;
    closeWorkspaceDialog();
    exitSelectMode();
    setView("workspace",name);
    toast("项目工作区已保存（不会修改真实文件）");
  }catch(e){state.workspaces=previous;toast("工作区保存失败："+e.message,true)}
  finally{workspaceSaving=false;$("#workspaceSave").disabled=false;render()}
}
function uniqueWorkspaceCopyName(original){
  const names=new Set(state.workspaces.map(item=>item.name.toLocaleLowerCase()));
  for(let i=1;i<=100;i++){
    const suffix=i===1?"（副本）":"（副本 "+i+"）";
    const name=Array.from(original).slice(0,40-Array.from(suffix).length).join("")+suffix;
    if(!names.has(name.toLocaleLowerCase()))return name;
  }
  throw new Error("找不到可用的副本名称，请先清理同名工作区");
}
function duplicateWorkspace(index){
  const item=state.workspaces[index];
  if(!item||workspaceSaving)return;
  if(state.workspaces.length>=20){toast("最多保存20个工作区，请先删除不用的工作区",true);return}
  const existing=item.members.filter(id=>byId(id));
  if(!existing.length){toast("原工作区没有可用模块，无法复制。请先修复成员",true);return}
  let name;
  try{name=uniqueWorkspaceCopyName(item.name)}catch(e){toast(e.message,true);return}
  openWorkspaceDialog(-1,existing);
  $("#workspaceDialogTitle").textContent="复制项目工作区";
  $("#workspaceName").value=name;
  $("#workspaceDescription").value=item.description;
  $("#workspaceStatus").value=item.status||"planning";
  workspaceDraftLinks=(item.links||[]).map(link=>({...link}));
  workspaceDraftLaunchIds=new Set(item.launch_ids||[]);
  renderWorkspaceLinkEditor();
  renderWorkspaceLaunchChoices();
  toast("已复制工作区内容，请检查名称、资源与模块后点击保存");
}
async function deleteWorkspace(index){
  const item=state.workspaces[index];
  if(!item||workspaceSaving)return;
  if(!confirm(`删除工作区「${item.name}」？仅删除工作区配置，不删除任何模块或真实文件。`))return;
  const old=state.workspaces;
  state.workspaces=old.filter((_,i)=>i!==index);
  if(!await persistProjectSettings()){state.workspaces=old;render();return}
  if(state.view==="workspace"&&state.activeWorkspace===item.name)setView("all");
  render();toast("工作区已删除，文件夹和模块均未删除");
}
/* V4.2 quick-add reuses the saved workspace IDs; it never accepts paths. */
let workspacePickerNodeId=null;
function closeWorkspacePicker(){
  if(workspaceSaving)return;
  $("#workspacePickerLayer").classList.add("hidden");
  workspacePickerNodeId=null;
}
function openWorkspacePicker(nodeId){
  const node=byId(nodeId);
  if(!node||workspaceSaving)return;
  closeCardMenu();
  if(!state.workspaces.length){
    openWorkspaceDialog(-1,[nodeId]);
    toast("尚无工作区，已为你预选该模块，请先新建工作区");
    return;
  }
  workspacePickerNodeId=nodeId;
  $("#workspacePickerSummary").textContent="将「"+node.title+"」加入哪个项目工作区？仅增加模块引用，不修改电脑中的文件。";
  $("#workspacePickerList").innerHTML=state.workspaces.map((item,index)=>{
    const exists=item.members.includes(nodeId),full=item.members.length>=30;
    const status=exists?"已关联":full?"已满（30项）":item.members.length+"/30项";
    return '<button type="button" class="workspace-picker-option" data-workspace-append="'+index+'" '+(exists||full?"disabled":"")+'>'
      +'<span>'+h(item.name)+'</span><small>'+h(status)+'</small></button>';
  }).join("");
  $("#workspacePickerLayer").classList.remove("hidden");
  const initial=$("#workspacePickerList").querySelector("button:not(:disabled)");
  (initial||$("#workspacePickerClose")).focus();
}
async function addNodeToWorkspace(index){
  const nodeId=workspacePickerNodeId,item=state.workspaces[index];
  if(!item||!byId(nodeId)||workspaceSaving||item.members.includes(nodeId)||item.members.length>=30)return;
  const before=state.workspaces;
  const after=before.map((w,i)=>i===index?
    {...copyWorkspaceRecord(w),members:[...w.members,nodeId]}:
    copyWorkspaceRecord(w));
  workspaceSaving=true;
  state.workspaces=after;
  try{
    if(!await persistProjectSettings()){
      state.workspaces=before;
      toast("加入工作区失败，原配置未变更",true);return;
    }
    workspaceSaving=false;
    closeWorkspacePicker();
    render();
    toast("已将模块加入「"+item.name+"」");
  }catch(error){
    state.workspaces=before;
    toast("加入工作区失败："+error.message,true);
  }finally{workspaceSaving=false;render()}
}
/* V3.8 — named groups of existing linked modules; nothing touches real folders. */
function validateFolderGroupName(value){
  if(typeof value!=="string"||!value.trim()||value.trim().length>40||
     /[\x00-\x1f\x7f]/.test(value))
    throw new Error("工作组名称须为 1—40 字且不能包含控制字符");
  return value.trim();
}
async function commitFolderGroupChange(next,successText){
  const previous=state.folderGroups;
  state.folderGroups=next;
  const saved=await persistProjectSettings();
  if(!saved){
    state.folderGroups=previous;
    render();return false;
  }
  render();
  toast(successText);
  return true;
}
async function saveSelectedFolderGroup(){
  if(state.batchBusy||state.groupBusy)return;
  const members=[...state.selectedIds];
  if(members.length<2||members.length>8){
    toast("请先选择 2—8 个需要一起打开的模块",true);return;
  }
  const invalid=members.filter(id=>!byId(id)?.folder_path);
  if(invalid.length){
    toast(`有 ${invalid.length} 个模块尚未关联文件夹，请先编辑并设置路径`,true);return;
  }
  const input=prompt("为文件夹工作组命名（2—8 个目录，最多 40 字）：");
  if(input===null)return;
  let name;
  try{name=validateFolderGroupName(input)}catch(e){toast(e.message,true);return}
  const previous=state.folderGroups;
  const index=previous.findIndex(group=>group.name.toLocaleLowerCase()===name.toLocaleLowerCase());
  if(index>=0 && !confirm(`工作组「${previous[index].name}」已存在。确定用当前选中的 ${members.length} 个目录替换原成员吗？`))return;
  if(index<0&&previous.length>=20){
    toast("最多保存 20 个工作组，请先删除不再需要的工作组",true);return;
  }
  const updated=previous.map(group=>({name:group.name,members:[...group.members]}));
  if(index>=0)updated[index]={name,members};
  else updated.push({name,members});
  if(await commitFolderGroupChange(updated,index>=0?"工作组目录已更新":"工作组已保存到侧栏")){
    exitSelectMode();render();
  }
}
async function renameFolderGroup(index){
  const group=state.folderGroups[index];
  if(!group||state.groupBusy)return;
  const input=prompt("修改工作组名称：",group.name);
  if(input===null)return;
  let name;
  try{name=validateFolderGroupName(input)}catch(e){toast(e.message,true);return}
  if(name===group.name)return;
  if(state.folderGroups.some((item,i)=>i!==index&&item.name.toLocaleLowerCase()===name.toLocaleLowerCase())){
    toast("已有同名工作组",true);return;
  }
  const updated=state.folderGroups.map((item,i)=>i===index?
    {name,members:[...item.members]}:{name:item.name,members:[...item.members]});
  await commitFolderGroupChange(updated,"工作组已重命名");
}
async function deleteFolderGroup(index){
  const group=state.folderGroups[index];
  if(!group||state.groupBusy)return;
  if(!confirm(`确定删除工作组「${group.name}」吗？\n只会移除快捷入口，不会删除任何模块或真实文件夹。`))return;
  await commitFolderGroupChange(state.folderGroups.filter((_,i)=>i!==index),"工作组已删除");
}
function closeGroupReport(){
  $("#groupResultLayer").classList.add("hidden");
}
function showFolderGroupReport(result){
  $("#groupResultTitle").textContent=`${result.group} · 打开结果`;
  $("#groupResultSummary").textContent=`成功打开 ${result.opened} 项，未打开 ${result.failed} 项。失败的目录不会影响其他目录。`;
  $("#groupResultRows").innerHTML=result.results.map(row=>
    `<div class="group-report-row ${row.ok?"success":"failure"}">
      <span aria-hidden="true">${row.ok?"✓":"!"}</span>
      <div><strong>${h(row.title)}</strong><small>${row.ok?"已发送 Windows 资源管理器打开指令":h(row.error||"打开失败")}</small></div>
    </div>`).join("");
  $("#groupResultLayer").classList.remove("hidden");
  $("#groupResultClose").focus();
}
async function openFolderGroup(index){
  const group=state.folderGroups[index];
  if(!group||state.groupBusy)return;
  const names=group.members.map(id=>byId(id)?.title||`已删除模块 #${id}`);
  const question=`打开工作组「${group.name}」中的 ${names.length} 个目录吗？\n\n${names.map((name,i)=>`${i+1}. ${name}`).join("\n")}\n\n仅打开已有绑定路径，不修改真实文件夹。`;
  if(!confirm(question))return;
  state.groupBusy=true;
  renderFolderGroups();updateBatchBar();
  try{
    const result=await mutate("POST","/api/groups/open",{name:group.name});
    try{
      await refresh();
    }catch(_){/* successful Explorer launches should still be reported */}
    showFolderGroupReport(result);
  }catch(error){toast("打开工作组失败："+error.message,true)}
  finally{state.groupBusy=false;renderFolderGroups();updateBatchBar()}
}

function updateBatchBar(){
  const bar=$("#bulkBar"),count=state.selectedIds.size;
  bar.classList.toggle("hidden",!state.selectMode);
  $("#bulkCount").textContent=`已选择 ${count} 项`;
  $("#selectModeBtn").setAttribute("aria-pressed",String(state.selectMode));
  $("#selectModeBtn").textContent=state.selectMode?"✓ 退出多选":"☑ 多选";
  for(const id of ["bulkTagAdd","bulkTagRemove","bulkDelete"]){$("#"+id).disabled=state.batchBusy||count===0}
  $("#bulkSaveGroup").disabled=state.batchBusy||state.groupBusy||count<2||count>8;
  $("#bulkSaveWorkspace").disabled=state.batchBusy||count<1||count>30;
  $("#bulkSelectAll").disabled=state.batchBusy||state.visibleIds.length===0;
  $("#bulkCancel").disabled=state.batchBusy;
}
function parseBulkTags(text){
  const tags=String(text??"").split(/[,，;；\n]+/).map(s=>s.trim()).filter(Boolean);
  if(!tags.length)throw new Error("请输入至少一个标签");
  if(tags.length>12||tags.some(t=>t.length>24))
    throw new Error("最多 12 个标签，每个最长 24 字");
  if(new Set(tags.map(t=>t.toLocaleLowerCase())).size!==tags.length)
    throw new Error("不能输入重复标签");
  return tags;
}
async function batchTags(action){
  if(state.batchBusy||!state.selectedIds.size)return;
  const ids=[...state.selectedIds];
  const raw=prompt(action==="add"?
    `向已选择的 ${ids.length} 个模块添加标签（逗号分隔）：`:
    `从已选择的 ${ids.length} 个模块移除标签（逗号分隔）：`);
  if(raw===null)return;
  let tags;
  try{tags=parseBulkTags(raw)}catch(e){toast(e.message,true);return}
  if(!confirm(`确认对 ${ids.length} 个模块${action==="add"?"添加":"移除"}标签 ${tags.join("、")} 吗？\n\n该操作不会移动或修改真实文件夹。`))return;
  state.batchBusy=true;updateBatchBar();
  try{
    const result=await mutate("POST","/api/tags/batch",{action,ids,tags});
    exitSelectMode();await refresh();
    toast(`标签${action==="add"?"添加":"移除"}完成：${result.changed} / ${result.selected} 个模块有变化`);
  }catch(e){toast("批量标签操作失败："+e.message,true)}
  finally{state.batchBusy=false;updateBatchBar()}
}
async function renameCurrentTag(){
  if(!state.activeTag)return;
  const old=state.activeTag;
  const raw=prompt(`将标签「${old}」改名为（输入已有标签将自动合并）：`,old);
  if(raw===null)return;
  const target=raw.trim();
  if(!target||target.length>24||/[,，;；\r\n\t]/.test(target)){
    toast("标签名必须是 1—24 字，且不能包含分隔符或控制字符",true);
    return;
  }
  if(target===old)return;
  if(!confirm(`将「${old}」重命名/合并为「${target}」？\n\n所有模块和回收站的同名标签都会更新，不会更改真实文件夹。`))return;
  try{
    const result=await mutate("POST","/api/tags/rename",{source:old,target});
    state.tagSelection=state.tagSelection.map(tag=>tag===old?target:tag);
    state.tagSelection=[...new Set(state.tagSelection)];
    state.tagExcluded=state.tagExcluded.map(tag=>tag===old?target:tag);
    state.tagExcluded=[...new Set(state.tagExcluded)];
    state.activeTag=state.tagSelection.length===1?state.tagSelection[0]:null;
    // A global label rename must update saved smart filters as well, including
    // those that are currently inactive. Merge duplicate names on collision.
    const rewritten=state.savedViews.map(view=>{
      const includes=[...new Set(view.includes.map(tag=>tag===old?target:tag))];
      const exclusions=[...new Set(view.excludes.map(tag=>tag===old?target:tag))]
        .filter(tag=>!includes.includes(tag));
      return {...view,includes,excludes:exclusions};
    });
    state.savedViews=rewritten;
    if(!await persistProjectSettings())
      toast("标签已重命名，但智能收藏夹同步保存失败，请检查设置文件并重新保存收藏夹",true);
    await refresh();rememberNavigation();
    toast(`已更新 ${result.changed} 条标签记录`);
  }catch(e){toast("重命名失败："+e.message,true)}
}
async function batchAction(action){
  if(action!=="delete"||state.batchBusy||!state.selectedIds.size)return;
  const ids=[...state.selectedIds],affected=new Set();
  ids.forEach(id=>descendants(id).forEach(item=>affected.add(item)));
  if(!confirm("移除 "+ids.length+" 个选中模块及下级共 "+affected.size+
       " 条导航记录？\n\n磁盘文件不会删除，请提前下载完整备份。"))return;
  state.batchBusy=true;updateBatchBar();
  try{
    await mutate("POST","/api/batch",{action:"delete",ids});
    exitSelectMode();await refresh();
    toast("已从导航移除选中模块");
  }catch(e){toast(e.message,true)}
  finally{state.batchBusy=false;updateBatchBar()}
}
function openCardMenu(id,x,y){
  closeCardMenu();
  const n=byId(id),menu=$("#cardContextMenu");
  if(!n||state.selectMode)return;
  state.contextId=id;
  const actions=[];
  if(n.node_type==="leaf"||n.folder_path)actions.push(["open","打开资源"]);
  if(n.node_type!=="leaf")actions.push(["enter","进入模块"]);
  actions.push(["edit","编辑模块"],["workspace-add","加入项目工作区…"]);
  if(n.node_type!=="leaf")actions.push(["child","新建子模块"]);
  if(n.folder_path||n.resource_target)actions.push(["copy-path","复制资源地址"]);
  actions.push(["delete","移除导航记录"]);
  menu.innerHTML=actions.map(([action,label])=>`<button type="button" role="menuitem" class="${action==='delete'?'menu-danger':''}" data-menu-action="${action}">${h(label)}</button>`).join("");
  menu.classList.remove("hidden");
  const bounds=menu.getBoundingClientRect();
  menu.style.left=Math.max(8,Math.min(x,window.innerWidth-bounds.width-8))+"px";
  menu.style.top=Math.max(8,Math.min(y,window.innerHeight-bounds.height-8))+"px";
  menu.querySelector("button")?.focus();
}
async function copyFolderPath(id){
  const folder=byId(id)?.folder_path||byId(id)?.resource_target;
  if(!folder){toast("该模块未关联资源地址",true);return}
  let copied=false;
  try{
    if(navigator.clipboard?.writeText){
      await navigator.clipboard.writeText(folder);
      copied=true;
    }
  }catch(_){/* Clipboard permissions vary between browsers. */}
  if(!copied){
    // Fallback works with older local browsers that do not expose Clipboard API.
    const input=document.createElement("textarea");
    input.value=folder;
    input.setAttribute("readonly","");
    input.style.position="fixed";
    input.style.opacity="0";
    input.style.pointerEvents="none";
    document.body.appendChild(input);
    try{input.focus();input.select();copied=Boolean(document.execCommand("copy"))}
    catch(_){copied=false}
    finally{input.remove()}
  }
  toast(copied?"文件夹路径已复制":"复制失败，可在“编辑模块”中手动复制路径",!copied);
}
async function contextAction(action,id){
  const n=byId(id);closeCardMenu();if(!n)return;
  if(action==="copy-path")await copyFolderPath(id);
  else if(action==="workspace-add")openWorkspacePicker(id);
  else await act(action,id);
}
async function exportBackup(){
  try {
    const payload=await api("/api/export");
    const blob=new Blob([JSON.stringify(payload,null,2)],{type:"application/json"});
    const url=URL.createObjectURL(blob);
    const link=document.createElement("a");link.href=url;link.download=`folderhub-${new Date().toISOString().slice(0,10)}.json`;document.body.append(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);toast("配置备份已导出");
  }catch(e){toast(e.message,true)}
}
async function restoreBackup(file){
  if(!file)return;
  if(!confirm("恢复备份将替换现有所有导航模块。\n建议先点击“备份”保存当前配置。\n\n确定继续吗？"))return;
  try {
    if(file.size>32*1024*1024)throw new Error("配置备份不能超过 32 MB，请减少封面图片大小或数量");
    const payload=JSON.parse(await file.text());
    await mutate("POST","/api/import",payload);
    exitSelectMode();state.view="all";state.selected=null;state.search="";$("#search").value="";
    await refresh();toast("导航配置已恢复；电脑中的文件没有被修改");
  }catch(e){toast("恢复失败："+e.message,true)}
}
function setTheme(theme) {
  state.theme=validTheme(theme);
  document.documentElement.dataset.theme=state.theme;
  renderThemeOptions();persistProjectSettings();
}
function renderThemeOptions(){
  $("#themeOptions").innerHTML=THEMES.map(t=>`<button type="button" class="theme-choice ${t.id===state.theme?'selected':''}" data-theme-choice="${t.id}" aria-pressed="${t.id===state.theme}">
    <span class="theme-sample" style="--sample-bg:${t.colors[0]};--sample-card:${t.colors[1]};--sample-accent:${t.colors[2]}"><i></i><b></b><em></em></span>
    <span class="theme-title">${t.title}${t.id===state.theme?' ✓':''}</span><span class="theme-caption">${t.description}</span></button>`).join("");
}
async function refreshStartup(){
  const toggle=$("#startupToggle"), label=$("#startupStatus");
  toggle.disabled=true;
  try {
    const result=await api("/api/startup");state.startup=result;
    toggle.checked=!!result.enabled;
    toggle.disabled=!result.supported;
    label.textContent=!result.supported?"仅 Windows 平台支持":result.needs_update?"启动项路径已变化，重新开启可更新":"当前状态："+(result.enabled?"已开启":"未开启");
  } catch(e) {label.textContent="无法读取启动项："+e.message}
}
function selectSettingsTab(tab){
  const current=["launch","appearance","storage","paths"].includes(tab)?tab:"appearance";
  if(current==="storage")refreshStorage();
  document.querySelectorAll("[data-settings-tab]").forEach(button=>{
    const selected=button.dataset.settingsTab===current;
    button.classList.toggle("selected",selected);
    button.setAttribute("aria-selected",String(selected));
  });
  document.querySelectorAll("[data-settings-page]").forEach(panel=>{
    panel.classList.toggle("hidden",panel.dataset.settingsPage!==current);
  });
  $(".settings-dialog").scrollTop=0;
}
async function refreshStorage(){
  const metrics=$("#storageMetrics"), backup=$("#storageBackup"), warning=$("#storageWarning");
  backup.disabled=true;
  metrics.textContent="正在检查本地数据...";
  try{
    const info=await api("/api/storage/status");
    const labels=[
      ["活动模块",info.active_modules],
      ["回收站批次",info.trash_batches],
      ["引用的封面",info.cover_files],
      ["缺失封面",info.missing_covers],
      ["未引用图片",info.unused_covers]
    ];
    metrics.innerHTML=labels.map(([label,value])=>`<div class="storage-metric"><strong>${Number(value)||0}</strong><span>${label}</span></div>`).join("");
    backup.disabled=!info.backup_ready;
    warning.textContent=info.missing_covers?
      `有 ${info.missing_covers} 个封面文件缺失。为避免生成不完整备份，已暂时禁用完整备份，请先找回 uploads/ 中的图片。`:
      "数据检查正常。完整 ZIP 包含 SQLite、已关联封面和回收站封面（不包含未引用图片）。";
  }catch(e){metrics.textContent="无法检查数据状态";warning.textContent=e.message;}
}
async function downloadPortableBackup(){
  // A short-lived one-time token prevents cross-site pages from forcing heavy ZIP creation.
  const button=$("#storageBackup");
  if(button.disabled)return;
  button.disabled=true;
  try{
    const auth=await mutate("POST","/api/storage/backup-ticket");
    window.location.assign(`/api/storage/backup?ticket=${encodeURIComponent(auth.ticket)}`);
  }catch(e){toast("备份下载失败："+e.message,true)}
  finally{setTimeout(()=>{button.disabled=false},1800)}
}
// Path health results are an explicit, in-memory scan snapshot; never persisted or uploaded.
let pathHealthSnapshot = null;
let pathHealthLimit = 60;
let pathHealthRequest = 0;
function clearPathHealthResults(message="尚未执行检查。"){
  pathHealthRequest++;
  pathHealthSnapshot=null;
  pathHealthLimit=60;
  $("#pathExport").disabled=true;
  $("#pathHealthSummary").textContent=message;
  $("#pathHealthList").replaceChildren();
}
// Migration proposals only suggest prefixes; never submit changes automatically.
let pathSuggestions = [];
let pathSuggestionGeneration = 0;
function clearPathSuggestions(message="输入新根目录后生成建议。"){
  pathSuggestionGeneration++;
  pathSuggestions=[];
  $("#pathSuggestSummary").textContent=message;
  $("#pathSuggestList").replaceChildren();
}
function renderPathSuggestions(suggestions){
  return suggestions.map((item,index)=>'<div class="path-row path-suggestion">'
    +'<strong>旧前缀：<code title="'+h(item.source)+'">'+h(item.source)+'</code></strong>'
    +'<span class="path-arrow">→</span><code title="'+h(item.target)+'">'+h(item.target)+'</code>'
    +'<small>涉及 '+item.linked+' 条路径；抽样检查 '+item.checked+' 条，其中 '+item.verified+' 条可访问。</small>'
    +'<div class="path-row-actions"><button type="button" class="outline-btn" data-path-suggestion="'+index+'">采用并生成预览</button></div>'
    +'</div>').join("");
}
async function suggestPaths(){
  clearPathSuggestions("正在分析已保存的关联路径，请稍候...");
  const generation=pathSuggestionGeneration;
  const target=$("#pathSuggestedRoot").value;
  const button=$("#pathSuggest");button.disabled=true;
  try{
    const result=await mutate("POST","/api/paths/suggest",{target});
    if(generation!==pathSuggestionGeneration)return;
    pathSuggestions=Array.isArray(result.suggestions)?result.suggestions:[];
    $("#pathSuggestSummary").textContent=pathSuggestions.length?
      "在 "+result.total+" 条关联路径中找到 "+pathSuggestions.length+" 种候选迁移规则。验证数量只是抽样，不代表全部目录可用。":
      "未找到有实际路径证据的建议。可直接使用下方手动前缀迁移功能。";
    $("#pathSuggestList").innerHTML=renderPathSuggestions(pathSuggestions);
  }catch(e){
    if(generation!==pathSuggestionGeneration)return;
    $("#pathSuggestSummary").textContent="分析失败："+e.message;
    toast(e.message,true);
  }finally{button.disabled=false}
}
async function acceptPathSuggestion(event){
  const button=event.target.closest("[data-path-suggestion]");
  if(!button)return;
  const index=Number(button.dataset.pathSuggestion);
  const proposal=pathSuggestions[index];
  if(!Number.isInteger(index)||index<0||!proposal)return;
  $("#pathPrefixFrom").value=proposal.source;
  $("#pathPrefixTo").value=proposal.target;
  clearPathPlan();
  await previewPaths(); // Read-only; apply still needs an explicit confirmation.
}
// Path migration must be explicit: a preview is invalidated when either input changes.
let currentPathPlan = null;
let pathPreviewGeneration = 0;
function clearPathPlan(){
  pathPreviewGeneration++;
  currentPathPlan=null;
  $("#pathApply").disabled=true;
  $("#pathPlanSummary").textContent="预览后才能应用，不会直接修改真实文件夹。";
  $("#pathPlanList").replaceChildren();
}
function pathRows(items,kind){
  const shown=kind==="health"?items.filter(x=>!x.exists):items;
  const limit=kind==="health"?pathHealthLimit:60;
  let result=shown.slice(0,limit).map(item=>{
    if(kind==="health")return `<div class="path-row"><strong>${h(item.title)}</strong><span class="path-warning">无法访问</span><code title="${h(item.path)}">${h(item.path)}</code><div class="path-row-actions"><button type="button" class="outline-btn" data-path-action="locate" data-path-id="${item.id}">定位模块</button><button type="button" class="outline-btn" data-path-action="edit" data-path-id="${item.id}">修改关联路径</button></div></div>`;
    return `<div class="path-row"><strong>${h(item.title)}</strong><code title="${h(item.old_path)}">${h(item.old_path)}</code><span class="path-arrow">↓</span><code title="${h(item.new_path)}">${h(item.new_path)}</code></div>`;
  }).join("");
  if(shown.length>limit){
    if(kind==="health")result+=`<button type="button" class="outline-btn path-load-more" data-path-action="more">再显示 ${Math.min(60,shown.length-limit)} 条（剩余 ${shown.length-limit} 条）</button>`;
    else result+=`<p class="settings-note">仅显示前 ${limit} 条，共 ${shown.length} 条记录。</p>`;
  }
  return result;
}
function csvPathCell(value){
  const raw=String(value??"");
  // Excel may evaluate CSV formulas from untrusted names/paths; neutralize before quoting.
  const safe=/^[\s\u0000-\u001f]*[=+\-@]/.test(raw)?"'"+raw:raw;
  return '"'+safe.replace(/"/g,'""')+'"';
}
function exportMissingPaths(){
  const missing=pathHealthSnapshot?.items.filter(item=>!item.exists)||[];
  if(!missing.length)return;
  const lines=[["模块 ID","模块名称","原始关联路径"],...missing.map(item=>[item.id,item.title,item.path])];
  const csv="\uFEFF"+lines.map(row=>row.map(csvPathCell).join(",")).join("\r\n")+"\r\n";
  const url=URL.createObjectURL(new Blob([csv],{type:"text/csv;charset=utf-8"}));
  const link=document.createElement("a");link.href=url;link.download=`folderhub-missing-paths-${new Date().toISOString().slice(0,10)}.csv`;
  document.body.append(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
  toast(`已导出 ${missing.length} 条失效路径（包含私人文件夹路径，请妥善保管）`);
}
function actOnPathHealth(event){
  const button=event.target.closest("[data-path-action]");
  if(!button)return;
  if(button.dataset.pathAction==="more"){
    if(!pathHealthSnapshot)return;
    pathHealthLimit+=60;
    $("#pathHealthList").innerHTML=pathRows(pathHealthSnapshot.items,"health");
    return;
  }
  if(!pathHealthSnapshot)return;
  const id=Number(button.dataset.pathId);
  if(!Number.isSafeInteger(id)||!pathHealthSnapshot.items.some(item=>item.id===id&&!item.exists)){
    toast("检测结果已过期，请重新检查",true);return;
  }
  if(!byId(id)){
    clearPathHealthResults("模块已被删除，请重新检查关联路径。");
    return;
  }
  closeSettings();
  if(button.dataset.pathAction==="locate")locateNode(id);
  else if(button.dataset.pathAction==="edit")editDialog(id);
}
async function checkPaths(){
  const button=$("#pathCheck");button.disabled=true;
  clearPathHealthResults("正在检查关联的文件夹... 网络盘可能需要一些时间。");
  const generation=pathHealthRequest;
  try {
    const result=await mutate("POST","/api/paths/check");
    if(generation!==pathHealthRequest)return;
    pathHealthSnapshot=result;
    $("#pathExport").disabled=!result.missing;
    $("#pathHealthSummary").textContent=`已检查 ${result.total} 条：可访问 ${result.accessible}，不可访问 ${result.missing}。`;
    $("#pathHealthList").innerHTML=result.missing?pathRows(result.items,"health"):'<p class="path-success">✓ 所有已关联文件夹均可访问。</p>';
  }catch(e){
    if(generation===pathHealthRequest)clearPathHealthResults("检查失败："+e.message);
    toast(e.message,true);
  }finally{button.disabled=false}
}
async function previewPaths(){
  clearPathPlan();
  const generation=pathPreviewGeneration;
  const source=$("#pathPrefixFrom").value;
  const target=$("#pathPrefixTo").value;
  const button=$("#pathPreview");button.disabled=true;
  $("#pathPlanSummary").textContent="正在计算匹配的路径...";
  try {
    const result=await mutate("POST","/api/paths/preview",{source,target});
    if(generation!==pathPreviewGeneration)return; // Form changed during the request.
    currentPathPlan=result.count?result:null;
    $("#pathApply").disabled=!currentPathPlan;
    $("#pathPlanSummary").textContent=result.count?`预览：将修改 ${result.count} 条模块路径，请核对后再确认。`:'没有匹配的关联路径，不需要修改。';
    $("#pathPlanList").innerHTML=pathRows(result.changes,"plan");
  }catch(e){if(generation===pathPreviewGeneration){$("#pathPlanSummary").textContent="预览失败："+e.message;toast(e.message,true)}}
  finally{button.disabled=false}
}
async function applyPaths(){
  const plan=currentPathPlan;
  if(!plan||!plan.count)return;
  const message=`确认批量修改 ${plan.count} 条模块的关联路径吗？\n\n${plan.source} → ${plan.target}\n\n此操作只更改数据库里的导航路径，不会移动硬盘文件夹。建议先下载完整备份。`;
  if(!confirm(message))return;
  const button=$("#pathApply");button.disabled=true;
  try {
    const result=await mutate("POST","/api/paths/apply",{source:plan.source,target:plan.target,fingerprint:plan.fingerprint});
    clearPathPlan();
    $("#pathPlanSummary").textContent=`已修改 ${result.changed} 条关联路径。可点击上方按钮重新检查。`;
    clearPathHealthResults("关联路径已更新，请重新执行检查。");
    clearPathSuggestions("关联路径已更新，请重新分析迁移建议。");
    await refresh();
    toast(`已更新 ${result.changed} 条导航路径，真实文件夹未受影响`);
  }catch(e){currentPathPlan=null;$("#pathPlanSummary").textContent="提交失败："+e.message+"；请重新生成预览。";toast(e.message,true)}
  finally{button.disabled=true}
}
function openSettings(){
  renderThemeOptions();
  updateAppearanceControls();
  selectSettingsTab("appearance");
  $("#homepageUrl").textContent=location.origin+"/";
  $("#settingsLayer").classList.remove("hidden");
  $("#settingsClose").focus();
  refreshStartup();
}
function closeSettings(){$("#settingsLayer").classList.add("hidden")}
async function changeStartup(enabled){
  const toggle=$("#startupToggle");toggle.disabled=true;
  try {
    const result=await mutate("POST","/api/startup",{enabled});
    state.startup=result;
    toast(enabled?"已开启 Windows 登录自启动":"已关闭 Windows 登录自启动");
  } catch(e){toast(e.message,true)}
  finally{await refreshStartup()}
}
function copyHomepage(){
  const url=$("#homepageUrl").textContent;
  if(navigator.clipboard?.writeText){navigator.clipboard.writeText(url).then(()=>toast("启动页地址已复制")).catch(()=>fallbackCopy(url));}
  else fallbackCopy(url);
}
function fallbackCopy(url){const input=document.createElement("textarea");input.value=url;document.body.appendChild(input);input.select();try{document.execCommand("copy");toast("启动页地址已复制")}catch(_){toast("请手动复制地址",true)}finally{input.remove()}}


/* V3.1 — keyboard-first folder launcher inspired by existing local launchers.
   Uses the in-memory module list; never scans drives or calls remote search APIs. */
const quickPalette={open:false,items:[],selected:0,returnFocus:null};
function quickCandidates(query=""){
  const term=String(query).trim();
  const result=[],seen=new Set();
  const collect=node=>{
    if(result.length>=12||seen.has(node.id))return;
    seen.add(node.id);
    result.push({node});
  };
  if(term){
    for(const node of searchAll(term)){
      collect(node);
      if(result.length>=12)break;
    }
  }else{
    for(const node of children(null)){
      collect(node);
      if(result.length>=12)break;
    }
    if(result.length<12){
      for(const node of state.nodes){
        if(node.folder_path||node.resource_target)collect(node);
        if(result.length>=12)break;
      }
    }
  }
  return result;
}
function renderQuickPalette(){
  const term=$("#quickInput").value;
  quickPalette.items=quickCandidates(term);
  const results=$("#quickResults");
  if(!quickPalette.items.length){
    quickPalette.selected=-1;
    results.innerHTML='<div class="quick-empty">没有匹配的模块。</div>';
    $("#quickInput").removeAttribute("aria-activedescendant");
    return;
  }
  quickPalette.selected=0;
  results.innerHTML=quickPalette.items.map(({node},index)=>{
    const path=node.folder_path||node.resource_target||ancestors(node.id).map(n=>n.title).join(" / ");
    const label=(node.tags||[]).length?path+" · 标签："+node.tags.join("、"):path;
    const suffix=node.node_type==="leaf"?(node.resource_kind==="url"?"网页":node.resource_kind==="file"?"文件":"文件夹"):"模块";
    return `<button type="button" class="quick-result" id="quick-option-${index}" role="option" aria-selected="false" data-quick-index="${index}">
      <span class="quick-icon" aria-hidden="true">${h(iconFor(node))}</span>
      <span class="quick-details"><strong>${term?highlightSearch(node.title,term):h(node.title)}</strong>
        <small title="${h(label)}">${term?highlightSearch(label,term):h(label)}</small></span>
      <span class="quick-tag">${h(suffix)}</span>
    </button>`;
  }).join("");
  markQuickSelection();
}
function markQuickSelection(){
  const items=$("#quickResults").querySelectorAll("[data-quick-index]");
  items.forEach((item,index)=>{
    const active=index===quickPalette.selected;
    item.classList.toggle("is-active",active);
    item.setAttribute("aria-selected",String(active));
  });
  const current=items[quickPalette.selected];
  if(current){
    $("#quickInput").setAttribute("aria-activedescendant",current.id);
    current.scrollIntoView({block:"nearest"});
  }else $("#quickInput").removeAttribute("aria-activedescendant");
}
function openQuickPalette(){
  if(!$("#quickLayer").classList.contains("hidden"))return;
  if(!$("#dialogLayer").classList.contains("hidden") ||
     !$("#settingsLayer").classList.contains("hidden") ||
     !$("#groupResultLayer").classList.contains("hidden"))return;
  closeCardMenu();
  quickPalette.returnFocus=document.activeElement;
  quickPalette.open=true;
  $("#quickLayer").classList.remove("hidden");
  $("#quickInput").value="";
  renderQuickPalette();
  $("#quickInput").focus();
}
function closeQuickPalette(){
  if(!quickPalette.open)return;
  quickPalette.open=false;
  $("#quickLayer").classList.add("hidden");
  $("#quickInput").removeAttribute("aria-activedescendant");
  quickPalette.items=[];quickPalette.selected=0;
  if(quickPalette.returnFocus && document.contains(quickPalette.returnFocus))
    quickPalette.returnFocus.focus({preventScroll:true});
  quickPalette.returnFocus=null;
}
async function quickLaunch(index){
  const entry=quickPalette.items[index],node=entry?.node;
  if(!node || !byId(node.id))return;
  if(node.node_type==="leaf"&&!node.folder_path&&!node.resource_target){
    toast("该叶子模块尚未关联资源，请先编辑模块",true);
    return;
  }
  closeQuickPalette();
  await act("primary",node.id);
}
function bindQuickPalette(){
  $("#quickOpenBtn").addEventListener("click",openQuickPalette);
  $("#quickClose").addEventListener("click",closeQuickPalette);
  $("#quickLayer").addEventListener("pointerdown",event=>{
    if(event.target===$("#quickLayer"))closeQuickPalette();
  });
  $("#quickInput").addEventListener("input",renderQuickPalette);
  $("#quickInput").addEventListener("keydown",async event=>{
    if(event.key==="Escape"){
      event.preventDefault();event.stopPropagation();closeQuickPalette();return;
    }
    if(event.key==="Tab")return;
    if(!["ArrowDown","ArrowUp","Enter"].includes(event.key))return;
    event.preventDefault();event.stopPropagation();
    if(!quickPalette.items.length)return;
    if(event.key==="Enter"){await quickLaunch(quickPalette.selected);return}
    const count=quickPalette.items.length;
    quickPalette.selected=event.key==="ArrowDown"?
      (quickPalette.selected+1+count)%count:
      (quickPalette.selected-1+count)%count;
    markQuickSelection();
  });
  $("#quickResults").addEventListener("click",async event=>{
    const item=event.target.closest("[data-quick-index]");
    if(item)await quickLaunch(Number(item.dataset.quickIndex));
  });
  // Trap Tab inside the modal; arrows and Enter remain usable in the input.
  $("#quickLayer").addEventListener("keydown",event=>{
    if(event.key==="Escape"){
      event.preventDefault();closeQuickPalette();return;
    }
    if(event.key!=="Tab")return;
    const focusable=[...$("#quickLayer").querySelectorAll('input,button')].filter(el=>!el.disabled);
    if(!focusable.length)return;
    const current=focusable.indexOf(document.activeElement);
    if(event.shiftKey && current===0){event.preventDefault();focusable.at(-1).focus()}
    else if(!event.shiftKey && current===focusable.length-1){
      event.preventDefault();focusable[0].focus();
    }
  });
}


/* Optional local-only Everything ES search. Results never launch automatically. */
let everythingItems=[];
let everythingRequestVersion=0;
let everythingController=null;
let everythingPendingQuery="";
const everythingDefaultStatus="需要本机安装并运行 Everything，且 es.exe 可用。";
function resetEverythingSearch(message=everythingDefaultStatus){
  // Closing, editing the query or reopening a dialog invalidates every
  // previous response, even if abort races with a completed fetch.
  everythingRequestVersion++;
  if(everythingController)everythingController.abort();
  everythingController=null;
  everythingPendingQuery="";
  everythingItems=[];
  $("#everythingResults").replaceChildren();
  $("#everythingResults").setAttribute("aria-busy","false");
  $("#everythingSubmit").disabled=false;
  $("#everythingStatus").textContent=message;
}
function closeEverything(){
  resetEverythingSearch();
  $("#everythingLayer").classList.add("hidden");
}
async function runEverythingSearch(event){
  event.preventDefault();
  const query=$("#everythingQuery").value.trim(),button=$("#everythingSubmit");
  if(query.length<2||query.length>100){toast("请输入 2—100 字搜索词",true);return}
  // Enter can submit a form even while its button is disabled. Do not launch
  // duplicate ES subprocesses for the same outstanding query.
  if(everythingController&&everythingPendingQuery===query)return;
  const version=++everythingRequestVersion;
  if(everythingController)everythingController.abort();
  const controller=new AbortController();
  everythingController=controller;
  everythingPendingQuery=query;
  everythingItems=[];
  button.disabled=true;
  $("#everythingStatus").textContent="正在查询本机 Everything 索引…";
  $("#everythingResults").replaceChildren();
  $("#everythingResults").setAttribute("aria-busy","true");
  try{
    const result=await api("/api/everything/search?q="+encodeURIComponent(query),
                           {signal:controller.signal});
    if(version!==everythingRequestVersion||controller.signal.aborted||
       $("#everythingLayer").classList.contains("hidden"))return;
    everythingItems=result.items||[];
    const skipped=Number(result.unavailable||0);
    $("#everythingStatus").textContent="找到 "+everythingItems.length+" 项"
      +(skipped?"，跳过 "+skipped+" 个当前无法访问的路径":"")
      +"；搜索结果不会自动打开。";
    $("#everythingResults").innerHTML=everythingItems.map((item,index)=>{
      const supported=item.supported!==false;
      return '<div class="everything-result"><span title="'+h(item.path)+'"><strong>'+h(item.name)+'</strong>'
        +'<small>'+h(item.path)+'</small></span><button type="button" data-everything-add="'+index+'"'
        +(supported?'':' disabled title="当前文件类型不支持加入导航"')
        +'>'+(supported?'＋ 加入导航':'文件类型不支持')+'</button></div>';
    }).join("");
  }catch(error){
    if(version!==everythingRequestVersion||controller.signal.aborted)return;
    everythingItems=[];
    $("#everythingStatus").textContent=error.message;
  }finally{
    if(version===everythingRequestVersion){
      everythingController=null;
      everythingPendingQuery="";
      button.disabled=false;
      $("#everythingResults").setAttribute("aria-busy","false");
    }
  }
}
function chooseEverythingResult(index){
  const item=everythingItems[index];if(!item||item.supported===false)return;
  const parent=state.nodes.find(node=>node.node_type==="root");
  if(!parent){toast("请先建立一个根分类，再添加 Everything 搜索结果",true);return}
  closeEverything();
  editDialog(null,parent.id);
  $("#entryType").value="leaf";
  $("#entryResourceKind").value=item.kind==="folder"?"folder":"file";
  if(item.kind==="folder")$("#entryPath").value=item.path;
  else $("#entryResourceTarget").value=item.path;
  $("#entryName").value=item.name;
  updateEntryType();
}
function bindEverything(){
  $("#everythingBtn").addEventListener("click",()=>{
    resetEverythingSearch();
    $("#everythingLayer").classList.remove("hidden");
    $("#everythingQuery").focus();
  });
  $("#everythingQuery").addEventListener("input",()=>{
    resetEverythingSearch("搜索词已变化，请按 Enter 或点击「搜索」重新查询。");
  });
  $("#everythingClose").addEventListener("click",closeEverything);
  $("#everythingLayer").addEventListener("click",event=>{
    if(event.target===$("#everythingLayer"))closeEverything();
  });
  $("#everythingLayer").addEventListener("keydown",event=>{
    if(event.key==="Escape"){event.preventDefault();closeEverything()}
  });
  $("#everythingForm").addEventListener("submit",runEverythingSearch);
  $("#everythingResults").addEventListener("click",event=>{
    const button=event.target.closest("[data-everything-add]");
    if(button)chooseEverythingResult(Number(button.dataset.everythingAdd));
  });
}

function bind(){
  bindSorting();
  bindQuickPalette();
  bindEverything();
  window.addEventListener("popstate",restoreBrowserNavigation);
  $("#selectModeBtn").addEventListener("click",()=>{if(state.batchBusy)return;state.selectMode=!state.selectMode;state.selectedIds.clear();closeCardMenu();render(true)});
  $("#bulkCancel").addEventListener("click",()=>{exitSelectMode();render(true)});
  $("#bulkSelectAll").addEventListener("click",()=>{if(state.batchBusy)return;const ids=state.visibleIds;if(ids.length>200){toast("已显示模块超过 200 项，请缩小搜索范围",true);return}state.selectedIds=new Set(ids);render(true)});
  $("#bulkTagAdd").addEventListener("click",()=>batchTags("add"));
  $("#bulkTagRemove").addEventListener("click",()=>batchTags("remove"));
  $("#bulkSaveGroup").addEventListener("click",saveSelectedFolderGroup);
  $("#bulkSaveWorkspace").addEventListener("click",()=>openWorkspaceDialog(-1,[...state.selectedIds]));
  $("#workspaceNew").addEventListener("click",()=>openWorkspaceDialog());
  $("#workspaceResources").addEventListener("change",event=>{
    const select=event.target.closest("[data-workspace-switch]");
    if(!select)return;
    const destination=select.value;
    if(state.workspaces.some(item=>item.name===destination)&&destination!==state.activeWorkspace)
      setView("workspace",destination);
  });
  $("#workspaceNav").addEventListener("click",e=>{
    const open=e.target.closest("[data-workspace-open]");
    if(open){const item=state.workspaces[Number(open.dataset.workspaceOpen)];if(item)setView("workspace",item.name);return}
    const edit=e.target.closest("[data-workspace-edit]");
    if(edit){openWorkspaceDialog(Number(edit.dataset.workspaceEdit));return}
    const remove=e.target.closest("[data-workspace-delete]");
    if(remove)deleteWorkspace(Number(remove.dataset.workspaceDelete));
  });
  $("#workspaceForm").addEventListener("submit",submitWorkspace);
  $("#workspaceLaunchList").addEventListener("change",event=>{
    const target=event.target.closest("[data-workspace-launch]");
    if(!target)return;
    const id=Number(target.dataset.workspaceLaunch);
    if(!workspaceDraftMembers.has(id)||byId(id)?.node_type!=="leaf"){target.checked=false;return}
    if(target.checked){
      if(workspaceDraftLaunchIds.size>=8){target.checked=false;toast("一次最多启动8项资源",true);return}
      workspaceDraftLaunchIds.add(id);
    }else workspaceDraftLaunchIds.delete(id);
    renderWorkspaceLaunchChoices();
  });
  $("#workspaceLaunchClose").addEventListener("click",closeWorkspaceLaunchResult);
  $("#workspaceLaunchDone").addEventListener("click",closeWorkspaceLaunchResult);
  $("#workspaceLaunchLayer").addEventListener("click",event=>{
    if(event.target===$("#workspaceLaunchLayer"))closeWorkspaceLaunchResult();
  });
  $("#workspaceLaunchLayer").addEventListener("keydown",event=>{
    if(event.key==="Escape"){event.stopPropagation();closeWorkspaceLaunchResult()}
  });
  $("#workspaceLinkAdd").addEventListener("click",()=>{
    if(workspaceDraftLinks.length>=8)return;
    workspaceDraftLinks.push({name:"",url:""});
    renderWorkspaceLinkEditor();
    $("#workspaceLinkList").querySelector('[data-workspace-link-name="'+(workspaceDraftLinks.length-1)+'"]')?.focus();
  });
  $("#workspaceLinkList").addEventListener("input",e=>{
    const target=e.target;
    if(target.matches("[data-workspace-link-name]")){
      const index=Number(target.dataset.workspaceLinkName);
      if(workspaceDraftLinks[index])workspaceDraftLinks[index].name=target.value;
    }
    if(target.matches("[data-workspace-link-url]")){
      const index=Number(target.dataset.workspaceLinkUrl);
      if(workspaceDraftLinks[index])workspaceDraftLinks[index].url=target.value;
    }
  });
  $("#workspaceLinkList").addEventListener("click",e=>{
    const move=e.target.closest("[data-workspace-link-move]");
    if(move){
      const index=Number(move.dataset.workspaceLinkMove),direction=Number(move.dataset.workspaceStep);
      if(Number.isInteger(index))moveWorkspaceDraftLink(index,direction);
      return;
    }
    const button=e.target.closest("[data-workspace-link-remove]");
    if(!button)return;
    const index=Number(button.dataset.workspaceLinkRemove);
    if(!Number.isSafeInteger(index)||index<0||index>=workspaceDraftLinks.length)return;
    workspaceDraftLinks.splice(index,1);
    renderWorkspaceLinkEditor();
    $("#workspaceLinkAdd").focus();
  });
  $("#workspaceMemberSearch").addEventListener("input",renderWorkspaceMembers);
  $("#workspaceMemberList").addEventListener("click",e=>{
    const button=e.target.closest("[data-workspace-move]");
    if(!button)return;
    const id=Number(button.dataset.workspaceMove),direction=Number(button.dataset.workspaceStep);
    if(!Number.isSafeInteger(id)||!workspaceDraftMembers.has(id))return;
    moveWorkspaceDraftMember(id,direction);
  });
  $("#workspaceMemberList").addEventListener("change",e=>{
    if(!e.target.matches("[data-workspace-member]"))return;
    const id=Number(e.target.dataset.workspaceMember);
    if(!Number.isSafeInteger(id)||id<1)return;
    if(e.target.checked){
      if(workspaceDraftMembers.size>=30){e.target.checked=false;toast("最多选择30个模块",true);return}
      workspaceDraftMembers.add(id);
    }else workspaceDraftMembers.delete(id);
    renderWorkspaceMembers();
    $("#workspaceMemberList").querySelector('[data-workspace-member="'+id+'"]')?.focus();
  });
  $("#workspaceLayer").addEventListener("keydown",e=>{
    if(e.key==="Escape"){e.preventDefault();e.stopPropagation();closeWorkspaceDialog();return}
    if(e.key!=="Tab")return;
    const controls=[...$("#workspaceLayer").querySelectorAll("input,textarea,button")]
      .filter(el=>!el.disabled && el.offsetParent!==null);
    if(!controls.length)return;
    const first=controls[0],last=controls.at(-1);
    if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}
    else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}
  });
  $("#workspacePickerClose").addEventListener("click",closeWorkspacePicker);
  $("#workspacePickerCancel").addEventListener("click",closeWorkspacePicker);
  $("#workspacePickerLayer").addEventListener("click",e=>{if(e.target===$("#workspacePickerLayer"))closeWorkspacePicker()});
  $("#workspacePickerList").addEventListener("click",e=>{
    const btn=e.target.closest("[data-workspace-append]");
    if(btn&&!btn.disabled)addNodeToWorkspace(Number(btn.dataset.workspaceAppend));
  });
  $("#workspacePickerLayer").addEventListener("keydown",e=>{
    if(e.key==="Escape"){e.preventDefault();e.stopPropagation();closeWorkspacePicker();return}
    if(e.key!=="Tab")return;
    const controls=[...$("#workspacePickerLayer").querySelectorAll("button")]
      .filter(el=>!el.disabled&&el.offsetParent!==null);
    if(!controls.length)return;
    const first=controls[0],last=controls.at(-1);
    if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}
    else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}
  });
  $("#workspaceClose").addEventListener("click",closeWorkspaceDialog);
  $("#workspaceCancel").addEventListener("click",closeWorkspaceDialog);
  $("#workspaceLayer").addEventListener("click",e=>{if(e.target===$("#workspaceLayer"))closeWorkspaceDialog()});
  $("#folderGroupNav").addEventListener("click",event=>{
    const open=event.target.closest("[data-group-open]");
    if(open){openFolderGroup(Number(open.dataset.groupOpen));return}
    const rename=event.target.closest("[data-group-rename]");
    if(rename){renameFolderGroup(Number(rename.dataset.groupRename));return}
    const remove=event.target.closest("[data-group-delete]");
    if(remove)deleteFolderGroup(Number(remove.dataset.groupDelete));
  });
  $("#groupResultClose").addEventListener("click",closeGroupReport);
  $("#groupResultDone").addEventListener("click",closeGroupReport);
  $("#groupResultLayer").addEventListener("click",event=>{
    if(event.target===$("#groupResultLayer"))closeGroupReport();
  });
  $("#bulkDelete").addEventListener("click",()=>batchAction("delete"));
  $("#cardContextMenu").addEventListener("click",e=>{const btn=e.target.closest("[data-menu-action]");if(btn&&state.contextId!==null)contextAction(btn.dataset.menuAction,state.contextId)});
  $("#entries").addEventListener("contextmenu",e=>{const card=e.target.closest(".entry-card");if(!card||e.target.closest("input,textarea"))return;e.preventDefault();openCardMenu(Number(card.dataset.id),e.clientX,e.clientY)});
  $("#entries").addEventListener("keydown",e=>{if((e.key==="F10"&&e.shiftKey)||e.key==="ContextMenu"){const card=e.target.closest(".entry-card");if(!card)return;e.preventDefault();const r=card.getBoundingClientRect();openCardMenu(Number(card.dataset.id),r.left+32,r.top+32)}});
  document.addEventListener("pointerdown",e=>{if(!e.target.closest("#cardContextMenu"))closeCardMenu()});
  $("#specialNav").addEventListener("click",e=>{const item=e.target.closest("[data-view]");if(item)setView(item.dataset.view)});
  $("#smartViewNav").addEventListener("click",e=>{
    const btn=e.target.closest("[data-saved-view]");
    if(btn)openSmartView(Number(btn.dataset.savedView));
  });
  $("#tagFilters").addEventListener("click",e=>{
    const smart=e.target.closest("[data-smart-action]");
    if(smart){editSavedViews(smart.dataset.smartAction);return}
    if(e.target.closest("[data-tag-rename]")){renameCurrentTag();return}
    const mode=e.target.closest("[data-tag-match]");
    if(mode){updateTagFilterMode("match",mode.dataset.tagMatch);return}
    const pick=e.target.closest("[data-tag-pick]");
    if(pick){updateTagFilterMode("pick",pick.dataset.tagPick);return}
    if(e.target.closest("[data-tag-clear]")){chooseTag(null);return}
    const btn=e.target.closest("[data-tag-filter]");
    if(btn)chooseTag(btn.dataset.tagFilter||null);
  });
  $("#treeNav").addEventListener("click",e=>{
    const toggle=e.target.closest("[data-toggle]");
    if(toggle){toggleBranch(Number(toggle.dataset.toggle));return}
    const item=e.target.closest("[data-node]");if(!item)return;
    const id=Number(item.dataset.node);const n=byId(id);
    setView("node",id);if(n?.node_type==="leaf")openFolder(id);
  });
  $("#breadcrumb").addEventListener("click",e=>{const item=e.target.closest("[data-crumb]");if(item)item.dataset.crumb==="all"?setView("all"):setView("node",Number(item.dataset.crumb))});
  $("#entries").addEventListener("click",e=>{
    const btn=e.target.closest("[data-action]");
    if(btn)act(btn.dataset.action,Number(btn.dataset.id));
  });
  $("#sectionOperations").addEventListener("click",e=>{const btn=e.target.closest("[data-action]");if(btn)act(btn.dataset.action,state.selected)});
  $("#addRoot").addEventListener("click",()=>editDialog(null,null));
  $("#newBtn").addEventListener("click",()=>editDialog());
  $("#search").addEventListener("input",e=>{
    closeCardMenu();state.selectedIds.clear();state.search=e.target.value;
    state.searchKeyboardIndex=-1;state.renderLimit=100;queueSearchRender();
  });
  $("#search").addEventListener("keydown",async e=>{
    if(!state.search.trim())return;
    if(e.key==="Escape"){
      e.preventDefault();e.stopPropagation();state.search="";state.searchKeyboardIndex=-1;
      $("#search").value="";state.renderLimit=100;flushSearchRender();return;
    }
    if(!["ArrowDown","ArrowUp","Enter"].includes(e.key))return;
    const results=searchAll(state.search);
    if(!results.length)return;
    if(state.selectMode && e.key==="Enter")return;
    e.preventDefault();e.stopPropagation();
    if(e.key==="Enter"){
      if(searchRenderFrame!==null){
        cancelAnimationFrame(searchRenderFrame);
        searchRenderFrame=null;
      }
      const index=state.searchKeyboardIndex<0?0:Math.min(state.searchKeyboardIndex,results.length-1);
      await act("primary",results[index].id);return;
    }
    // Navigate only cards that are currently rendered. Previously ArrowUp
    // from the first search state jumped to the last of 20k results and
    // immediately built up to 20k DOM cards just to move keyboard focus.
    const visibleCount=Math.min(results.length,state.renderLimit);
    const old=state.searchKeyboardIndex;
    state.searchKeyboardIndex=e.key==="ArrowDown"?(old+1)%visibleCount:
      old<0?visibleCount-1:(old-1+visibleCount)%visibleCount;
    flushSearchRender();
    document.getElementById(`folderhub-entry-${results[state.searchKeyboardIndex].id}`)?.scrollIntoView({block:"nearest"});
  });
  $("#layoutBtn").addEventListener("click",()=>{
    const scrollY=window.scrollY;
    state.layout=state.layout==="grid"?"list":"grid";
    $("#layoutBtn").textContent=state.layout==="grid"?"▦":"☷";
    $("#layoutBtn").setAttribute("aria-label",state.layout==="grid"?"切换到列表模式":"切换到网格模式");
    render(true);
    // Preserve the user's vertical position during a layout toggle.
    window.scrollTo({top:scrollY,behavior:"instant"});
    persistProjectSettings();
  });
  $("#backupBtn").addEventListener("click",exportBackup);
  $("#restoreBtn").addEventListener("click",()=>$("#importFile").click());
  $("#themeBtn").addEventListener("click",openSettings);
  $("#settingsBtn").addEventListener("click",openSettings);
  $("#settingsClose").addEventListener("click",closeSettings);
  $("#settingsDone").addEventListener("click",closeSettings);
  $("#settingsLayer").addEventListener("click",e=>{if(e.target===$("#settingsLayer"))closeSettings()});
  $("#themeOptions").addEventListener("click",e=>{const btn=e.target.closest("[data-theme-choice]");if(btn)setTheme(btn.dataset.themeChoice)});
  $("#settingsLayer").addEventListener("click",e=>{const pref=e.target.closest("[data-pref][data-value]");if(pref)setPreference(pref.dataset.pref,pref.dataset.value)});
  $("#settingsLayer").addEventListener("click",e=>{const tab=e.target.closest("[data-settings-tab]");if(tab)selectSettingsTab(tab.dataset.settingsTab)});
  $("#showCoversToggle").addEventListener("change",e=>{preferences.showCovers=e.target.checked;savePreferences()});
  $("#entryIcon").addEventListener("change",syncCoverPreview);
  $("#entryCoverFile").addEventListener("change",e=>{handleCoverFile(e.target.files[0]);});
  $("#pickCover").addEventListener("click",()=>$("#entryCoverFile").click());
  $("#removeCover").addEventListener("click",()=>{state.pendingCover=null;state.removeCover=true;$("#entryCoverFile").value="";syncCoverPreview()});
  $("#resetAppearance").addEventListener("click",()=>{preferences={...PREF_DEFAULTS};savePreferences();toast("布局与字号已恢复默认")});
  $("#sidebarToggle").addEventListener("click",()=>{preferences.sidebarCollapsed=!preferences.sidebarCollapsed;savePreferences()});
  $("#startupToggle").addEventListener("change",e=>changeStartup(e.target.checked));
  $("#copyHomepage").addEventListener("click",copyHomepage);
  $("#storageRefresh").addEventListener("click",refreshStorage);
  $("#storageBackup").addEventListener("click",downloadPortableBackup);
  $("#pathSuggest").addEventListener("click",suggestPaths);
  $("#pathSuggestedRoot").addEventListener("input",()=>clearPathSuggestions());
  $("#pathSuggestList").addEventListener("click",acceptPathSuggestion);
  $("#pathCheck").addEventListener("click",checkPaths);
  $("#pathExport").addEventListener("click",exportMissingPaths);
  $("#pathHealthList").addEventListener("click",actOnPathHealth);
  $("#pathPreview").addEventListener("click",previewPaths);
  $("#pathApply").addEventListener("click",applyPaths);
  for(const selector of ["#pathPrefixFrom","#pathPrefixTo"]){
    $(selector).addEventListener("input",clearPathPlan);
  }
  $("#importFile").addEventListener("change",async e=>{await restoreBackup(e.target.files[0]);e.target.value=""});
  $("#entryForm").addEventListener("submit",submitDialog);
  $("#entryType").addEventListener("change",updateEntryType);
  $("#entryResourceKind").addEventListener("change",updateEntryType);
  $("#entryParent").addEventListener("change",e=>{
    if(!e.target.value)$("#entryType").value="root";
    else if($("#entryType").value==="root")$("#entryType").value="group";
    updateEntryType();
  });
  $("#dialogClose").addEventListener("click",closeDialog);
  $("#cancelDialog").addEventListener("click",closeDialog);
  $("#dialogLayer").addEventListener("click",e=>{if(e.target===$("#dialogLayer"))closeDialog()});
  $("#pickFolder").addEventListener("click",async()=>{const btn=$("#pickFolder");btn.disabled=true;try{const d=await mutate("POST","/api/pick-folder");if(d.path)$("#entryPath").value=d.path}catch(e){toast(e.message,true)}finally{btn.disabled=false}});
  document.addEventListener("keydown",e=>{
    if(e.key.toLowerCase()==="p"&&(e.ctrlKey||e.metaKey)&&e.shiftKey){
      if($("#dialogLayer").classList.contains("hidden") && $("#settingsLayer").classList.contains("hidden")){
        e.preventDefault();openQuickPalette();
      }
      return;
    }
    if(quickPalette.open)return;
    if(e.key==="Escape"&&!$("#workspacePickerLayer").classList.contains("hidden")){
      closeWorkspacePicker();return;
    }
    if(e.key==="Escape"&&!$("#workspaceLayer").classList.contains("hidden")){
      closeWorkspaceDialog();return;
    }
    if(e.key==="Escape"&&!$("#groupResultLayer").classList.contains("hidden")){
      closeGroupReport();return;
    }
    if(e.key==="Escape"&&!$("#cardContextMenu").classList.contains("hidden")){closeCardMenu();return}
    if(e.key==="Escape"&&state.selectMode){exitSelectMode();render();return}
    if(e.key==="Escape"&&!$("#dialogLayer").classList.contains("hidden"))closeDialog();
    if(e.key==="Escape"&&!$("#settingsLayer").classList.contains("hidden"))closeSettings();
    if(e.key.toLowerCase()==="k"&&(e.ctrlKey||e.metaKey)){e.preventDefault();$("#search").focus();$("#search").select()}
  });
}
async function init(){
  bind();
  applyPreferences();
  try{
    const c=await api("/api/config");state.token=c.token;
    await loadProjectSettings();
    await refresh();
    startBrowserNavigation();
    if(c.platform!=="win32")toast("当前非 Windows 系统，浏览和打开资源管理器功能不可用",true);
  }
  catch(e){toast(e.message,true);$("#entries").innerHTML=`<div class="empty-state"><h3>本地服务无法连接</h3><p>${h(e.message)}</p></div>`}
}
init();
