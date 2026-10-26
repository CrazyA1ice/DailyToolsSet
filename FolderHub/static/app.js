"use strict";

const state = {nodes:[], token:"", view:"all", selected:null, search:"", layout:"grid", editing:null};
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
  catch(e) {throw new Error("本地服务连接失败，请确认启动窗口仍然打开");}
  let data;
  try {data=await response.json()} catch(e){throw new Error("服务器响应无效")}
  if(!response.ok) throw new Error(data.error||`操作失败 (${response.status})`);
  return data;
}
const mutate = (method,path,data={}) => api(path,{method,body:JSON.stringify(data)});
async function refresh(){const data=await api("/api/nodes");state.nodes=data.nodes;render()}

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
function setView(view,id=null){state.view=view;state.selected=id;state.search="";$("#search").value="";render()}
function renderNav(){
  const roots=children(null), fav=state.nodes.filter(n=>n.favorite);
  $("#rootCount").textContent=roots.length;$("#favoriteCount").textContent=fav.length;
  document.querySelectorAll("#specialNav [data-view]").forEach(el=>el.classList.toggle("active",state.view===el.dataset.view));
  const walk=(nodes,depth=0) => nodes.map(n=>{
    const count=children(n.id).length;
    return `<button type="button" data-node="${n.id}" class="tree-item ${state.view==='node'&&state.selected===n.id?'active':''}" style="padding-left:${12+depth*13}px" title="${h(n.title)}">
      <span class="tree-arrow">${count?'›':'·'}</span><span class="tree-folder">▤</span><span class="tree-text">${h(n.title)}</span></button>${walk(children(n.id),depth+1)}`;
  }).join("");
  $("#treeNav").innerHTML=walk(roots);
}
function renderCrumb(){
  const bits=[`<button type="button" data-crumb="all">首页</button>`];
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
  return `<article class="entry-card" data-id="${n.id}">
    <div class="card-head"><span class="folder-icon ${linked?'':'unlinked'}">${linked?'▣':'▤'}</span>
      <div class="card-actions">
        <button title="${n.favorite?'取消收藏':'加入收藏'}" class="small-action ${n.favorite?'on':''}" data-action="favorite" data-id="${n.id}">${n.favorite?'★':'☆'}</button>
        <button title="编辑模块" class="small-action" data-action="edit" data-id="${n.id}">✎</button>
        <button title="移除模块（不会删除真实文件夹）" class="small-action" data-action="delete" data-id="${n.id}">×</button>
      </div>
    </div>
    <button type="button" class="card-primary" data-action="primary" data-id="${n.id}" title="${linked?'在 Windows 资源管理器打开文件夹':'进入子模块'}">
      <strong>${h(n.title)}</strong><span class="path">${linked?h(n.folder_path):'导航分类 · 尚未绑定文件夹'}</span></button>
    <div class="card-bottom"><span class="pill ${linked?'linked':''}">${linked?'● 已关联':`${childCount} 个子模块`}</span>
      <div class="card-links">${childCount?`<button data-action="enter" data-id="${n.id}">进入子级 ›</button>`:''}
        ${linked?`<button data-action="open" data-id="${n.id}">打开 ↗</button>`:''}
        <button data-action="child" data-id="${n.id}">＋ 子模块</button>
      </div></div>
  </article>`;
}
function emptyView(){
  const searching=!!state.search;
  return `<div class="empty-state"><div class="empty-art">${searching?'⌕':'▤'}</div><h3>${searching?'没有找到匹配的文件夹':'还没有模块'}</h3>
    <p>${searching?'换个名称或路径关键词试试':'点击“新建模块”，建立你的第一层文件夹导航。'}</p>
    ${searching?'':`<button class="primary-btn" data-action="empty-create">＋ 创建模块</button>`}</div>`;
}
function render(){
  if(state.view==="node" && !byId(state.selected)){state.view="all";state.selected=null}
  renderNav();renderCrumb();
  $("#nodeCount").textContent=state.nodes.length;
  $("#linkedCount").textContent=state.nodes.filter(n=>n.folder_path).length;
  $("#favStat").textContent=state.nodes.filter(n=>n.favorite).length;
  let display,title,subtitle,sectionTitle;
  const searching=state.search.trim().toLocaleLowerCase();
  if(searching){display=state.nodes.filter(n=>(n.title+" "+(n.folder_path||"")).toLocaleLowerCase().includes(searching));sectionTitle="搜索结果";title="快速查找文件夹";subtitle="全局检索所有模块、子模块和已保存的文件夹路径。";}
  else if(state.view==="favorites"){display=sorted(state.nodes.filter(n=>n.favorite));title="我的收藏";subtitle="重要的文件夹，总是在触手可及的位置。";sectionTitle="常用文件夹";}
  else if(state.view==="node") {const node=byId(state.selected);display=children(state.selected);title=node.title;subtitle=node.folder_path||"查看子模块，或者为此模块设置文件夹路径。";sectionTitle="下级模块";}
  else{display=children(null);title="我的文件导航";subtitle="用清晰的分类，快速抵达电脑上的每一个工作文件夹。";sectionTitle="全部分类";}
  $("#pageTitle").textContent=title;
  $("#pageSubtitle").textContent=subtitle;
  $("#sectionTitle").textContent=sectionTitle;
  $("#sectionMeta").textContent=`共 ${display.length} 个项目 · ${searching?'搜索覆盖所有层级':'点击已绑定的模块卡片可打开系统文件资源管理器'}`;
  $("#newBtnText").textContent=state.view==="node"&&!searching?"新建子模块":"新建模块";
  $("#searchHint").textContent=searching?`${display.length} 项结果`:"全局搜索";
  $("#sectionOperations").innerHTML=state.view==="node"&&!searching?`<button data-action="edit-current">编辑当前模块</button>`:"";
  $("#entries").className="entries"+(state.layout==="list"?" list":"");
  $("#entries").innerHTML=display.length?display.map(card).join(""):emptyView();
}
function editDialog(id=null,parentId=undefined){
  state.editing=id;
  const node=id===null?null:byId(id);
  $("#dialogTitle").textContent=node?"编辑模块":"新建模块";
  $("#entryName").value=node?.title||"";
  $("#entryPath").value=node?.folder_path||"";
  $("#entryFavorite").checked=!!node?.favorite;
  const disabled = node?descendants(node.id):new Set();
  const options=[`<option value="">顶级模块（无上级）</option>`];
  const walk=(nodes,depth)=>nodes.forEach(n=>{
    if(disabled.has(n.id))return;
    options.push(`<option value="${n.id}">${h("　".repeat(depth)+n.title)}</option>`);
    walk(children(n.id),depth+1);
  });walk(children(null),0);
  $("#entryParent").innerHTML=options.join("");
  const defaultParent=node?node.parent_id:(parentId!==undefined?parentId:(state.view==="node"?state.selected:null));
  $("#entryParent").value=defaultParent===null?"":String(defaultParent);
  $("#dialogLayer").classList.remove("hidden");
  $("#entryName").focus();
}
function closeDialog(){$("#dialogLayer").classList.add("hidden");state.editing=null}
async function submitDialog(event){
  event.preventDefault();
  const payload={title:$("#entryName").value,folder_path:$("#entryPath").value,parent_id:$("#entryParent").value?Number($("#entryParent").value):null,favorite:$("#entryFavorite").checked};
  const button=$("#submitEntry");button.disabled=true;
  try {
    if(state.editing!==null)await mutate("PATCH",`/api/nodes/${state.editing}`,payload);
    else await mutate("POST","/api/nodes",payload);
    closeDialog();await refresh();toast("模块已保存");
  }catch(e){toast(e.message,true)}finally{button.disabled=false}
}
async function openFolder(id){
  try{await mutate("POST",`/api/nodes/${id}/open`);toast("已在 Windows 资源管理器打开文件夹")}
  catch(e){toast(e.message,true)}
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
    case "primary":case "open":{const n=byId(id);if(n?.folder_path)await openFolder(id);else setView("node",id);break}
    case "enter":setView("node",id);break;
    case "child":editDialog(null,id);break;
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
function bind(){
  $("#specialNav").addEventListener("click",e=>{const item=e.target.closest("[data-view]");if(item)setView(item.dataset.view)});
  $("#treeNav").addEventListener("click",e=>{const item=e.target.closest("[data-node]");if(item)setView("node",Number(item.dataset.node))});
  $("#breadcrumb").addEventListener("click",e=>{const item=e.target.closest("[data-crumb]");if(item)item.dataset.crumb==="all"?setView("all"):setView("node",Number(item.dataset.crumb))});
  $("#entries").addEventListener("click",e=>{const btn=e.target.closest("[data-action]");if(btn)act(btn.dataset.action,Number(btn.dataset.id))});
  $("#sectionOperations").addEventListener("click",e=>{const btn=e.target.closest("[data-action]");if(btn)act(btn.dataset.action,state.selected)});
  $("#addRoot").addEventListener("click",()=>editDialog(null,null));
  $("#newBtn").addEventListener("click",()=>editDialog());
  $("#search").addEventListener("input",e=>{state.search=e.target.value;render()});
  $("#layoutBtn").addEventListener("click",()=>{state.layout=state.layout==="grid"?"list":"grid";$("#layoutBtn").textContent=state.layout==="grid"?"▦":"☷";render()});
  $("#backupBtn").addEventListener("click",exportBackup);
  $("#restoreBtn").addEventListener("click",()=>$("#importFile").click());
  $("#importFile").addEventListener("change",async e=>{await restoreBackup(e.target.files[0]);e.target.value=""});
  $("#entryForm").addEventListener("submit",submitDialog);
  $("#dialogClose").addEventListener("click",closeDialog);
  $("#cancelDialog").addEventListener("click",closeDialog);
  $("#dialogLayer").addEventListener("click",e=>{if(e.target===$("#dialogLayer"))closeDialog()});
  $("#pickFolder").addEventListener("click",async()=>{const btn=$("#pickFolder");btn.disabled=true;try{const d=await mutate("POST","/api/pick-folder");if(d.path)$("#entryPath").value=d.path}catch(e){toast(e.message,true)}finally{btn.disabled=false}});
  document.addEventListener("keydown",e=>{
    if(e.key==="Escape"&&!$("#dialogLayer").classList.contains("hidden"))closeDialog();
    if(e.key.toLowerCase()==="k"&&(e.ctrlKey||e.metaKey)){e.preventDefault();$("#search").focus();$("#search").select()}
  });
}
async function init(){
  bind();
  try{const c=await api("/api/config");state.token=c.token;await refresh();if(c.platform!=="win32")toast("当前非 Windows 系统，浏览和打开资源管理器功能不可用",true)}
  catch(e){toast(e.message,true);$("#entries").innerHTML=`<div class="empty-state"><h3>本地服务无法连接</h3><p>${h(e.message)}</p></div>`}
}
init();
