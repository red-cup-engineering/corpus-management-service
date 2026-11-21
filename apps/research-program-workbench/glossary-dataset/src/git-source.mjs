import { execFileSync } from "node:child_process";
import { readTreeEntries } from "@red-cup-engineering/git-engine/git-command-codec";
import { readGitBlobObjectsSync } from "@red-cup-engineering/git-engine/pinned-source-files";
import { readEvidenceBoundCommit } from "@red-cup-engineering/git-engine/source-path-proof";
import { gitBlobIdOf } from "@red-cup-engineering/git-engine/git-object-id";

const oidPattern = /^[a-f0-9]{40}$/u;
const limits = {maxBytes:32*1024*1024,timeoutMs:60_000};

export function safePath(path) {
  return typeof path === "string" && !/[\\\u0000-\u001f\u007f]/u.test(path)
    && path.split("/").every((part) => part.length && part !== "." && part !== ".." && part !== ".git");
}
export function admitProfile(profile) {
  const keys = ["formatVersion", "repository", "namespace", "contentRoot", "glossaryRoot", "reviewedVocabulary", "authoredRelations", "datasetConformance"];
  if (!profile || Object.keys(profile).sort().join() !== keys.sort().join() || profile.formatVersion !== 1
      || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/u.test(profile.repository)
      || !/^urn:[A-Za-z0-9][A-Za-z0-9-]*:[A-Za-z0-9:._-]+:$/u.test(profile.namespace)
      || [profile.contentRoot, profile.glossaryRoot, profile.reviewedVocabulary, profile.authoredRelations, profile.datasetConformance].some((p) => !safePath(p))
      || profile.glossaryRoot !== profile.contentRoot + "/text/glossary"
      || !profile.reviewedVocabulary.endsWith(".ttl")
      || !profile.authoredRelations.endsWith(".json")
      || !profile.datasetConformance.endsWith(".json")) throw new TypeError("invalid Science glossary dataset profile");
  return profile;
}

export function openPinnedGitSource(directory, revision) {
  if (typeof directory !== "string" || !oidPattern.test(revision)) throw new TypeError("a local Git repository and a full SHA-1 commit are required");
  // Git Engine owns commit verification, tree row decoding and selected blob custody.
  // Only the scoped local catalog observation is specific to this consumer.
  const environment = {GIT_OPTIONAL_LOCKS:"0",GIT_NO_LAZY_FETCH:"1",GIT_TERMINAL_PROMPT:"0"};
  function git(args) {
    return execFileSync("git", ["--no-replace-objects","--literal-pathspecs","-C",directory,...args], {
      env:{...process.env,...environment}, stdio:["ignore","pipe","pipe"],
      maxBuffer:limits.maxBytes, timeout:limits.timeoutMs,
    });
  }
  const {tree:{sha:tree}}=readEvidenceBoundCommit({sha:revision,object:git(["cat-file","commit",revision])});
  function list(scope) {
    if (!safePath(scope)) throw new TypeError("unsafe Git scope");
    return readTreeEntries(git(["ls-tree","-r","-z","--full-tree",tree,"--",scope]),100_000).map(({path,mode,type,object:oid})=>{
      if (!safePath(path) || !oidPattern.test(oid) || path !== scope && !path.startsWith(scope+"/")) throw new Error("unrecognized Git tree entry");
      return { mode,type,oid,path,regular:type==="blob" && (mode==="100644" || mode==="100755") };
    });
  }
  function receive(entries) {
    if (entries.some(e=>!e.regular)) throw new Error("selected Git sources must be regular blobs");
    const native = readGitBlobObjectsSync({directory,objects:entries.map(e=>e.oid),receiveMissing:false,...limits,environment});
    return entries.map(entry=>{
      const bytes=native.get(entry.oid);
      if (!bytes || gitBlobIdOf(bytes)!==entry.oid) throw new Error(`Git blob identity mismatch: ${entry.path}`);
      return {...entry,bytes};
    });
  }
  function read(path) {
    const [entry,...unexpected]=list(path);
    if (!entry || unexpected.length || entry.path!==path) throw new Error(`pinned Git file does not exist: ${path}`);
    return receive([entry])[0];
  }
  function readTree(path) {
    if (!safePath(path)) throw new TypeError("unsafe Git tree path");
    const [entry,...unexpected] = readTreeEntries(git(["ls-tree","-z","--full-tree",tree,"--",path]), 2);
    if (!entry || unexpected.length || entry.path!==path || entry.mode!=="040000" ||
        entry.type!=="tree" || !oidPattern.test(entry.object)) throw new Error(`pinned Git tree does not exist: ${path}`);
    return {path,oid:entry.object};
  }
  return Object.freeze({revision,tree,list,read,readTree,receive});
}

/** Read the profile, catalog, and selected Markdown from one native Git commit. */
export function readPinnedGlossarySource({repository, revision, profilePath}) {
  const source = openPinnedGitSource(repository, revision);
  const sourceProfile = source.read(profilePath);
  const text = new TextDecoder("utf-8", {fatal:true,ignoreBOM:true}).decode(sourceProfile.bytes);
  const profile = admitProfile(JSON.parse(text));
  const content = source.readTree(profile.contentRoot);
  const entries = source.list(profile.contentRoot);
  const glossary = entries.filter(e=>e.path.startsWith(profile.glossaryRoot+"/") && e.path.endsWith(".md"));
  if (glossary.some(e=>!e.regular)) throw new Error("glossary contains a tracked nonregular Markdown source");
  return {
    source, sourceProfile, profile, content,
    documents: source.receive(glossary),
    contentPaths: entries.filter(e=>e.regular).map(e=>e.path),
  };
}
