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
// All presentation preferences are browser-local; SQLite navigation records are never changed.
const PREF_DEFAULTS = Object.freeze({font:"large",density:"comfortable",sidebar:"normal",columns:"auto",accent:"blue",sidebarCollapsed:false});
const PREF_ALLOWED = {font:["normal","large","xlarge"],density:["comfortable","compact"],sidebar:["normal","wide"],columns:["auto","2","3","4"],accent:["blue","purple","teal","orange","rose"]};
function readPreferences(){
  try {
    const stored=JSON.parse(localStorage.getItem("folderhub.appearance")||"{}");
    if(!stored || typeof stored!=="object" || Array.isArray(stored))return {...PREF_DEFAULTS};
    const result={...PREF_DEFAULTS};
    for(const [key,values] of Object.entries(PREF_ALLOWED))if(values.includes(stored[key]))result[key]=stored[key];
    for(const key of ["sidebarCollapsed"])if(typeof stored[key]==="boolean")result[key]=stored[key];
    return result;
  } catch(_){return {...PREF_DEFAULTS}}
}
let preferences=readPreferences();
function applyPreferences(){
  const root=document.documentElement;
  root.dataset.font=preferences.font;
  root.dataset.density=preferences.density;
  root.dataset.sidebarWidth=preferences.sidebar;
  root.dataset.columns=preferences.columns;
  root.dataset.accent=preferences.accent;
  root.dataset.sidebarCollapsed=String(preferences.sidebarCollapsed);
  const trigger=document.querySelector("#sidebarToggle");
  if(trigger)trigger.setAttribute("aria-expanded",String(!preferences.sidebarCollapsed));
}
function updateAppearanceControls(){
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
  try{localStorage.setItem("folderhub.appearance",JSON.stringify(preferences))}catch(_){}
  applyPreferences();updateAppearanceControls();
}
const validTheme = theme => THEMES.some(t=>t.id===theme) ? theme : "cloud";
function getSavedTheme(){try{return validTheme(localStorage.getItem("folderhub.theme") || "cloud")}catch(_){return "cloud"}}
const state = {openingIds:new Set(),nodes:[], token:"", view:"all", selected:null, search:"", layout:"grid", editing:null, theme:getSavedTheme(), startup:null, expanded:new Set(), treeInitialized:false};
document.documentElement.dataset.theme=state.theme;
applyPreferences();
const $ = (s) => document.querySelector(s);
const h = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let toastTimer;
const byId = id => state.nodes.find(n => n.id === id);
const sorted = nodes => [...nodes].sort((a,b)=>a.sort_order-b.sort_order || a.id-b.id);
const children = id => sorted(state.nodes.filter(n=>n.parent_id===id));

function toast(message, error=false) {
  const el=$("#toast"); el.textContent=message; el.className="toast show"+(error?" error":"");
  clearTimeout(toastTimer);toastTimer=setTimeout(()=>{el.className="toast"},3600);
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
function saveTreeState(){try{localStorage.setItem("folderhub.expanded",JSON.stringify([...state.expanded]))}catch(_){}}
function expandLineage(id){
  for(const node of ancestors(id)){if(node.node_type!=="leaf")state.expanded.add(node.id)}
  saveTreeState();
}
async function refresh(){
  const data=await api("/api/nodes");state.nodes=data.nodes;
  if(!state.treeInitialized){
    const saved=loadTreeState();
    state.expanded=new Set(Array.isArray(saved)?saved.filter(id=>Number.isInteger(id)):children(null).map(n=>n.id));
    state.treeInitialized=true;
  }
  if(state.view==="node"&&state.selected!==null)expandLineage(state.selected);
  render();
}

function descendants(id) {
  const found=new Set([id]);
  let changed=true;
  while(changed){changed=false;for(const n of state.nodes){if(n.parent_id!==null && found.has(n.parent_id) && !found.has(n.id)){found.add(n.id);changed=true}}}
  return found;
}
function ancestors(id) {
  const result=[], visited=new Set();let current=byId(id);
  while(current && !visited.has(current.id)){result.unshift(current);visited.add(current.id);current=byId(current.parent_id)}
  return result;
}
function setView(view,id=null){
  state.view=view;state.selected=id;
  state.search="";$("#search").value="";
  if(view==="node"&&id!==null)expandLineage(id);
  render();
}
const TYPE_LABEL = {root:"根模块",group:"普通模块",leaf:"叶子模块"};
function toggleBranch(id){
  if(state.expanded.has(id))state.expanded.delete(id);else state.expanded.add(id);
  saveTreeState();renderNav();
}
function renderNav(){
  const roots=children(null), fav=state.nodes.filter(n=>n.favorite);
  $("#rootCount").textContent=roots.length;$("#favoriteCount").textContent=fav.length;
  document.querySelectorAll("#specialNav [data-view]").forEach(el=>el.classList.toggle("active",state.view===el.dataset.view));
  const walk=(nodes) => nodes.map(n=>{
    const sub=children(n.id), expand=sub.length>0 && state.expanded.has(n.id), isLeaf=n.node_type==="leaf";
    return `<div class="tree-branch" role="group">
      <div class="tree-row ${state.view==='node'&&state.selected===n.id?'active':''}">
        ${sub.length?`<button type="button" class="tree-toggle" data-toggle="${n.id}" aria-expanded="${expand}" aria-label="${expand?'折叠':'展开'} ${h(n.title)}"><span class="tree-chevron ${expand?'is-open':''}">›</span></button>`
          :'<span class="tree-spacer" aria-hidden="true"></span>'}
        <button type="button" class="tree-item" data-node="${n.id}" title="${h(n.title)} (${TYPE_LABEL[n.node_type]||'模块'})">
          <span class="tree-folder" aria-hidden="true">${isLeaf?'▣':n.node_type==='root'?'▤':'▥'}</span>
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
  if(state.view==="node"){
    for(const n of ancestors(state.selected)){
      bits.push(`<span>›</span><button type="button" data-crumb="${n.id}">${h(n.title)}</button>`);
    }
  }
  $("#breadcrumb").innerHTML=bits.join("");
}
function card(n){
  const childCount=children(n.id).length;
  const linked=!!n.folder_path;
  const leaf=n.node_type==="leaf";
  const lineage=ancestors(n.id).map(a=>a.title).join(" / ");
  const primaryTitle=leaf?"在 Windows 资源管理器打开文件夹":"进入此模块";
  return `<article class="entry-card ${leaf?"is-leaf":"is-container"} ${state.openingIds.has(n.id)?"is-opening":""}" data-id="${n.id}">
    <div class="card-head"><span class="folder-icon ${linked?'':'unlinked'}">${leaf?'▣':n.node_type==='root'?'▤':'▥'}</span>
      <div class="card-actions">
        <button title="${n.favorite?'取消收藏':'加入收藏'}" class="small-action ${n.favorite?'on':''}" data-action="favorite" data-id="${n.id}">${n.favorite?'★':'☆'}</button>
        <button title="编辑模块" class="small-action" data-action="edit" data-id="${n.id}">✎</button>
        <button title="移除模块（不会删除真实文件夹）" class="small-action" data-action="delete" data-id="${n.id}">×</button>
      </div>
    </div>
    <button type="button" class="card-primary" data-action="primary" data-id="${n.id}" title="${primaryTitle}">
      <strong>${h(n.title)}</strong><span class="type-chip ${n.node_type}">${TYPE_LABEL[n.node_type]||'模块'}</span>
      <span class="path" title="${h(n.folder_path||lineage)}">${h(linked?n.folder_path:(leaf?'未设置有效文件夹':`${childCount} 个子模块`))}</span></button>
    ${state.search?`<div class="entry-lineage" title="${h(lineage)}">⌁ ${h(lineage)}</div>`:''}
    <div class="card-bottom"><span class="pill ${linked?'linked':''}">${leaf?'● 文件夹入口':`${childCount} 个子模块`}</span>
      <div class="card-links">${!leaf?`<button data-action="enter" data-id="${n.id}">进入 ›</button>`:''}
        ${linked?`<button data-action="open" data-id="${n.id}">打开 ↗</button>`:''}
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
  return state.nodes.map(n=>{
    const own=(n.title+" "+(n.folder_path||"")).toLocaleLowerCase();
    const full=ancestors(n.id).map(x=>x.title).join(" /").toLocaleLowerCase();
    const body=own+" "+full;
    if(!words.every(w=>body.includes(w)))return null;
    return {node:n,score:words.every(w=>own.includes(w))?0:1};
  }).filter(Boolean).sort((a,b)=>a.score-b.score||a.node.title.localeCompare(b.node.title,"zh-CN")).map(x=>x.node);
}
function render(){
  if(state.view==="node" && !byId(state.selected)){state.view="all";state.selected=null}
  renderNav();renderCrumb();
  let display,sectionTitle;
  const searching=state.search.trim();
  if(searching){
    display=searchAll(searching);sectionTitle="全局搜索结果";
  } else if(state.view==="favorites"){
    display=sorted(state.nodes.filter(n=>n.favorite));sectionTitle="常用入口";
  } else if(state.view==="node"){
    const node=byId(state.selected);
    display=node.node_type==="leaf"?[node]:children(state.selected);
    sectionTitle=node.node_type==="leaf"?"当前文件夹":"下级模块";
  } else {
    // Home only shows top-level root modules.
    display=children(null);sectionTitle="根模块";
  }
  $("#sectionHeading").hidden=state.view==="all"&&!searching;
  $("#sectionTitle").textContent=sectionTitle;
  $("#sectionMeta").textContent=`共 ${display.length} 个项目 · ${searching?'搜索覆盖整个目录树，结果显示完整所属层级':'叶子模块直接打开文件资源管理器'}`;
  const canAddChild=state.view==="node"&&!searching&&byId(state.selected)?.node_type!=="leaf";
  $("#newBtnText").textContent=canAddChild?"新建子模块":"新建根模块";
  $("#searchHint").textContent=searching?`${display.length} 项结果`:"Ctrl K";
  $("#sectionOperations").innerHTML=state.view==="node"&&!searching?`<button data-action="edit-current">编辑当前模块</button>`:"";
  $("#entries").className="entries"+(state.layout==="list"?" list":"");
  $("#entries").innerHTML=display.length?display.map(card).join(""):emptyView();
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
function closeDialog(){$("#dialogLayer").classList.add("hidden");state.editing=null}
async function submitDialog(event){
  event.preventDefault();
  const type=$("#entryType").value;
  const payload={title:$("#entryName").value,node_type:type,
    folder_path:type==="leaf"||(!$("#entryPathRow").classList.contains("hidden"))?$("#entryPath").value:null,
    parent_id:type==="root"?null:($("#entryParent").value?Number($("#entryParent").value):null),
    favorite:$("#entryFavorite").checked};
  const button=$("#submitEntry");button.disabled=true;
  try {
    const savedId=state.editing;
    let created;
    if(savedId!==null)await mutate("PATCH",`/api/nodes/${savedId}`,payload);
    else created=await mutate("POST","/api/nodes",payload);
    closeDialog();await refresh();
    if(savedId!==null)expandLineage(savedId);
    else if(type==="root"&&created?.id)state.expanded.add(created.id);
    else if(created?.id)expandLineage(created.id);
    saveTreeState();render();toast("模块已保存");
  }catch(e){toast(e.message,true)}finally{button.disabled=false}
}
async function openFolder(id){
  if(state.openingIds.has(id))return;
  state.openingIds.add(id);render();
  try{
    await mutate("POST",`/api/nodes/${id}/open`);
    toast("已向 Windows 资源管理器发送打开指令，并尝试将窗口置前");
  }catch(e){toast(e.message,true)}
  finally{state.openingIds.delete(id);render()}
}
async function removeNode(id){
  const n=byId(id);if(!n)return;
  const count=descendants(id).size-1;
  if(!confirm(`确定移除「${n.title}」${count?`及其 ${count} 个下级模块`:''}吗？\n\n只删除导航记录，不会删除电脑中的任何文件和文件夹。`))return;
  try{await mutate("DELETE",`/api/nodes/${id}`);await refresh();toast("导航记录已移除，真实文件夹未受影响")}
  catch(e){toast(e.message,true)}
}
async function favoriteNode(id){
  const n=byId(id);if(!n)return;
  try{await mutate("PATCH",`/api/nodes/${id}`,{favorite:!n.favorite});await refresh()}
  catch(e){toast(e.message,true)}
}
async function act(action,id){
  switch(action){
    case "primary":{const n=byId(id);if(n?.node_type==="leaf")await openFolder(id);else setView("node",id);break}
    case "open":await openFolder(id);break;
    case "enter":setView("node",id);break;
    case "child":if(byId(id)?.node_type!=="leaf")editDialog(null,id);else toast("叶子模块不能拥有子模块",true);break;
    case "edit":editDialog(id);break;
    case "delete":await removeNode(id);break;
    case "favorite":await favoriteNode(id);break;
    case "empty-create":editDialog();break;
    case "edit-current":editDialog(state.selected);break;
  }
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
    if(file.size>2*1024*1024)throw new Error("配置文件不能超过 2 MB");
    const payload=JSON.parse(await file.text());
    await mutate("POST","/api/import",payload);
    state.view="all";state.selected=null;state.search="";$("#search").value="";
    await refresh();toast("导航配置已恢复；电脑中的文件没有被修改");
  }catch(e){toast("恢复失败："+e.message,true)}
}
function setTheme(theme) {
  state.theme=validTheme(theme);
  document.documentElement.dataset.theme=state.theme;
  try{localStorage.setItem("folderhub.theme",state.theme)}catch(_){/* private mode may block storage */}
  renderThemeOptions();
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
  const current=tab==="launch"?"launch":"appearance";
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

function bind(){
  $("#specialNav").addEventListener("click",e=>{const item=e.target.closest("[data-view]");if(item)setView(item.dataset.view)});
  $("#treeNav").addEventListener("click",e=>{
    const toggle=e.target.closest("[data-toggle]");
    if(toggle){toggleBranch(Number(toggle.dataset.toggle));return}
    const item=e.target.closest("[data-node]");if(!item)return;
    const id=Number(item.dataset.node);const n=byId(id);
    setView("node",id);if(n?.node_type==="leaf")openFolder(id);
  });
  $("#breadcrumb").addEventListener("click",e=>{const item=e.target.closest("[data-crumb]");if(item)item.dataset.crumb==="all"?setView("all"):setView("node",Number(item.dataset.crumb))});
  $("#entries").addEventListener("click",e=>{const btn=e.target.closest("[data-action]");if(btn)act(btn.dataset.action,Number(btn.dataset.id))});
  $("#sectionOperations").addEventListener("click",e=>{const btn=e.target.closest("[data-action]");if(btn)act(btn.dataset.action,state.selected)});
  $("#addRoot").addEventListener("click",()=>editDialog(null,null));
  $("#newBtn").addEventListener("click",()=>editDialog());
  $("#search").addEventListener("input",e=>{state.search=e.target.value;render()});
  $("#layoutBtn").addEventListener("click",()=>{state.layout=state.layout==="grid"?"list":"grid";$("#layoutBtn").textContent=state.layout==="grid"?"▦":"☷";render()});
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
  $("#resetAppearance").addEventListener("click",()=>{preferences={...PREF_DEFAULTS};savePreferences();toast("布局与字号已恢复默认")});
  $("#sidebarToggle").addEventListener("click",()=>{preferences.sidebarCollapsed=!preferences.sidebarCollapsed;savePreferences()});
  $("#startupToggle").addEventListener("change",e=>changeStartup(e.target.checked));
  $("#copyHomepage").addEventListener("click",copyHomepage);
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
    if(e.key==="Escape"&&!$("#dialogLayer").classList.contains("hidden"))closeDialog();
    if(e.key==="Escape"&&!$("#settingsLayer").classList.contains("hidden"))closeSettings();
    if(e.key.toLowerCase()==="k"&&(e.ctrlKey||e.metaKey)){e.preventDefault();$("#search").focus();$("#search").select()}
  });
}
async function init(){
  bind();
  applyPreferences();
  try{const c=await api("/api/config");state.token=c.token;await refresh();if(c.platform!=="win32")toast("当前非 Windows 系统，浏览和打开资源管理器功能不可用",true)}
  catch(e){toast(e.message,true);$("#entries").innerHTML=`<div class="empty-state"><h3>本地服务无法连接</h3><p>${h(e.message)}</p></div>`}
}
init();
