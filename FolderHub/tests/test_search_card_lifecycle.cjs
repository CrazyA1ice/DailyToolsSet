// Runs actual FolderHub search/card functions against a dependency-free DOM mock.
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "static", "app.js"), "utf8");
function extract(startToken, endToken) {
  const start = source.indexOf(startToken);
  const end = source.indexOf(endToken, start);
  assert(start >= 0 && end > start, "Cannot find app.js code: " + startToken);
  return source.slice(start, end);
}

const state = {
  nodes: [
    {id: 1, parent_id: null, title: "Research", node_type: "root", sort_order: 0, icon: "folder", tags: []},
    {id: 2, parent_id: 1, title: "Papers", node_type: "group", sort_order: 0, icon: "folder", tags: []},
    {id: 3, parent_id: 2, title: "Paper.pdf", node_type: "leaf", sort_order: 0, icon: "folder",
      folder_path: "C:/paper.pdf", resource_kind: "folder", tags: ["methods"]},
  ],
  view: "all",
  search: "paper",
  searchKeyboardIndex: -1,
  renderLimit: 100,
  layout: "grid",
  selectMode: false,
  openingIds: new Set(),
  selectedIds: new Set(),
};
const results = Array.from({length: 120}, (_, i) => ({id: i + 100, title: "Result " + i}));
const cards = new Map();
let cardBuilds = 0;
let renders = 0;
let historyUpdates = 0;
let scrolls = 0;
let flushes = 0;
function makeCard(id) {
  const classes = new Set();
  return {
    classes,
    classList: {
      add: k => classes.add(k),
      remove: k => classes.delete(k),
      contains: k => classes.has(k),
    },
    scrollIntoView(options) {
      assert.equal(options.block, "nearest");
      scrolls++;
    },
  };
}
function fillCards() {
  cards.clear();
  for (let i = 0; i < Math.min(results.length, state.renderLimit); i++) {
    const c = makeCard(results[i].id);
    if (i === state.searchKeyboardIndex) c.classList.add("keyboard-active");
    cards.set(results[i].id, c);
    cardBuilds++;
  }
}
fillCards();
const sandbox = {
  state,
  document: {getElementById: id => cards.get(Number(id.replace("folderhub-entry-", ""))) || null},
  render() {renders++; fillCards();},
  rememberNavigation() {historyUpdates++;},
  h: String,
  highlightSearch: String,
  TYPE_LABEL: {root: "root", group: "group", leaf: "leaf"},
  iconFor: () => "folder",
  coverUrl: () => "/image",
  // Verify that cards use the indexed lineage rather than recomputing it.
  ancestors() { throw new Error("card() must not rebuild ancestor chains"); },
};
const indexFunctions = extract("let nodeById = new Map();", "\nfunction toast(");
const cardFunction = extract("function card(n,", "\nfunction emptyView()");
const keyboardFunction = extract("function highlightSearchKeyboard(results,nextIndex){", "\nfunction searchAll(term){");
const script = indexFunctions + "\n" + cardFunction + "\n" +
  "let searchRenderFrame=null;\n" +
  "function flushSearchRender(){flushes++;searchRenderFrame=null;render(true);rememberNavigation();}\n" +
  keyboardFunction + "\nthis.testUI={rebuildNodeIndex,card,highlightSearchKeyboard," +
  "schedule:()=>{searchRenderFrame=17;},lineage:()=>lineageById};";
sandbox.flushes = flushes;
// Use a closure attached to sandbox to observe pending frame flushes.
const scriptWithCounter = script.replace(
  "function flushSearchRender(){flushes++;",
  "function flushSearchRender(){globalCounters.flushes++;"
);
sandbox.globalCounters = {flushes: 0};
vm.runInNewContext(scriptWithCounter, sandbox, {timeout: 3000});
const ui = sandbox.testUI;

ui.rebuildNodeIndex();
assert.equal(ui.lineage().get(3), "Research /Papers /Paper.pdf");
const cardMarkup = ui.card(state.nodes[2]);
assert.match(cardMarkup, /Research \/Papers \/Paper.pdf/);

for (let i = 0; i < 400; i++) {
  const index = i % 100;
  ui.highlightSearchKeyboard(results, index);
  assert.equal(cards.get(results[index].id).classList.contains("keyboard-active"), true);
  if (i > 0) {
    const previous = (i - 1) % 100;
    assert.equal(cards.get(results[previous].id).classList.contains("keyboard-active"), false);
  }
}
assert.equal(renders, 0, "arrow keys must never rebuild cards");
assert.equal(cardBuilds, 100, "initial 100 cards retain DOM identities");
assert.equal(scrolls, 400);
assert.equal(historyUpdates, 400);

// Typing may have a pending full-search render. It must flush just once.
ui.schedule();
ui.highlightSearchKeyboard(results, 1);
assert.equal(sandbox.globalCounters.flushes, 1);
assert.equal(renders, 1);
assert.equal(cards.get(101).classList.contains("keyboard-active"), true);
assert.equal(cards.get(100).classList.contains("keyboard-active"), false);

// If a card was removed by a concurrent update, use the safe render fallback.
cards.delete(102);
ui.highlightSearchKeyboard(results, 2);
assert.equal(renders, 2);
assert.equal(cards.get(102).classList.contains("keyboard-active"), true);

// A server refresh must invalidate cached parent-chain strings too.
state.nodes[1] = {...state.nodes[1], title: "Updated papers"};
ui.rebuildNodeIndex();
assert.equal(ui.lineage().get(3), "Research /Updated papers /Paper.pdf");
assert.match(ui.card(state.nodes[2]), /Research \/Updated papers \/Paper.pdf/);
console.log("Search card lifecycle: 120 results, 400 keyboard moves, pending frame, fallback and indexed lineage passed");
