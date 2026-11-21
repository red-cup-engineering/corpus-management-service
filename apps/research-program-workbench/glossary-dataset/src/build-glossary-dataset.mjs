import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, realpathSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { basename, dirname, isAbsolute, relative, resolve, join } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { admitProfile, projectGlossaryDataset, safePath } from "./project-glossary-dataset.mjs";
import { openPinnedGitSource } from "./git-source.mjs";
import { createSnapshotReceipt, observeNodeProviders } from "./snapshot-receipt.mjs";

const decoder = new TextDecoder("utf-8", {fatal:true,ignoreBOM:true});
const json = (bytes)=>JSON.parse(decoder.decode(bytes));
function runJson(python, args) {
  const process = spawnSync(python, ["-B", ...args], {encoding:"utf8",timeout:120_000,maxBuffer:16*1024*1024});
  if (process.error || process.status !== 0) throw new Error(`required native stage failed: ${args[0]} (${process.status ?? process.error?.name})\n${(process.stderr ?? "").slice(-2000)}`);
  return JSON.parse(process.stdout);
}
function safeRelative(path) {
  if (!safePath(path)) throw new TypeError(`invalid relative source/output path: ${path}`);
  return path;
}
function write(root, relativePath, bytes) {
  const path = join(root, safeRelative(relativePath));
  mkdirSync(dirname(path), {recursive:true,mode:0o700});
  writeFileSync(path, bytes, {flag:"wx",mode:0o600});
}
function writeJson(root, path, value) {
  write(root,path,JSON.stringify(value,null,2)+"\n");
}

export async function buildGlossaryDataset({repository,revision,profile:profilePath,output,audience,python = "python3"}) {
  if (audience !== "authenticated" || ![repository,revision,profilePath,output].every(v=>typeof v==="string" && v.length)) throw new TypeError("an authenticated audience, native Git repository, exact revision, Science profile path and private output are required");
  const repositoryRoot = realpathSync(repository);
  const outputParent = realpathSync(dirname(resolve(output)));
  const destination = join(outputParent, basename(resolve(output)));
  const relativeToSource = relative(repositoryRoot,destination);
  if (!relativeToSource || !isAbsolute(relativeToSource) && relativeToSource !== ".." && !relativeToSource.startsWith("../")) throw new Error("private output must be outside the source repository");
  if (existsSync(destination)) throw new Error("private output already exists");
  const providers = observeNodeProviders();
  const source = openPinnedGitSource(repositoryRoot,revision);
  const sourceProfile = source.read(safeRelative(profilePath));
  const profile = admitProfile(json(sourceProfile.bytes));
  const content = source.readTree(profile.contentRoot);
  const entries = source.list(profile.contentRoot);
  const glossary = entries.filter(e=>e.path.startsWith(profile.glossaryRoot+"/") && e.path.endsWith(".md"));
  if (glossary.some(e=>!e.regular)) throw new Error("glossary contains a tracked nonregular Markdown source");
  const documents = source.receive(glossary);
  const contentPaths = entries.filter(e=>e.regular).map(e=>e.path);
  const staging = mkdtempSync(join(outputParent,".glossary-pending-"));
  try {
    const work = join(staging,"source");
    mkdirSync(work,{mode:0o700});
    for (const doc of documents) write(work,doc.path,doc.bytes);
    const config = source.read("research.toml");
    const ontology = source.read(profile.reviewedVocabulary);
    const authoredProfile = source.read(profile.authoredRelations);
    const conformance = source.read(profile.datasetConformance);
    const inputBlobs = [sourceProfile,config,ontology,authoredProfile,conformance];
    for (const entry of [config,ontology,authoredProfile,conformance]) write(work,entry.path,entry.bytes);
    const acceptance = json(conformance.bytes);
    if (acceptance.formatVersion !== 1 || !Array.isArray(acceptance.dataset?.shapes) || !acceptance.dataset.shapes.length || !Array.isArray(acceptance.dataset?.ask) || !acceptance.dataset.ask.length) throw new Error("Science dataset acceptance must select both SHACL shapes and named-graph ASK queries");
    const datasetPath = safeRelative(acceptance.dataset.file);
    if (!datasetPath.endsWith(".nq")) throw new Error("Science dataset output must be an N-Quads path");
    const checks = new Set([...acceptance.dataset.shapes,...acceptance.dataset.ask.map(a=>a.query)]);
    for (const file of checks) {
      const entry = source.read(safeRelative(file));
      inputBlobs.push(entry);
      write(work,entry.path,entry.bytes);
    }
    const authored = runJson(python,["-m","research_corpus.vocabulary","--root",work,"--authored-relations",profile.authoredRelations,"--audience",audience]);
    const reviewed = runJson(python,[fileURLToPath(new URL("./read-reviewed-turtle.py",import.meta.url)),join(work,ontology.path),profile.namespace+"graph:reviewed-vocabulary"]);
    const result = await projectGlossaryDataset({profile,revision,tree:source.tree,documents,contentPaths,reviewed,authored,audience});
    write(work,datasetPath,result.nquads);
    const report = runJson(python,["-m","rdf_vocabulary_conformance","--root",work,"--config",profile.datasetConformance]);
    const provenance = {repository:profile.repository,revision,tree:source.tree,
      glossaryBlobs:result.glossaryBlobs,inputs:inputBlobs.map(({path,oid})=>[path,oid])};
    const receipt = createSnapshotReceipt({datasetPath,nquads:result.nquads,source:provenance,
      contentTree:content.oid,coverage:result.coverage,report,
      providers:{...providers,...reviewed.runtime,rdfConformance:{...reviewed.runtime.rdfConformance,version:report.version}}});
    const digest = receipt.manifest.artifact.sha256;
    const delivered = join(staging,"deliverable");
    mkdirSync(delivered,{mode:0o700});
    write(delivered,datasetPath,result.nquads);
    writeJson(delivered,"coverage.json",result.coverage);
    writeJson(delivered,"acceptance.json",report);
    writeJson(delivered,"source.json",{...provenance,sha256:digest});
    write(delivered,receipt.manifest.artifact.path,receipt.compressed);
    writeJson(delivered,receipt.manifestPath,receipt.manifest);
    if (existsSync(destination)) throw new Error("private output already exists");
    renameSync(delivered,destination);
    return { destination, sha256:digest, coverage: result.coverage };
  } finally {
    rmSync(staging,{recursive:true,force:true});
  }
}

if (process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  try {
    const { values } = parseArgs({options:{repository:{type:"string"},revision:{type:"string"},profile:{type:"string"},output:{type:"string"},audience:{type:"string"},python:{type:"string"}}});
    console.log(JSON.stringify(await buildGlossaryDataset(values)));
  } catch (error) {
    console.error(error.message);
    process.exitCode=1;
  }
}
