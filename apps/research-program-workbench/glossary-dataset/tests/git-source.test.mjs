import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { registerHooks } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";

test("the public pinned source reader receives the exact Git catalog without graph providers", async (t) => {
  // Keep this boundary test effective even when the full projector is installed.
  const graphProviders = [
    "@red-cup-engineering/markdown-engineering-services-section",
    "@red-cup-engineering/term-engineering-services-section",
    "@red-cup-engineering/computer-triplet-serialized-content-engineering-services-section",
  ];
  const hook = registerHooks({resolve(specifier, context, next) {
    assert.ok(!graphProviders.some(name => specifier === name || specifier.startsWith(name + "/")),
      `catalog must not load a graph provider: ${specifier}`);
    return next(specifier, context);
  }});
  t.after(() => hook.deregister());
  const { readPinnedGlossarySource } = await import("@red-cup-engineering/research-glossary-dataset/git-source");

  const repository = mkdtempSync(join(tmpdir(), "glossary-git-source-"));
  t.after(() => rmSync(repository, {recursive:true,force:true}));
  function write(path, text) {
    const target = join(repository, path);
    mkdirSync(dirname(target), {recursive:true});
    writeFileSync(target, text);
  }
  const git = (args) => execFileSync("git", ["-C", repository, ...args],
    {stdio:["ignore","pipe","pipe"],encoding:"utf8"}).trim();
  git(["init","--object-format=sha1"]);
  const profilePath = "data/build.json";
  const profile = {
    formatVersion:1,repository:"fixture/source",namespace:"urn:fixture:glossary:",
    contentRoot:"content",glossaryRoot:"content/text/glossary",
    reviewedVocabulary:"data/reviewed.ttl",authoredRelations:"data/relations.json",datasetConformance:"data/check.json",
  };
  const termPath = "content/text/glossary/terms/one.md", otherPath = "content/text/notes/elsewhere.md";
  const stored = "# One\n\nOriginal prose.\n";
  write(profilePath, JSON.stringify(profile));
  write("data/invalid.json", JSON.stringify({...profile,glossaryRoot:"content/text/notes"}));
  write(termPath, stored);
  write(otherPath, "# Elsewhere\n");
  git(["add","--","."]);
  git(["-c","user.name=Fixture","-c","user.email=fixture@invalid.example","-c","commit.gpgsign=false","commit","-m","Fixture"]);
  const revision = git(["rev-parse","HEAD"]);
  write(termPath, "Not part of the pinned commit.\n");

  const received = readPinnedGlossarySource({repository,revision,profilePath});
  assert.deepEqual(received.profile, profile);
  assert.equal(received.sourceProfile.oid, git(["rev-parse",`${revision}:${profilePath}`]));
  assert.deepEqual(received.content,{path:"content",oid:git(["rev-parse",`${revision}:content`])});
  assert.deepEqual(received.contentPaths,[termPath,otherPath]);
  assert.deepEqual(received.documents, [{
    mode:"100644",type:"blob",oid:git(["rev-parse",`${revision}:${termPath}`]),
    path:termPath,regular:true,bytes:Buffer.from(stored),
  }]);
  assert.throws(() => readPinnedGlossarySource({repository,revision:"HEAD",profilePath}), /full SHA-1 commit/u);
  assert.throws(() => readPinnedGlossarySource({repository,revision,profilePath:"data/missing.json"}), /does not exist/u);
  assert.throws(() => readPinnedGlossarySource({repository,revision,profilePath:"data/invalid.json"}), /invalid Science glossary dataset profile/u);
});
