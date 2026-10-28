// Dependency-free regression against the actual FolderHub navigation functions.
// This is an optional Node.js test; the application does not require Node.
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "static", "app.js"), "utf8");
function fragment(from, to) {
  const start = source.indexOf(from);
  const end = source.indexOf(to, start);
  assert(start >= 0 && end > start, "Missing navigation implementation: " + from);
  return source.slice(start, end);
}
const implementation = [
  fragment("let nodeById = new Map();", "// Cache each ancestor chain once"),
  fragment("function rebuildNodeIndex(){", "\nfunction toast("),
  fragment("function expandLineage(id){", "\nasync function refresh()"),
  fragment("function toggleBranch(id){", "\nfunction renderSavedViews()"),
].join("\n");

let htmlAssignments = 0;
let treeFocusCount = 0;
let savedStateCount = 0;
let otherSidebarRefreshes = 0;
class MockTree {
  constructor() { this.rows = new Map(); this.toggles = new Map(); this.html = ""; }
  set innerHTML(value) {
    this.html = value;
    htmlAssignments++;
    this.rows = new Map();
    this.toggles = new Map();
    for (const match of value.matchAll(/data-node="(\d+)"/g)) {
      const id = Number(match[1]);
      const row = {
        active: false,
        classList: {
          add: cls => { if (cls === "active") row.active = true; },
          remove: cls => { if (cls === "active") row.active = false; },
        },
      };
      this.rows.set(id, {closest: () => row, row});
    }
    for (const match of value.matchAll(/data-toggle="(\d+)"/g)) {
      this.toggles.set(Number(match[1]), {
        focus: () => {treeFocusCount++;},
      });
    }
  }
  get innerHTML() { return this.html; }
  querySelector(selector) {
    if (selector === ".tree-row.active") {
      for (const entry of this.rows.values()) {
        if (entry.row.active) return entry.row;
      }
      return null;
    }
    let m = selector.match(/^\[data-node="(\d+)"\]$/);
    if (m) return this.rows.get(Number(m[1])) || null;
    m = selector.match(/^\[data-toggle="(\d+)"\]$/);
    if (m) return this.toggles.get(Number(m[1])) || null;
    throw Error("Unexpected selector: " + selector);
  }
}
const tree = new MockTree();
const elements = {
  "#treeNav": tree,
  "#rootCount": {textContent: ""},
  "#tagCount": {textContent: ""},
};
const $ = selector => {
  assert(Object.hasOwn(elements, selector), "Unexpected UI element: " + selector);
  return elements[selector];
};
// Include many visible children to catch accidental O(tree size) remounts.
const extraLeaves = Array.from({length: 1200}, (_, i) => ({
  id: i + 100, parent_id: 1, sort_order: i + 1, node_type: "leaf",
  title: "Document " + i, icon: "folder", tags: [],
}));
const state = {
  nodes: [
    {id: 1, parent_id: null, sort_order: 0, node_type: "root",
      title: "Projects", icon: "folder", tags: ["research"]},
    {id: 2, parent_id: null, sort_order: 1, node_type: "root",
      title: "Articles", icon: "folder", tags: []},
    {id: 3, parent_id: 1, sort_order: 0, node_type: "leaf",
      title: "Paper.pdf", icon: "folder", tags: ["research"]},
    ...extraLeaves,
  ],
  expanded: new Set([1]),
  view: "node",
  selected: 1,
};
const sandbox = {
  state, $, h: String, iconFor: node => node.icon,
  TYPE_LABEL: {root: "root", group: "group", leaf: "leaf"},
  buildSearchRecords: () => [],
  saveTreeState() {savedStateCount++;},
  ancestors(id) {
    const chain = [];
    const visited = new Set();
    let current = state.nodes.find(n => n.id === id);
    while (current && !visited.has(current.id)) {
      visited.add(current.id);
      chain.unshift(current);
      current = state.nodes.find(n => n.id === current.parent_id);
    }
    return chain;
  },
  renderSavedViews() {otherSidebarRefreshes++;},
  renderFolderGroups() {otherSidebarRefreshes++;},
  renderWorkspaces() {otherSidebarRefreshes++;},
  document: {
    querySelectorAll() {
      return [{dataset: {view: "all"}, classList: {toggle() {}}}];
    },
  },
};
vm.runInNewContext(implementation +
  "\nthis.navigationTest = {rebuildNodeIndex, expandLineage, toggleBranch, renderNav};",
  sandbox, {timeout: 2000});
const nav = sandbox.navigationTest;
const active = id => Boolean(tree.rows.get(id)?.row.active);

nav.rebuildNodeIndex();
nav.renderNav();
assert.equal(htmlAssignments, 1);
assert.equal(active(1), true);
assert.equal(active(3), false);
assert.equal(elements["#rootCount"].textContent, 2);
assert.equal(elements["#tagCount"].textContent, 1);
assert.equal(tree.html.includes('aria-expanded="true"'), true);
const firstRootRow = tree.rows.get(1).row;

// Switching selection changes only active markers, preserving the same DOM rows.
state.selected = 3;
nav.renderNav();
assert.equal(htmlAssignments, 1, "selection must not remount the tree");
assert.equal(tree.rows.get(1).row, firstRootRow, "existing rows keep their identity");
assert.equal(active(1), false);
assert.equal(active(3), true);

state.view = "all";
nav.renderNav();
assert.equal(htmlAssignments, 1);
assert.equal(active(3), false);
state.view = "node";
state.selected = 3;

// Collapse makes children disappear and restores focus to the toggle.
nav.toggleBranch(1);
assert.equal(htmlAssignments, 2);
assert.equal(tree.rows.has(3), false);
assert.equal(treeFocusCount, 1);

// Navigating into a hidden descendant expands the lineage just once.
const savedBefore = savedStateCount;
nav.expandLineage(3);
nav.renderNav();
assert.equal(htmlAssignments, 3);
assert.equal(tree.rows.has(3), true);
assert.equal(active(3), true);
assert.equal(savedStateCount, savedBefore + 1);
nav.expandLineage(3);
nav.renderNav();
assert.equal(htmlAssignments, 3);
assert.equal(savedStateCount, savedBefore + 1,
  "already-expanded lineage must not trigger another persistence");

// A true server data refresh invalidates cached markup, even without new view.
state.nodes[0] = {...state.nodes[0], title: "Renamed projects",
  tags: ["research", "research-new"]};
nav.rebuildNodeIndex();
nav.renderNav();
assert.equal(htmlAssignments, 4);
assert.match(tree.html, /Renamed projects/);
assert.equal(elements["#tagCount"].textContent, 2,
  "tag index must refresh when server data changes");

// Many ordinary view changes avoid recreating the large sidebar tree.
for (let i = 0; i < 400; i++) {
  state.selected = i % 2 === 0 ? 1 : 2;
  nav.renderNav();
}
assert.equal(htmlAssignments, 4);
assert.equal(otherSidebarRefreshes, 3 * (1 + 1 + 1 + 1 + 1 + 1 + 1 + 400));
console.log("Sidebar tree lifecycle: 1200 extra nodes, selection, collapse/focus, lineage, refresh and 400 view changes passed");
