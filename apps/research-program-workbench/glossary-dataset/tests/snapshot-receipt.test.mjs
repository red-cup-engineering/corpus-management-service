import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { appendFileSync, cpSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { test } from "node:test";
import { gunzipSync } from "node:zlib";
import { createSnapshotReceipt, observeWorkbench, sha256 } from "../src/snapshot-receipt.mjs";

const datasetPath = "build/dataset.nq";
const nquads = "<urn:x> <urn:y> <urn:z> <urn:g> .\n";
const source = { revision:"a".repeat(40), tree:"b".repeat(40), inputs:[["data/ontology.ttl","c".repeat(40)]] };
const coverage = { revision:source.revision, tree:source.tree, audience:"authenticated", projectedDocuments:1 };
const report = { ok:true, checks:[{id:"dataset.ask",ok:true},{id:"dataset.shacl",ok:true}],
  inputs:{files:[{path:datasetPath,sha256:sha256(nquads)}]} };
const args = {datasetPath,nquads,source,contentTree:"d".repeat(40),coverage,report,providers:{}};

test("receipt binds the admitted graph to exact source, canonical GNU gzip and both digests",()=>{
  const paired = createSnapshotReceipt(args);
  assert.deepEqual(paired,createSnapshotReceipt(args));
  const expected = execFileSync("gzip",["-n","-9","-c"],{input:nquads});
  assert.deepEqual(paired.compressed,expected);
  assert.equal(gunzipSync(paired.compressed).toString("utf8"),nquads);
  assert.deepEqual(paired.manifest.artifact,{
    path:"data/records/dataset.nq.gz",mediaType:"application/n-quads",contentEncoding:"gzip",
    quads:1,sha256:sha256(nquads),compressedSha256:sha256(expected),
  });
  assert.deepEqual(paired.manifest.source,{
    commit:source.revision,contentTree:args.contentTree,inputs:Object.fromEntries(source.inputs),
  });
  assert.deepEqual(paired.manifest.coverage,{audience:"authenticated",projectedDocuments:1});
});

test("a stale conformance digest or coverage from another revision cannot become a receipt",()=>{
  assert.throws(()=>createSnapshotReceipt({...args,nquads:nquads+nquads}),/did not independently receive/);
  assert.throws(()=>createSnapshotReceipt({...args,coverage:{...coverage,revision:"e".repeat(40)}}),/different source tree/);
});

test("two identical package manifests do not conceal a different projector implementation", async (t) => {
  const temporary = mkdtempSync(join(tmpdir(), "glossary-producer-"));
  t.after(() => rmSync(temporary, { recursive: true, force: true }));
  cpSync(new URL("../package.json", import.meta.url), join(temporary, "package.json"));
  cpSync(new URL("../src/", import.meta.url), join(temporary, "src"), { recursive: true });
  const nativeCopy = await import(pathToFileURL(join(temporary, "src/snapshot-receipt.mjs")).href);
  const original = observeWorkbench();
  assert.deepEqual(nativeCopy.observeWorkbench(), original);
  assert.ok(original.modules["src/read-reviewed-turtle.py"]);
  const name = "src/project-glossary-dataset.mjs";
  appendFileSync(join(temporary, name), "\n// Distinct projector fixture.\n");
  const measured = nativeCopy.observeWorkbench();
  assert.equal(measured.manifestSha256, original.manifestSha256);
  assert.equal(measured.version, original.version);
  assert.notEqual(measured.modules[name], original.modules[name]);
  assert.deepEqual({ ...measured.modules, [name]: original.modules[name] }, original.modules);
});
