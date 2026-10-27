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
const state = {openingIds:new Set(),nodes:[],trash:[],recent:[], renderLimit:100, searchKeyboardIndex:-1, token:"", view:"all", selected:null, search:"", layout:"grid", editing:null, theme:"cloud", startup:null, expanded:new Set(), treeInitialized:false, pendingCover:null, removeCover:false, draggingId:null, sorting:false,selectMode:false,selectedIds:new Set(),visibleIds:[],batchBusy:false,contextId:null};

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
  const view=hash.slice(1);
  return ["favorites","recent","trash"].includes(view)?
    {view,id:null}:{view:"all",id:null};
}
function routeUrl(view,id=null){
  const suffix=view==="node"?`#node/${id}`:view==="all"?"":`#${view}`;
  return window.location.pathname+window.location.search+suffix;
}
function navigationSnapshot(){
  return {folderhubRoute:1,view:state.view,
    id:state.view==="node"?state.selected:null,
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
function collectProjectSettings(){
  return {...preferences,theme:state.theme,layout:state.layout,
    expanded:state.treeInitialized?[...state.expanded]:initialExpanded};
}
async function persistProjectSettings(){
  if(!projectSettingsReady)return;
  pendingSettings=collectProjectSettings();
  if(settingsWriteInFlight)return;
  settingsWriteInFlight=true;
  try{
    while(pendingSettings){
      const snapshot=pendingSettings;pendingSettings=null;
      try{await mutate("PUT","/api/preferences",{settings:snapshot})}
      catch(e){toast("保存项目个性化设置失败："+e.message,true)}
    }
  }finally{settingsWriteInFlight=false}
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
  const saved=payload.settings||{};
  preferences={...PREF_DEFAULTS};
  for(const [key,values] of Object.entries(PREF_ALLOWED))
    if(values.includes(saved[key]))preferences[key]=saved[key];
  for(const key of ["showCovers","sidebarCollapsed"])
    if(typeof saved[key]==="boolean")preferences[key]=saved[key];
  state.theme=validTheme(saved.theme);
  state.layout=saved.layout==="list"?"list":"grid";
  initialExpanded=Array.isArray(saved.expanded)?saved.expanded:null;
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
const byId = id => nodeById.get(id);
const sorted = nodes => [...nodes].sort((a,b)=>a.sort_order-b.sort_order || a.id-b.id);
const children = id => childrenByParent.get(id??null) || [];
function rebuildNodeIndex(){
  nodeById = new Map(state.nodes.map(node=>[node.id,node]));
  childrenByParent = new Map();
  for(const node of state.nodes){
    const parent = node.parent_id??null;
    if(!childrenByParent.has(parent))childrenByParent.set(parent,[]);
    childrenByParent.get(parent).push(node);
  }
  for(const nodes of childrenByParent.values())nodes.sort((a,b)=>a.sort_order-b.sort_order || a.id-b.id);
  searchRecords=state.nodes.map(node=>{
    const own=(node.title+" "+(node.folder_path||"")).toLocaleLowerCase();
    const full=ancestors(node.id).map(entry=>entry.title).join(" /").toLocaleLowerCase();
    return {node,own,body:own+" "+full};
  });
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
  if(!response.ok) throw new Error(data.error||`操作失败 (${response.status})`);
  return data;
}
const mutate = (method,path,data={}) => api(path,{method,body:JSON.stringify(data)});
function loadTreeState() {
  try {const saved=localStorage.getItem("folderhub.expanded");return saved===null?null:JSON.parse(saved)}
  catch(_){return null}
}
function saveTreeState(){persistProjectSettings()}
function expandLineage(id){
  for(const node of ancestors(id)){if(node.node_type!=="leaf")state.expanded.add(node.id)}
  saveTreeState();
}
async function refresh(){
  const [data,bin,usage]=await Promise.all([api("/api/nodes"),api("/api/trash"),api("/api/recent")]);
  state.nodes=data.nodes;state.trash=bin.items;state.recent=usage.items;
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
  if(!fromHistory)rememberNavigation();
  closeCardMenu();exitSelectMode();
  if(view==="node"&&!byId(id)){view="all";id=null}
  state.view=view;state.selected=view==="node"?id:null;
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
  saveTreeState();renderNav();
}
function renderNav(){
  const roots=children(null), fav=state.nodes.filter(n=>n.favorite);
  $("#rootCount").textContent=roots.length;$("#favoriteCount").textContent=fav.length;
  $("#trashCount").textContent=state.trash.length;
  $("#recentCount").textContent=state.recent.length;
  document.querySelectorAll("#specialNav [data-view]").forEach(el=>el.classList.toggle("active",state.view===el.dataset.view));
  const walk=(nodes) => nodes.map(n=>{
    const sub=children(n.id), expand=sub.length>0 && state.expanded.has(n.id), isLeaf=n.node_type==="leaf";
    return `<div class="tree-branch" role="group">
      <div class="tree-row ${state.view==='node'&&state.selected===n.id?'active':''}">
        ${sub.length?`<button type="button" class="tree-toggle" data-toggle="${n.id}" aria-expanded="${expand}" aria-label="${expand?'折叠':'展开'} ${h(n.title)}"><span class="tree-chevron ${expand?'is-open':''}">›</span></button>`
          :'<span class="tree-spacer" aria-hidden="true"></span>'}
        <button type="button" class="tree-item" data-node="${n.id}" title="${h(n.title)} (${TYPE_LABEL[n.node_type]||'模块'})">
          <span class="tree-folder" aria-hidden="true">${h(iconFor(n))}</span>
          <span class="tree-text">${h(n.title)}</span>${isLeaf?'<span class="tree-leaf-mark" title="关联的文件夹">↗</span>':''}
        </button>
      </div>${sub.length&&expand?`<div class="tree-children" role="group">${walk(sub)}</div>`:''}
    </div>`;
  }).join("");
  $("#treeNav").innerHTML=walk(roots);
}
function renderCrumb(){
  const bits=[`<button type="button" data-crumb="all">首页</button>`];
  if(state.search.trim()){
    bits.push('<span>›</span><strong>全局搜索</strong>');
    $("#breadcrumb").innerHTML=bits.join("");return;
  }
  if(state.view==="favorites") bits.push(`<span>›</span><strong>我的收藏</strong>`);
  if(state.view==="recent") bits.push(`<span>›</span><strong>最近使用</strong>`);
  if(state.view==="trash") bits.push(`<span>›</span><strong>回收站</strong>`);
  if(state.view==="node"){
    for(const n of ancestors(state.selected)){
      bits.push(`<span>›</span><button type="button" data-crumb="${n.id}">${h(n.title)}</button>`);
    }
  }
  $("#breadcrumb").innerHTML=bits.join("");
}
function card(n,reorderable=false,keyboardActive=false){
  const childCount=children(n.id).length;
  const linked=!!n.folder_path;
  const leaf=n.node_type==="leaf";
  const lineage=ancestors(n.id).map(a=>a.title).join(" / ");
  const usage=state.view==="recent" && !state.search ? state.recent.find(item=>item.node_id===n.id) : null;
  const lastUsed=usage?new Date(usage.last_opened_at):null;
  const recentText=usage?`${usage.pinned?"📌 已置顶 · ":""}最近打开：${lastUsed && !Number.isNaN(lastUsed.getTime()) ? lastUsed.toLocaleString("zh-CN") : "未知时间"} · 累计 ${Number(usage.open_count)||0} 次`:"";
  const contextText=state.search?`所属：${lineage}`:recentText;
  // List metadata belongs in the primary information column, not the grid's
  // auxiliary sibling row (which was deliberately hidden in list mode).
  const listContext=state.layout==="list" && contextText?
    `<span class="list-card-context" title="${h(contextText)}">${state.search?highlightSearch(contextText,state.search):h(contextText)}</span>`:"";
  const recentCaption=state.layout!=="list" && recentText?
    `<div class="entry-lineage">${h(recentText)}</div>`:"";
  const primaryTitle=leaf?"在 Windows 资源管理器打开文件夹":"进入此模块";
  return `<article class="entry-card ${leaf?"is-leaf":"is-container"} ${state.openingIds.has(n.id)?"is-opening":""} ${state.selectedIds.has(n.id)?"is-selected":""} ${keyboardActive?"keyboard-active":""}" id="folderhub-entry-${n.id}" data-id="${n.id}" tabindex="0" aria-label="${h(n.title)}，右键打开快捷菜单">
    <div class="card-cover tone-${n.id%6} ${n.has_image?'with-image':'with-icon'}" aria-hidden="true">
      ${n.has_image?`<img class="cover-image" src="${coverUrl(n)}" loading="lazy" alt="">`:`<span class="cover-emoji">${h(iconFor(n))}</span><span class="cover-decoration"></span>`}
      <span class="cover-type">${TYPE_LABEL[n.node_type]||"模块"}</span>
    </div>
    <div class="card-head"><span class="folder-icon ${linked?'':'unlinked'}">${h(iconFor(n))}</span>
      <div class="card-actions">
        ${usage && !state.selectMode?`<button type="button" class="small-action recent-pin ${usage.pinned?"on":""}" title="${usage.pinned?"取消置顶":"置顶到最近使用顶部"}" aria-label="${usage.pinned?"取消置顶":"置顶"} ${h(n.title)}" data-action="pin" data-id="${n.id}">${usage.pinned?"📌":"📍"}</button>`:""}
        ${state.selectMode?`<button type="button" class="card-select" data-action="select" data-id="${n.id}" aria-pressed="${state.selectedIds.has(n.id)}" aria-label="${state.selectedIds.has(n.id)?'取消选择':'选择'} ${h(n.title)}">${state.selectedIds.has(n.id)?'✓':'○'}</button>`:''}
        ${reorderable && !state.selectMode?`<button type="button" class="small-action sort-grip" draggable="true" data-drag="${n.id}" title="拖动调整同级顺序，也可使用上下箭头键" aria-label="移动 ${h(n.title)}：拖动排序或按上下箭头键">⠿</button>`:""}
        ${!state.selectMode?`<button type="button" class="small-action card-more" title="更多操作" aria-label="更多操作：${h(n.title)}" data-action="menu" data-id="${n.id}">⋯</button>`:''}
        <button title="${n.favorite?'取消收藏':'加入收藏'}" class="small-action ${n.favorite?'on':''}" data-action="favorite" data-id="${n.id}">${n.favorite?'★':'☆'}</button>
        <button title="编辑模块" class="small-action" data-action="edit" data-id="${n.id}">✎</button>
        <button title="移除模块（不会删除真实文件夹）" class="small-action" data-action="delete" data-id="${n.id}">×</button>
      </div>
    </div>
    <button type="button" class="card-primary" data-action="primary" data-id="${n.id}" title="${primaryTitle}">
      <strong>${state.search?highlightSearch(n.title,state.search):h(n.title)}</strong><span class="type-chip ${n.node_type}">${TYPE_LABEL[n.node_type]||'模块'}</span>
      <span class="path" title="${h(n.folder_path||lineage)}">${state.search?highlightSearch(linked?n.folder_path:(leaf?'未设置有效文件夹':`${childCount} 个子模块`),state.search):h(linked?n.folder_path:(leaf?'未设置有效文件夹':`${childCount} 个子模块`))}</span>
      ${listContext}</button>
    ${state.search && state.layout!=="list"?`<div class="entry-lineage" title="${h(lineage)}">⌁ ${highlightSearch(lineage,state.search)}</div>`:''}
    ${recentCaption}
    <div class="card-bottom"><span class="pill ${linked?'linked':''}">${leaf?'● 文件夹入口':`${childCount} 个子模块`}</span>
      <div class="card-links">${state.search && !state.selectMode?`<button type="button" data-action="locate" data-id="${n.id}" title="定位到原目录，不打开文件夹">⌖ 定位</button>`:""}${!leaf?`<button data-action="enter" data-id="${n.id}">进入 ›</button>`:''}
        ${linked?`<button data-action="open" data-id="${n.id}">打开 ↗</button>`:''}
        ${linked && state.layout==="list"?`<button type="button" data-action="copy-path" data-id="${n.id}" title="复制关联的文件夹路径">复制路径</button>`:''}
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
function searchAll(term){
  const words=term.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  if(!words.length)return [];
  return searchRecords.filter(item=>words.every(word=>item.body.includes(word)))
    .sort((a,b)=>{
      const aOwn=words.every(word=>a.own.includes(word))?0:1;
      const bOwn=words.every(word=>b.own.includes(word))?0:1;
      return aOwn-bOwn || a.node.title.localeCompare(b.node.title,"zh-CN");
    }).map(item=>item.node);
}
function trashCard(item){
  const date=new Date(item.deleted_at);
  const dateText=Number.isNaN(date.getTime())?"未知时间":date.toLocaleString("zh-CN");
  return `<article class="trash-card" data-trash-id="${item.id}">
    <span class="trash-card-icon" aria-hidden="true">♻</span>
    <div class="trash-card-content"><strong>${h(item.title)}</strong>
      <span>${item.item_count} 条导航记录 · ${h(dateText)}</span></div>
    <div class="trash-card-actions">
      <button type="button" class="outline-btn" data-trash-action="restore" data-trash-id="${item.id}">恢复</button>
      <button type="button" class="outline-btn trash-purge" data-trash-action="purge" data-trash-id="${item.id}">永久清除</button>
    </div>
  </article>`;
}
function render(skipNav=false){
  if(state.view==="node" && !byId(state.selected)){
    state.view="all";state.selected=null;
    if(navigationReady)window.history.replaceState(navigationSnapshot(),"",routeUrl("all"));
  }
  if(!skipNav)renderNav();
  renderCrumb();
  const trashView=state.view==="trash"&&!state.search.trim();
  $("#newBtn").hidden=trashView || (state.view==="recent"&&!state.search.trim());
  $("#selectModeBtn").hidden=trashView;
  if(trashView){
    state.visibleIds=[];
    $("#sectionHeading").hidden=false;
    $("#sectionTitle").textContent="导航回收站";
    $("#sectionMeta").textContent="可恢复误删的模块、子模块及封面；不会触碰电脑中的真实文件夹";
    $("#sectionOperations").innerHTML="";
    $("#entries").className="entries trash-list";
    $("#entries").innerHTML=state.trash.length?state.trash.map(trashCard).join(""):
      '<div class="trash-empty"><span aria-hidden="true">♻</span><strong>回收站是空的</strong><p>移除的导航模块会暂存在这里，便于恢复。</p></div>';
    updateBatchBar();
    return;
  }
  let display,sectionTitle;
  const searching=state.search.trim();
  if(searching){display=searchAll(searching);sectionTitle="全局搜索结果";}
  else if(state.view==="favorites"){display=sorted(state.nodes.filter(n=>n.favorite));sectionTitle="常用入口";}
  else if(state.view==="recent"){
    display=state.recent.map(item=>byId(item.node_id)).filter(Boolean);
    sectionTitle="最近打开的文件夹";
  }
  else if(state.view==="node"){
    const node=byId(state.selected);
    display=node.node_type==="leaf"?[node]:children(state.selected);
    sectionTitle=node.node_type==="leaf"?"当前文件夹":"下级模块";
  } else{display=children(null);sectionTitle="根模块";}
  $("#sectionHeading").hidden=state.view==="all"&&!searching;
  $("#sectionTitle").textContent=sectionTitle;
  $("#sectionMeta").textContent=state.view==="recent"&&!searching?
    "置顶项目优先显示，其余按最近打开时间排列 · 只记录通过 FolderHub 打开的文件夹":
    `共 ${display.length} 个项目 · ${searching?'搜索覆盖整个目录树，结果显示完整所属层级':'叶子模块直接打开文件资源管理器'}`;
  const canAddChild=state.view==="node"&&!searching&&byId(state.selected)?.node_type!=="leaf";
  $("#newBtnText").textContent=canAddChild?"新建子模块":"新建根模块";
  $("#searchHint").textContent=searching?`${display.length} 项结果`:"Ctrl K";
  $("#sectionOperations").innerHTML=state.view==="node"&&!searching?
    `<button data-action="edit-current">编辑当前模块</button>`:
    state.view==="recent"&&!searching&&state.recent.length?
      '<button type="button" data-action="clear-recent" title="只清除访问记录，不删除导航模块或实际文件夹">清空访问记录</button>':"";
  $("#entries").className="entries"+(state.layout==="list"?" list":"");
  const reorderable=!state.selectMode && !searching && (state.view==="all" || (state.view==="node" && byId(state.selected)?.node_type!=="leaf"));
  const page=display.slice(0,state.renderLimit);
  state.visibleIds=page.map(n=>n.id);
  if(!searching || state.searchKeyboardIndex >= display.length)state.searchKeyboardIndex=-1;
  $("#entries").classList.toggle("selection-mode",state.selectMode);
  $("#entries").innerHTML=display.length?page.map((n,index)=>card(n,reorderable,Boolean(searching)&&index===state.searchKeyboardIndex)).join("")+
    (display.length>page.length?`<div class="load-more"><span>已显示 ${page.length} / ${display.length} 项</span><button type="button" class="outline-btn" data-action="load-more">加载更多模块 ↓</button></div>`:""):
    state.view==="recent"&&!searching?
      '<div class="empty-state"><div class="empty-art">◷</div><h3>还没有最近访问记录</h3><p>通过 FolderHub 打开文件夹后，会自动显示在这里。</p></div>':
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
  $("#entryPathRow").classList.toggle("hidden",t!=="leaf"&&!hasLegacyPath);
  $("#entryPathRequired").textContent=t==="leaf"?"（必填）":hasLegacyPath?"（旧版路径，仅保留使用）":"";
  $("#entryPath").required=t==="leaf";
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
  $("#entryFavorite").checked=!!node?.favorite;
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
    folder_path:type==="leaf"||(!$("#entryPathRow").classList.contains("hidden"))?$("#entryPath").value:null,
    parent_id:type==="root"?null:($("#entryParent").value?Number($("#entryParent").value):null),
    favorite:$("#entryFavorite").checked};
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
    closeDialog();await refresh();
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
    toast("已向 Windows 资源管理器发送打开指令，并尝试将窗口置前");
    try{
      state.recent=(await api("/api/recent")).items;
      $("#recentCount").textContent=state.recent.length;
      if(state.view==="recent"&&!state.search.trim())render(true);
    }catch(_){/* opening succeeded even if history refresh fails */}
  }catch(e){toast(e.message,true)}
  finally{
    state.openingIds.delete(id);
    document.getElementById(`folderhub-entry-${id}`)?.classList.remove("is-opening");
  }
}
async function removeNode(id){
  const n=byId(id);if(!n)return;
  const count=descendants(id).size-1;
  if(!confirm(`确定将「${n.title}」${count?`及其 ${count} 个下级模块`:''}移入导航回收站吗？\n\n真实文件夹不会被移动或删除，可在回收站恢复。`))return;
  try{const result=await mutate("DELETE",`/api/nodes/${id}`);await refresh();
    toast(`已移入回收站（共 ${result.deleted} 条导航记录）`,false,
      {label:"撤销",handler:()=>restoreTrash(result.trash_id)})}
  catch(e){toast(e.message,true)}
}
async function favoriteNode(id){
  const n=byId(id);if(!n)return;
  const hadCardFocus=Number(document.activeElement?.closest(".entry-card")?.dataset.id)===id;
  try{
    await mutate("PATCH",`/api/nodes/${id}`,{favorite:!n.favorite});
    await refresh();
    if(hadCardFocus)restoreCardFocus(id,"favorite");
  }catch(e){toast(e.message,true)}
}
async function toggleRecentPin(id){
  const visit=state.recent.find(row=>row.node_id===id);
  if(!visit)return;
  const hadCardFocus=Number(document.activeElement?.closest(".entry-card")?.dataset.id)===id;
  try{
    await mutate("POST","/api/recent/pin",{node_id:id,pinned:!Boolean(visit.pinned)});
    state.recent=(await api("/api/recent")).items;
    render();
    if(hadCardFocus)restoreCardFocus(id,"pin");
    toast(visit.pinned?"已取消置顶":"已置顶到最近使用顶部");
  }catch(e){toast("修改置顶失败："+e.message,true)}
}
async function clearRecentHistory(){
  if(!confirm("确定清空最近使用记录吗？\\n\\n只清除访问时间和次数，不会删除任何模块或电脑中的文件夹。"))return;
  try{
    const result=await mutate("DELETE","/api/recent",{});
    state.recent=[];render();toast(`已清空 ${result.cleared} 条访问记录`);
  }catch(e){toast("清空失败："+e.message,true)}
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
    case "favorite":await favoriteNode(id);break;
    case "empty-create":editDialog();break;
    case "edit-current":editDialog(state.selected);break;
    case "load-more":{
      const previous=state.visibleIds.length;
      state.renderLimit+=100;
      render(true);rememberNavigation();
      const firstNew=state.visibleIds[previous];
      if(firstNew!==undefined)
        document.getElementById(`folderhub-entry-${firstNew}`)?.querySelector(".card-primary")?.focus({preventScroll:true});
      break;
    }
    case "clear-recent":await clearRecentHistory();break;
    case "pin":await toggleRecentPin(id);break;
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
function updateBatchBar(){
  const bar=$("#bulkBar"),count=state.selectedIds.size;
  bar.classList.toggle("hidden",!state.selectMode);
  $("#bulkCount").textContent=`已选择 ${count} 项`;
  $("#selectModeBtn").setAttribute("aria-pressed",String(state.selectMode));
  $("#selectModeBtn").textContent=state.selectMode?"✓ 退出多选":"☑ 多选";
  for(const id of ["bulkFavorite","bulkUnfavorite","bulkDelete"]){$("#"+id).disabled=state.batchBusy||count===0}
  $("#bulkSelectAll").disabled=state.batchBusy||state.visibleIds.length===0;
  $("#bulkCancel").disabled=state.batchBusy;
}
async function batchAction(action){
  if(state.batchBusy||!state.selectedIds.size)return;
  const ids=[...state.selectedIds];
  if(action==="delete"){
    const all=new Set();ids.forEach(id=>descendants(id).forEach(x=>all.add(x)));
    if(!confirm(`确定移除选中的 ${ids.length} 个模块吗？\n其中包含子模块在内，共 ${all.size} 条导航记录。\n\n只删除 FolderHub 的导航记录与封面，不会删除或移动电脑中的真实文件夹。\n建议先备份配置。`))return;
  }
  state.batchBusy=true;updateBatchBar();
  try{
    const result=await mutate("POST","/api/batch",{action,ids});
    exitSelectMode();await refresh();
    if(action==="delete")toast(`已移入回收站（共 ${result.deleted} 条导航记录）`,false,
      {label:"撤销",handler:()=>restoreTrash(result.trash_id)});
    else toast(`已更新 ${result.changed} 个模块的收藏状态`);
  }catch(e){toast(e.message,true)}finally{state.batchBusy=false;updateBatchBar()}
}
async function restoreTrash(id){
  try{
    const result=await mutate("POST",`/api/trash/${id}/restore`);
    await refresh();
    toast(`已恢复 ${result.restored} 条导航记录及对应封面`);
  }catch(e){toast("恢复失败："+e.message,true)}
}
async function purgeTrash(id){
  const item=state.trash.find(x=>x.id===id);
  if(!item)return;
  if(!confirm(`永久清除「${item.title}」的回收站备份吗？\n\n清除后无法从回收站恢复导航记录和封面；电脑中的真实文件不受影响。`))return;
  try{await mutate("DELETE",`/api/trash/${id}`);await refresh();toast("回收站记录已永久清除（真实文件未受影响）")}
  catch(e){toast("清除失败："+e.message,true)}
}
function openCardMenu(id,x,y){
  closeCardMenu();
  const n=byId(id),menu=$("#cardContextMenu");
  if(!n||state.selectMode)return;
  state.contextId=id;
  const actions=[];
  if(n.node_type==="leaf"||n.folder_path)actions.push(["open","在资源管理器中打开"]);
  if(n.node_type!=="leaf")actions.push(["enter","进入模块"]);
  actions.push(["edit","编辑模块"],["favorite",n.favorite?"取消收藏":"添加到收藏"]);
  if(n.node_type!=="leaf")actions.push(["child","新建子模块"]);
  if(n.folder_path)actions.push(["copy-path","复制文件夹路径"]);
  actions.push(["delete","移除导航记录"]);
  menu.innerHTML=actions.map(([action,label])=>`<button type="button" role="menuitem" class="${action==='delete'?'menu-danger':''}" data-menu-action="${action}">${h(label)}</button>`).join("");
  menu.classList.remove("hidden");
  const bounds=menu.getBoundingClientRect();
  menu.style.left=Math.max(8,Math.min(x,window.innerWidth-bounds.width-8))+"px";
  menu.style.top=Math.max(8,Math.min(y,window.innerHeight-bounds.height-8))+"px";
  menu.querySelector("button")?.focus();
}
async function copyFolderPath(id){
  const folder=byId(id)?.folder_path;
  if(!folder){toast("该模块未关联文件夹",true);return}
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
  const limit=60;
  let result=shown.slice(0,limit).map(item=>{
    if(kind==="health")return `<div class="path-row"><strong>${h(item.title)}</strong><span class="path-warning">无法访问</span><code title="${h(item.path)}">${h(item.path)}</code></div>`;
    return `<div class="path-row"><strong>${h(item.title)}</strong><code title="${h(item.old_path)}">${h(item.old_path)}</code><span class="path-arrow">↓</span><code title="${h(item.new_path)}">${h(item.new_path)}</code></div>`;
  }).join("");
  if(shown.length>limit)result+=`<p class="settings-note">仅显示前 ${limit} 条，共 ${shown.length} 条记录。</p>`;
  return result;
}
async function checkPaths(){
  const button=$("#pathCheck");button.disabled=true;
  $("#pathHealthSummary").textContent="正在检查关联的文件夹... 网络盘可能需要一些时间。";
  try {
    const result=await mutate("POST","/api/paths/check");
    $("#pathHealthSummary").textContent=`已检查 ${result.total} 条：可访问 ${result.accessible}，不可访问 ${result.missing}。`;
    $("#pathHealthList").innerHTML=result.missing?pathRows(result.items,"health"):'<p class="path-success">✓ 所有已关联文件夹均可访问。</p>';
  }catch(e){$("#pathHealthSummary").textContent="检查失败："+e.message;$("#pathHealthList").replaceChildren();toast(e.message,true)}
  finally{button.disabled=false}
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
    $("#pathHealthSummary").textContent="关联路径已更新，请重新执行检查。";
    $("#pathHealthList").replaceChildren();
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
  const knownRecent=new Map(state.recent.map((row,index)=>[row.node_id,{...row,index}]));
  if(term){
    const lower=term.toLocaleLowerCase();
    const matches=searchAll(term);
    return matches.map(node=>{
      const visit=knownRecent.get(node.id),title=node.title.toLocaleLowerCase();
      let score=title===lower?0:title.startsWith(lower)?1:2;
      if(node.favorite)score-=.35;
      if(visit?.pinned)score-=.45;
      else if(visit)score-=.12;
      return {node,visit,score};
    }).sort((a,b)=>a.score-b.score||a.node.title.localeCompare(b.node.title,"zh-CN")).slice(0,12);
  }
  const seen=new Set(),results=[];
  const add=node=>{
    if(!node||seen.has(node.id))return;
    seen.add(node.id);results.push({node,visit:knownRecent.get(node.id)||null});
  };
  // Pin first; then favorites; then recent folders; finally root modules.
  for(const visit of state.recent)if(visit.pinned)add(byId(visit.node_id));
  for(const node of sorted(state.nodes.filter(n=>n.favorite)))add(node);
  for(const visit of state.recent)add(byId(visit.node_id));
  for(const node of children(null))add(node);
  return results.slice(0,12);
}
function renderQuickPalette(){
  const term=$("#quickInput").value;
  quickPalette.items=quickCandidates(term);
  const results=$("#quickResults");
  if(!quickPalette.items.length){
    quickPalette.selected=-1;
    results.innerHTML='<div class="quick-empty">没有匹配的模块。可返回首页新建或修改导航模块。</div>';
    $("#quickInput").removeAttribute("aria-activedescendant");
    return;
  }
  quickPalette.selected=0;
  results.innerHTML=quickPalette.items.map(({node,visit},index)=>{
    const path=node.folder_path||ancestors(node.id).map(n=>n.title).join(" / ");
    const kinds=[visit?.pinned?"置顶":null,node.favorite?"收藏":null,visit&&!visit.pinned?"最近使用":null].filter(Boolean);
    const suffix=kinds.length?kinds.join(" · "):node.node_type==="leaf"?"文件夹":"模块";
    return `<button type="button" class="quick-result" id="quick-option-${index}" role="option" aria-selected="false" data-quick-index="${index}">
      <span class="quick-icon" aria-hidden="true">${h(iconFor(node))}</span>
      <span class="quick-details"><strong>${term?highlightSearch(node.title,term):h(node.title)}</strong>
        <small title="${h(path)}">${term?highlightSearch(path,term):h(path)}</small></span>
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
     !$("#settingsLayer").classList.contains("hidden"))return;
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
  if(node.node_type==="leaf"&&!node.folder_path){
    toast("该叶子模块尚未绑定文件夹，请先编辑模块",true);
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

function bind(){
  bindSorting();
  bindQuickPalette();
  window.addEventListener("popstate",restoreBrowserNavigation);
  $("#selectModeBtn").addEventListener("click",()=>{if(state.batchBusy)return;state.selectMode=!state.selectMode;state.selectedIds.clear();closeCardMenu();render(true)});
  $("#bulkCancel").addEventListener("click",()=>{exitSelectMode();render(true)});
  $("#bulkSelectAll").addEventListener("click",()=>{if(state.batchBusy)return;const ids=state.visibleIds;if(ids.length>200){toast("已显示模块超过 200 项，请缩小搜索范围",true);return}state.selectedIds=new Set(ids);render(true)});
  $("#bulkFavorite").addEventListener("click",()=>batchAction("favorite"));
  $("#bulkUnfavorite").addEventListener("click",()=>batchAction("unfavorite"));
  $("#bulkDelete").addEventListener("click",()=>batchAction("delete"));
  $("#cardContextMenu").addEventListener("click",e=>{const btn=e.target.closest("[data-menu-action]");if(btn&&state.contextId!==null)contextAction(btn.dataset.menuAction,state.contextId)});
  $("#entries").addEventListener("contextmenu",e=>{const card=e.target.closest(".entry-card");if(!card||e.target.closest("input,textarea"))return;e.preventDefault();openCardMenu(Number(card.dataset.id),e.clientX,e.clientY)});
  $("#entries").addEventListener("keydown",e=>{if((e.key==="F10"&&e.shiftKey)||e.key==="ContextMenu"){const card=e.target.closest(".entry-card");if(!card)return;e.preventDefault();const r=card.getBoundingClientRect();openCardMenu(Number(card.dataset.id),r.left+32,r.top+32)}});
  document.addEventListener("pointerdown",e=>{if(!e.target.closest("#cardContextMenu"))closeCardMenu()});
  $("#specialNav").addEventListener("click",e=>{const item=e.target.closest("[data-view]");if(item)setView(item.dataset.view)});
  $("#treeNav").addEventListener("click",e=>{
    const toggle=e.target.closest("[data-toggle]");
    if(toggle){toggleBranch(Number(toggle.dataset.toggle));return}
    const item=e.target.closest("[data-node]");if(!item)return;
    const id=Number(item.dataset.node);const n=byId(id);
    setView("node",id);if(n?.node_type==="leaf")openFolder(id);
  });
  $("#breadcrumb").addEventListener("click",e=>{const item=e.target.closest("[data-crumb]");if(item)item.dataset.crumb==="all"?setView("all"):setView("node",Number(item.dataset.crumb))});
  $("#entries").addEventListener("click",e=>{
    const trashButton=e.target.closest("[data-trash-action]");
    if(trashButton){
      const id=Number(trashButton.dataset.trashId);
      if(trashButton.dataset.trashAction==="restore")restoreTrash(id);
      else if(trashButton.dataset.trashAction==="purge")purgeTrash(id);
      return;
    }
    const btn=e.target.closest("[data-action]");
    if(btn)act(btn.dataset.action,Number(btn.dataset.id));
  });
  $("#sectionOperations").addEventListener("click",e=>{const btn=e.target.closest("[data-action]");if(btn)act(btn.dataset.action,state.selected)});
  $("#addRoot").addEventListener("click",()=>editDialog(null,null));
  $("#newBtn").addEventListener("click",()=>editDialog());
  $("#search").addEventListener("input",e=>{closeCardMenu();state.selectedIds.clear();state.search=e.target.value;state.searchKeyboardIndex=-1;state.renderLimit=100;render(true);rememberNavigation()});
  $("#search").addEventListener("keydown",async e=>{
    if(!state.search.trim())return;
    if(e.key==="Escape"){
      e.preventDefault();e.stopPropagation();state.search="";state.searchKeyboardIndex=-1;
      $("#search").value="";state.renderLimit=100;render(true);rememberNavigation();return;
    }
    if(!["ArrowDown","ArrowUp","Enter"].includes(e.key))return;
    const results=searchAll(state.search);
    if(!results.length)return;
    if(state.selectMode && e.key==="Enter")return;
    e.preventDefault();e.stopPropagation();
    if(e.key==="Enter"){
      const index=state.searchKeyboardIndex<0?0:Math.min(state.searchKeyboardIndex,results.length-1);
      await act("primary",results[index].id);return;
    }
    const old=state.searchKeyboardIndex;
    state.searchKeyboardIndex=e.key==="ArrowDown"?(old+1)%results.length:
      old<0?results.length-1:(old-1+results.length)%results.length;
    if(state.searchKeyboardIndex>=state.renderLimit)
      state.renderLimit=Math.ceil((state.searchKeyboardIndex+1)/100)*100;
    render(true);rememberNavigation();
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
  $("#pathCheck").addEventListener("click",checkPaths);
  $("#pathPreview").addEventListener("click",previewPaths);
  $("#pathApply").addEventListener("click",applyPaths);
  for(const selector of ["#pathPrefixFrom","#pathPrefixTo"]){
    $(selector).addEventListener("input",clearPathPlan);
  }
  $("#importFile").addEventListener("change",async e=>{await restoreBackup(e.target.files[0]);e.target.value=""});
  $("#entryForm").addEventListener("submit",submitDialog);
  $("#entryType").addEventListener("change",updateEntryType);
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
