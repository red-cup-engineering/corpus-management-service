import { execFileSync } from "node:child_process";
import { readTreeEntries } from "@red-cup-engineering/git-engine/git-command-codec";
import { readGitBlobObjectsSync } from "@red-cup-engineering/git-engine/pinned-source-files";
import { readEvidenceBoundCommit } from "@red-cup-engineering/git-engine/source-path-proof";
import { gitBlobIdOf } from "@red-cup-engineering/git-engine/git-object-id";
import { safePath } from "./project-glossary-dataset.mjs";

const oidPattern = /^[a-f0-9]{40}$/u;
const limits = {maxBytes:32*1024*1024,timeoutMs:60_000};

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
  return Object.freeze({revision,tree,list,read,receive});
}
