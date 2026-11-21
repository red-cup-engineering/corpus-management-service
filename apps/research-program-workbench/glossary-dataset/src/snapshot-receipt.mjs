import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, realpathSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { gunzipSync } from "node:zlib";

const manifestPath = new URL("../package.json", import.meta.url);
const workbenchModules = [
  "build-glossary-dataset.mjs",
  "git-source.mjs",
  "project-glossary-dataset.mjs",
  "read-reviewed-turtle.py",
  "snapshot-receipt.mjs",
];
const providerExports = {
  gitEngine: ["@red-cup-engineering/git-engine", ["git-object-id", "git-command-codec", "pinned-source-files", "source-path-proof"]],
  markdown: ["@red-cup-engineering/markdown-engineering-services-section", ["read-markdown-frontmatter", "read-markdown-structure", "read-markdown-features", "derive-markdown-vault-graph", "resolve-markdown-link-target"]],
  term: ["@red-cup-engineering/term-engineering-services-section", ["glossary-index", "glossary-skos", "term-carrier"]],
  tripletSerialization: ["@red-cup-engineering/computer-triplet-serialized-content-engineering-services-section", ["rdf-named-graph", "rdf-terms", "n-quads", "rdf-canonicalization"]],
};

export const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");

function providerRoot(filename, name) {
  for (let dir = dirname(filename); dirname(dir) !== dir; dir = dirname(dir)) {
    const path = join(dir, "package.json");
    if (!existsSync(path)) continue;
    const bytes = readFileSync(path);
    const record = JSON.parse(bytes);
    if (record.name === name) return { dir, version: record.version, manifestSha256: sha256(bytes) };
  }
  throw new Error(`could not observe the package manifest for ${name}`);
}

function measureWorkbench(bytes) {
  const { name, version } = JSON.parse(bytes);
  const modules = Object.fromEntries(workbenchModules.map((path) =>
    ["src/" + path, sha256(readFileSync(new URL(path, import.meta.url)))]));
  return { name, version, manifestSha256: sha256(bytes), modules };
}

/** Measure the owning application, including the Python helper it invokes. */
export function observeWorkbench() {
  return measureWorkbench(readFileSync(manifestPath));
}

/** Observe the actual provider exports, not manually supplied package commit claims. */
export function observeNodeProviders() {
  const bytes = readFileSync(manifestPath);
  const workbench = measureWorkbench(bytes);
  const { dependencies } = JSON.parse(bytes);
  return { workbench, ...Object.fromEntries(Object.entries(providerExports).map(([key, [name, names]]) => {
    let selected;
    const modules = Object.fromEntries(names.map((subpath) => {
      const file = realpathSync(fileURLToPath(import.meta.resolve(name + "/" + subpath)));
      const pkg = providerRoot(file, name);
      if (pkg.version !== dependencies[name] || selected && pkg.dir !== selected.dir)
        throw new Error(`loaded provider does not match the declared package: ${name}`);
      selected = pkg;
      return [subpath, sha256(readFileSync(file))];
    }));
    return [key, { name, version:selected.version, manifestSha256:selected.manifestSha256, modules }];
  })) };
}

function compressSnapshot(raw) {
  const env = { ...process.env, LC_ALL: "C" };
  delete env.GZIP;
  const options = { env, timeout:30_000, maxBuffer:16*1024*1024, stdio:["pipe","pipe","pipe"] };
  const version = execFileSync("gzip", ["--version"], options).toString("utf8").split("\n")[0];
  if (!/^gzip \d+(?:\.\d+)+$/u.test(version)) throw new Error("GNU gzip version was not observed");
  const compressed = execFileSync("gzip", ["-n","-9","-c"], { ...options, input:raw });
  if (compressed[3] !== 0 || compressed.readUInt32LE(4) !== 0 || !gunzipSync(compressed).equals(raw))
    throw new Error("snapshot gzip did not receive the exact graph bytes with a deterministic header");
  return { compressed, encoder:version };
}

/** Materialize the tracked artifact pair after independent conformance admitted the raw graph. */
export function createSnapshotReceipt({ datasetPath, nquads, source, contentTree, coverage, report, providers }) {
  const raw = Buffer.from(nquads, "utf8"), digest = sha256(raw);
  if (!nquads.endsWith("\n") || report.ok !== true
      || !report.checks?.some(c=>c.id==="dataset.ask" && c.ok===true)
      || !report.checks?.some(c=>c.id==="dataset.shacl" && c.ok===true)
      || !report.inputs?.files?.some(f=>f.path===datasetPath && f.sha256===digest))
    throw new Error("dataset conformance did not independently receive the written graph");
  const stem = basename(datasetPath, ".nq");
  if (!/^[a-z0-9][a-z0-9._-]*$/u.test(stem)) throw new Error("unsupported tracked snapshot basename");
  const prefix = "data/records/" + stem;
  const { compressed, encoder } = compressSnapshot(raw);
  const { revision, tree, ...counts } = coverage;
  if (revision !== source.revision || tree !== source.tree) throw new Error("coverage refers to a different source tree");
  const artifact = {
    path:prefix+".nq.gz", mediaType:"application/n-quads", contentEncoding:"gzip",
    sha256:digest, compressedSha256:sha256(compressed),
    quads:nquads.split("\n").length-1,
  };
  const manifest = {
    formatVersion:1, artifact,
    source:{commit:source.revision, contentTree, inputs:Object.fromEntries(source.inputs)},
    coverage:counts, projectionProviders:providers,
    conformance:report, compression:{encoder, arguments:["-n","-9","-c"]},
  };
  return { compressed, manifest, manifestPath:prefix+".manifest.json" };
}
