// Optional dependency-free Node regression for real asynchronous UI behavior.
// The Python unittest wrapper skips this test when Node.js is unavailable.
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const js = fs.readFileSync(path.join(__dirname, "..", "static", "app.js"), "utf8");
const from = js.indexOf("let everythingItems=[];");
const to = js.indexOf("function chooseEverythingResult(index)", from);
assert(from >= 0 && to > from, "Everything lifecycle functions were not found");
const fragment = js.slice(from, to);
const requests = [];
const elements = new Map();
function $(name) {
  if (!elements.has(name)) {
    const classes = new Set(["hidden"]);
    elements.set(name, {
      value: "", textContent: "", innerHTML: "", disabled: false, attributes: {},
      classList: {
        add: key => classes.add(key),
        remove: key => classes.delete(key),
        contains: key => classes.has(key),
      },
      replaceChildren() { this.innerHTML = ""; },
      setAttribute(key, value) { this.attributes[key] = value; },
    });
  }
  return elements.get(name);
}
const sandbox = {
  $, AbortController, encodeURIComponent,
  h: String,
  toast() {},
  api(url, options) {
    return new Promise((resolve, reject) => {
      requests.push({url, options, resolve, reject});
    });
  },
};
vm.runInNewContext(fragment + "\nthis.everythingTest = {" +
  "runEverythingSearch, resetEverythingSearch, closeEverything, " +
  "items: () => everythingItems};", sandbox, {timeout: 1500});
const ui = sandbox.everythingTest;
const submitEvent = {preventDefault() {}};

async function main() {
  ui.resetEverythingSearch();
  $("#everythingLayer").classList.remove("hidden");
  $("#everythingQuery").value = "old";
  const oldSearch = ui.runEverythingSearch(submitEvent);
  assert.equal(requests.length, 1);
  await ui.runEverythingSearch(submitEvent);
  assert.equal(requests.length, 1, "same pending query should be deduplicated");

  $("#everythingQuery").value = "new";
  ui.resetEverythingSearch("search changed");
  assert.equal(requests[0].options.signal.aborted, true);
  const newSearch = ui.runEverythingSearch(submitEvent);
  assert.equal(requests.length, 2);
  assert.equal($("#everythingResults").attributes["aria-busy"], "true");

  requests[1].resolve({items: [{name: "new.pdf", path: "C:/new.pdf", supported: true}]});
  await newSearch;
  assert.match($("#everythingResults").innerHTML, /new.pdf/);
  requests[0].resolve({items: [{name: "old.pdf", path: "C:/old.pdf", supported: true}]});
  await oldSearch;
  assert.doesNotMatch($("#everythingResults").innerHTML, /old.pdf/,
    "late results must never overwrite latest search");
  assert.equal(ui.items().length, 1);

  $("#everythingQuery").value = "pending";
  const pendingSearch = ui.runEverythingSearch(submitEvent);
  ui.closeEverything();
  assert.equal(requests[2].options.signal.aborted, true);
  requests[2].resolve({items: [{name: "stale.pdf", path: "C:/stale.pdf"}]});
  await pendingSearch;
  assert.equal($("#everythingResults").innerHTML, "");
  assert.equal(ui.items().length, 0);
  assert.equal($("#everythingSubmit").disabled, false);
  assert.equal($("#everythingResults").attributes["aria-busy"], "false");

  $("#everythingLayer").classList.remove("hidden");
  ui.resetEverythingSearch();
  $("#everythingQuery").value = "failure";
  const failingSearch = ui.runEverythingSearch(submitEvent);
  requests[3].reject(new Error("mock ES unavailable"));
  await failingSearch;
  assert.match($("#everythingStatus").textContent, /mock ES unavailable/);
  assert.equal($("#everythingSubmit").disabled, false);
  assert.equal($("#everythingResults").attributes["aria-busy"], "false");
  console.log("Everything UI lifecycle: 4 request paths passed");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
