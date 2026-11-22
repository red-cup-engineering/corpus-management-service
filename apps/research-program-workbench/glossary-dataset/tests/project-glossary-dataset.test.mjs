import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { gunzipSync } from "node:zlib";
import { sha256 } from "../src/snapshot-receipt.mjs";
import { buildGlossaryDataset } from "../src/build-glossary-dataset.mjs";
import { openPinnedGitSource } from "../src/git-source.mjs";
import { replayGlossaryNavigation } from "../src/replay-glossary-navigation.mjs";
import { admitProfile, projectGlossaryDataset } from "../src/project-glossary-dataset.mjs";

const namespace = "urn:fixture:glossary:";
const namespaceGraph = namespace + "graph:";
const vocabulary = namespace + "glossary-vocabulary:";
const concept = namespace + "concept:";
const rootUrl = "https://github.com/fixture/source/blob/main/";
const first = "content/text/glossary/terms/first.md", second = "content/text/glossary/terms/second.md";
const child = "content/text/glossary/terms/held.md";
const profilePath = "data/build.json";
const profile = {
  formatVersion:1,repository:"fixture/source",namespace,contentRoot:"content",glossaryRoot:"content/text/glossary",
  reviewedVocabulary:"data/reviewed.ttl",authoredRelations:"data/relations.json",datasetConformance:"data/check.json",
};

function fixture(t) {
  const parent=mkdtempSync(join(tmpdir(),"glossary-acceptance-"));
  t.after(()=>rmSync(parent,{recursive:true,force:true}));
  const root=join(parent,"repository");
  mkdirSync(root);
  function write(path, text) {
    const target=join(root,path);
    mkdirSync(dirname(target),{recursive:true});
    writeFileSync(target,text);
  }
  const renderVocabulary=()=>execFileSync("python3",["-B","-m","research_corpus.vocabulary","--root",root],
    {stdio:["ignore","pipe","pipe"]});
  const git=(args)=>execFileSync("git",["-C",root,...args],{stdio:["ignore","pipe","pipe"],encoding:"utf8"}).trim();
  const commit=()=>{
    git(["add","--","."]);
    git(["-c","user.name=Fixture","-c","user.email=fixture@invalid.example","-c","commit.gpgsign=false","commit","-m","Fixture"]);
    return git(["rev-parse","HEAD"]);
  };
  git(["init","--object-format=sha1"]);
  write(first,"---\nidentity: first\nname: First\ndescription: An admitted concept\nresult-concept: second\n---\n\n[See second](second.md).\n\n[Do not link held](held.md).\n");
  write(second,"---\nidentity: second\nname: Second\ndescription: An admitted result\n---\n\nAn independently defined result.\n");
  write(child,"---\nidentity: held\nname: Held\ndescription: A withheld concept\nconsent-status: withheld\n---\n\nThis carrier is outside the audience.\n");
  write("content/text/glossary/README.md","# Glossary navigation\n");
  write("research.toml",`[program]\ntitle="Fixture"\n[corpus]\nlib_dirs=["content/text/glossary/terms"]\n[vocabulary]\nscheme="${namespace}scheme"\nnamespace="${concept}"\ndocument_base_url="${rootUrl}"\noutput="data/reviewed.ttl"\nmembers=["${first}","${second}"]\n`);
  write(profilePath,JSON.stringify(profile));
  write(profile.authoredRelations,JSON.stringify({formatVersion:1,relations:{"result-concept":vocabulary+"resultConcept"}}));
  write(profile.datasetConformance,JSON.stringify({formatVersion:1,dataset:{file:"build/dataset.nq",shapes:["data/shape.ttl"],ask:[{id:"authored",query:"data/ask.rq",expect:true}]}}));
  write("data/shape.ttl",`@prefix sh: <http://www.w3.org/ns/shacl#> .\n<${namespace}shape> a sh:NodeShape ; sh:targetSubjectsOf <${vocabulary}resultConcept> ; sh:class <http://www.w3.org/2004/02/skos/core#Concept> .\n`);
  const authoredEdge=`<${concept}first> <${vocabulary}resultConcept> <${concept}second> .`;
  write("data/ask.rq",`ASK { GRAPH <${namespaceGraph}authored-assertions> { ${authoredEdge} } FILTER NOT EXISTS { GRAPH ?elsewhere { ${authoredEdge} } FILTER(?elsewhere != <${namespaceGraph}authored-assertions>) } }\n`);
  renderVocabulary();
  return {root, parent, write, commit, renderVocabulary, args:{repository:root,profile:profilePath,audience:"authenticated",output:join(parent,"accepted")}};
}

test("native navigation replay reads the exact Git cut, not a fabricated receiver observation", t=>{
  const {root,write,commit}=fixture(t);
  const revision=commit();
  write(first,"[Invented destination](forged.md)\n");
  const later=commit();
  const path=fileURLToPath(new URL("../src/replay-glossary-navigation.mjs",import.meta.url));
  const replay=(at)=>execFileSync(process.execPath,[path,"--repository",root,"--revision",at,
    "--profile",profilePath,"--audience","authenticated"],{encoding:"utf8"});
  const expected=replay(revision), afterEdit=replay(later);
  const graph=`<${namespaceGraph}navigation> .`;
  assert.ok(expected.trimEnd().split("\n").every(line=>line.endsWith(graph)));
  const original=`<${vocabulary}rawTarget> "second.md" ${graph}`;
  const falseWitness=`<${vocabulary}rawTarget> "forged.md" ${graph}`;
  assert.ok(expected.includes(original));
  assert.doesNotMatch(expected,/held\.md|forged\.md/u);
  assert.ok(afterEdit.includes(falseWitness));
  // A structurally valid replacement, with the same graph, observation IRI
  // and asserted target, must differ from native replay of the selected cut.
  const mutated=expected.replace(original,falseWitness);
  assert.equal(mutated.split("\n").length,expected.split("\n").length);
  assert.notEqual(mutated,replay(revision));
  write(first,"A valid glossary document with no navigation.\n");
  const linkless=commit();
  assert.equal(replay(linkless),"");
});

test("native immutable Git → Workbench → RDF → independent named ASK and SHACL",async t=>{
  const {root,write,commit,args}=fixture(t);
  const revision=commit();
  write(first,"worktree-only modification must not become an input");
  write(profile.reviewedVocabulary,"worktree-only stale Turtle");
  const out=await buildGlossaryDataset({...args,revision});
  const bytes=readFileSync(join(out.destination,"build/dataset.nq"),"utf8");
  const source=JSON.parse(readFileSync(join(out.destination,"source.json")));
  const received=JSON.parse(readFileSync(join(out.destination,"acceptance.json")));
  const original=openPinnedGitSource(root,revision);
  assert.equal(source.revision,revision);
  assert.equal(source.tree,original.tree);
  assert.equal(source.glossaryBlobs.find(([path])=>path===first)[1],original.read(first).oid);
  assert.equal(out.coverage.trackedGlossaryMarkdown,4);
  assert.equal(out.coverage.projectedDocuments,3);
  assert.equal(out.coverage.authoredObservations,1);
  assert.ok(bytes.includes(`<${concept}first> <${vocabulary}resultConcept> <${concept}second> <${namespaceGraph}authored-assertions>`));
  assert.ok(bytes.includes(`<${namespaceGraph}reviewed-vocabulary>`));
  const replay = await replayGlossaryNavigation({...args,revision});
  const navigation = bytes.split("\n").filter(line=>line.endsWith(` <${namespaceGraph}navigation> .`)).join("\n") + "\n";
  assert.equal(replay,navigation);
  assert.ok(bytes.includes(`<${namespaceGraph}navigation>`));
  assert.ok(bytes.includes(`<${namespaceGraph}documents>`));
  assert.doesNotMatch(bytes,/worktree-only|held\.md|outside the audience/u);
  assert.equal(received.ok,true);
  const manifestPath = "data/records/dataset.manifest.json";
  const manifestBytes = readFileSync(join(out.destination,manifestPath));
  const receipt = JSON.parse(manifestBytes);
  const gzipBytes = readFileSync(join(out.destination,receipt.artifact.path));
  assert.equal(receipt.source.commit,source.revision);
  assert.equal(receipt.source.contentTree,original.readTree(profile.contentRoot).oid);
  assert.deepEqual(receipt.source.inputs,Object.fromEntries(source.inputs));
  assert.equal(receipt.artifact.sha256,sha256(bytes));
  assert.equal(receipt.artifact.compressedSha256,sha256(gzipBytes));
  assert.equal(receipt.artifact.quads,bytes.split("\n").length-1);
  assert.equal(gunzipSync(gzipBytes).toString("utf8"),bytes);
  const ownRuntime = ["src/build-glossary-dataset.mjs", "src/git-source.mjs",
    "src/project-glossary-dataset.mjs", "src/project-glossary-navigation.mjs", "src/read-reviewed-turtle.py", "src/snapshot-receipt.mjs"];
  assert.deepEqual(receipt.projectionProviders.workbench.modules, Object.fromEntries(
    ownRuntime.map((path) => [path, sha256(readFileSync(new URL("../" + path, import.meta.url)))]),
  ));
  const applicationManifest = readFileSync(new URL("../package.json", import.meta.url));
  assert.equal(receipt.projectionProviders.workbench.manifestSha256, sha256(applicationManifest));
  const { dependencies } = JSON.parse(applicationManifest);
  const providerPackages = {
    gitEngine: "@red-cup-engineering/git-engine",
    markdown: "@red-cup-engineering/markdown-engineering-services-section",
    term: "@red-cup-engineering/term-engineering-services-section",
    tripletSerialization: "@red-cup-engineering/computer-triplet-serialized-content-engineering-services-section",
  };
  for (const [role, name] of Object.entries(providerPackages)) {
    assert.ok(Object.hasOwn(dependencies, name));
    assert.equal(receipt.projectionProviders[role].name, name);
    assert.equal(receipt.projectionProviders[role].version, dependencies[name]);
  }
  assert.match(receipt.projectionProviders.markdown.modules["derive-markdown-vault-graph"],/^[a-f0-9]{64}$/u);
  assert.equal(receipt.projectionProviders.researchCorpus.module,"research_corpus.vocabulary");
  assert.deepEqual(receipt.conformance,received);
  const second=await buildGlossaryDataset({...args,revision,output:join(dirname(out.destination),"again")});
  assert.deepEqual(readFileSync(join(second.destination,manifestPath)),manifestBytes);
  assert.deepEqual(readFileSync(join(second.destination,receipt.artifact.path)),gzipBytes);
  assert.deepEqual(received.checks.map(c=>[c.id,c.ok]).sort(),[["dataset.ask",true],["dataset.shacl",true]]);
  await assert.rejects(buildGlossaryDataset({...args,revision}),/already exists/);
});

test("refuses stale pinned reviewed Turtle even when the dirty worktree has regenerated it",async t=>{
  const {root,write,commit,renderVocabulary,args}=fixture(t);
  const turtle=join(root,profile.reviewedVocabulary);
  const previous=readFileSync(turtle);
  const original=readFileSync(join(root,first),"utf8");
  // New verified provenance changes only the reviewed Turtle, not the authored relation.
  write(first,original.replace("result-concept: second","result-concept: second\n"+
    "provenance:\n  sources: [https://example.invalid/original.md]"));
  const revision=commit();
  renderVocabulary();
  const corrected=readFileSync(turtle);
  assert.notDeepEqual(corrected,previous);
  await assert.rejects(buildGlossaryDataset({...args,revision}),{
    message:/required native stage failed: research_corpus\.vocabulary[^]*missing or stale output/,
  });
  assert.equal(existsSync(args.output),false);
  assert.deepEqual(readFileSync(turtle),corrected);

  // Inverting the dirty state exercises the real producer on fresh tracked bytes.
  const fresh=commit();
  write(profile.reviewedVocabulary,previous);
  const out=await buildGlossaryDataset({...args,revision:fresh});
  const nquads=readFileSync(join(out.destination,"build/dataset.nq"),"utf8");
  assert.ok(nquads.includes("<http://www.w3.org/ns/prov#wasDerivedFrom> <https://example.invalid/original.md>"));
  assert.deepEqual(readFileSync(turtle),previous);
});

test("a byte-identical Turtle copy at a different profile path does not satisfy the vocabulary check",async t=>{
  const {root,write,commit,args}=fixture(t);
  const other="data/not-the-configured-output.ttl";
  write(other,readFileSync(join(root,profile.reviewedVocabulary)));
  write(profilePath,JSON.stringify({...profile,reviewedVocabulary:other}));
  await assert.rejects(buildGlossaryDataset({...args,revision:commit()}),
    /vocabulary.output differs from the expected reviewed vocabulary path/);
  assert.equal(existsSync(args.output),false);
});

test("negative named graph control cannot promote a dataset",async t=>{
  const {write,commit,args}=fixture(t);
  write("data/ask.rq",`ASK { GRAPH <${namespaceGraph}navigation> { <${concept}first> <${vocabulary}resultConcept> <${concept}second> } }\n`);
  await assert.rejects(buildGlossaryDataset({...args,revision:commit()}),/required native stage failed: rdf_vocabulary_conformance/);
  assert.equal(existsSync(args.output),false);
});

test("scope, transport and audience preconditions fail closed",async t=>{
  const {commit,args,root}=fixture(t), revision=commit();
  const git=openPinnedGitSource(root,revision);
  const original=git.read(first);
  const meta={profile,revision,tree:git.tree,contentPaths:[first],audience:"authenticated"};
  await assert.rejects(projectGlossaryDataset({...meta,documents:[{...original,bytes:Buffer.from("changed")}]}),/unqualified glossary blob/);
  await assert.rejects(projectGlossaryDataset({...meta,audience:"public",documents:[original]}),/authenticated/);
  await assert.rejects(projectGlossaryDataset({...meta,contentPaths:[first,second],documents:[original]}),/inventory do not agree/);
  await assert.rejects(buildGlossaryDataset({...args,revision,output:join(root,"must-not-write")}),/outside the source/);
  assert.throws(()=>admitProfile({...profile,glossaryRoot:"../escape"}),/profile/);
});

test("do not disclose reviewed concepts whose defining documents are withheld",async t=>{
  const {root,write,commit,renderVocabulary,args}=fixture(t);
  const config=readFileSync(join(root,"research.toml"),"utf8");
  write("research.toml",config.replace(`"${second}"]`,`"${second}","${child}"]`));
  renderVocabulary();
  await assert.rejects(buildGlossaryDataset({...args,revision:commit()}),/reviewed vocabulary .* outside the selected audience/);
  assert.equal(existsSync(args.output),false);
});

test("an owner-authored list stays complete and is not downgraded by strict Term observation",async t=>{
  const {root,write,commit,renderVocabulary,args}=fixture(t);
  const third="content/text/glossary/terms/third.md";
  write(third,"---\nidentity: third\nname: Third\ndescription: Another reviewed result\n---\n");
  const original=readFileSync(join(root,first),"utf8");
  write(first,original.replace("result-concept: second","depends-on: [second, third]"));
  const originalConfig=readFileSync(join(root,"research.toml"),"utf8");
  write("research.toml",originalConfig.replace(`"${second}"]`,`"${second}","${third}"]`));
  renderVocabulary();
  const predicate="https://561.group/ns/predicate/depends-on";
  write(profile.authoredRelations,JSON.stringify({formatVersion:1,relations:{"depends-on":predicate}}));
  const edges=["second","third"].map(target=>`<${concept}first> <${predicate}> <${concept+target}> .`).join(" ");
  write("data/ask.rq",`ASK { GRAPH <${namespaceGraph}authored-assertions> { ${edges} } }`);
  const out=await buildGlossaryDataset({...args,revision:commit()});
  assert.equal(out.coverage.authoredObservations,2);
  assert.equal(out.coverage.projectedAuthoredObservations,2);
  assert.equal(out.coverage.unprojectedAuthoredObservations,0);
  const bytes=readFileSync(join(out.destination,"build/dataset.nq"),"utf8");
  assert.doesNotMatch(bytes,/"observed-unprojected"/u);
  assert.doesNotMatch(bytes,new RegExp(`<${rootUrl+first}> <${predicate}>`,"u"));
});

test("keeps repeated navigation witnesses, not a second independently mutable document edge",async t=>{
  const {root,write,commit,args}=fixture(t);
  const original=readFileSync(join(root,first),"utf8");
  write(first,original+"\n[Repeated](second.md) and [Missing](missing.md).\n");
  const out=await buildGlossaryDataset({...args,revision:commit()});
  const bytes=readFileSync(join(out.destination,"build/dataset.nq"),"utf8");
  const navigation = bytes.split("\n").filter(line=>line.endsWith(`<${namespaceGraph}navigation> .`));
  const target = `<${vocabulary}target> <${rootUrl+second}>`;
  const matches = navigation.filter(line=>line.includes(target));
  assert.equal(new Set(matches.map(line=>line.split(" ")[0])).size,2);
  const missing = navigation.find(line=>line.includes('"missing.md"')).split(" ")[0];
  assert.ok(!navigation.some(line=>line.startsWith(missing+" ")&&line.includes(`<${vocabulary}target>`)));
  assert.ok(!navigation.some(line=>line.includes("<http://purl.org/dc/terms/references>")));
  assert.equal(out.coverage.authoredObservations,1);
  assert.equal(out.coverage.projectedAuthoredObservations,1);
});
