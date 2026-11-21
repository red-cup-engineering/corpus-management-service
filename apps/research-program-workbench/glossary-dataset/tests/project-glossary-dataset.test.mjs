import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { gunzipSync } from "node:zlib";
import { sha256 } from "../src/snapshot-receipt.mjs";
import { buildGlossaryDataset } from "../src/build-glossary-dataset.mjs";
import { openPinnedGitSource } from "../src/git-source.mjs";
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
  const git=(args)=>execFileSync("git",["-C",root,...args],{stdio:["ignore","pipe","pipe"],encoding:"utf8"}).trim();
  const commit=()=>{
    git(["add","--","."]);
    git(["-c","user.name=Fixture","-c","user.email=fixture@invalid.example","-c","commit.gpgsign=false","commit","-m","Fixture"]);
    return git(["rev-parse","HEAD"]);
  };
  git(["init","--object-format=sha1"]);
  write(first,"---\nidentity: first\nname: First\ndescription: An admitted concept\nresult-concept: second\n---\n\n[See second](second.md).\n\n[Do not link held](held.md).\n");
  write(second,"---\nidentity: second\nname: Second\ndescription: An admitted result\n---\n\nAn independently defined result.\n");
  write(child,"---\nidentity: held\nname: Held\nconsent-status: withheld\n---\n\nThis carrier is outside the audience.\n");
  write("content/text/glossary/README.md","# Glossary navigation\n");
  write("research.toml",`[program]\ntitle="Fixture"\n[corpus]\nlib_dirs=["content/text/glossary/terms"]\n[vocabulary]\nscheme="${namespace}scheme"\nnamespace="${concept}"\ndocument_base_url="${rootUrl}"\noutput="data/reviewed.ttl"\nmembers=["${first}","${second}"]\n`);
  write(profilePath,JSON.stringify(profile));
  write(profile.authoredRelations,JSON.stringify({formatVersion:1,relations:{"result-concept":vocabulary+"resultConcept"}}));
  write(profile.reviewedVocabulary,`@prefix skos: <http://www.w3.org/2004/02/skos/core#> .\n@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n<${concept}first> a skos:Concept ; rdfs:isDefinedBy <${rootUrl+first}> .\n<${concept}second> a skos:Concept ; rdfs:isDefinedBy <${rootUrl+second}> .\n`);
  write(profile.datasetConformance,JSON.stringify({formatVersion:1,dataset:{file:"build/dataset.nq",shapes:["data/shape.ttl"],ask:[{id:"authored",query:"data/ask.rq",expect:true}]}}));
  write("data/shape.ttl",`@prefix sh: <http://www.w3.org/ns/shacl#> .\n<${namespace}shape> a sh:NodeShape ; sh:targetSubjectsOf <${vocabulary}resultConcept> ; sh:class <http://www.w3.org/2004/02/skos/core#Concept> .\n`);
  const authoredEdge=`<${concept}first> <${vocabulary}resultConcept> <${concept}second> .`;
  write("data/ask.rq",`ASK { GRAPH <${namespaceGraph}authored-assertions> { ${authoredEdge} } FILTER NOT EXISTS { GRAPH ?elsewhere { ${authoredEdge} } FILTER(?elsewhere != <${namespaceGraph}authored-assertions>) } }\n`);
  return {root, parent, write, commit, args:{repository:root,profile:profilePath,audience:"authenticated",output:join(parent,"accepted")}};
}

test("native immutable Git → Workbench → RDF → independent named ASK and SHACL",async t=>{
  const {root,write,commit,args}=fixture(t);
  const revision=commit();
  write(first,"worktree-only modification must not become an input");
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
  assert.equal(receipt.projectionProviders.markdown.version,"0.6.0-dev.0");
  assert.match(receipt.projectionProviders.markdown.modules["derive-markdown-vault-graph"],/^[a-f0-9]{64}$/u);
  assert.equal(receipt.projectionProviders.researchCorpus.module,"research_corpus.vocabulary");
  assert.deepEqual(receipt.conformance,received);
  const second=await buildGlossaryDataset({...args,revision,output:join(dirname(out.destination),"again")});
  assert.deepEqual(readFileSync(join(second.destination,manifestPath)),manifestBytes);
  assert.deepEqual(readFileSync(join(second.destination,receipt.artifact.path)),gzipBytes);
  assert.deepEqual(received.checks.map(c=>[c.id,c.ok]).sort(),[["dataset.ask",true],["dataset.shacl",true]]);
  await assert.rejects(buildGlossaryDataset({...args,revision}),/already exists/);
});

test("negative named graph control cannot promote a dataset",async t=>{
  const {write,commit,args}=fixture(t);
  write("data/ask.rq",`ASK { GRAPH <${namespaceGraph}navigation> { <${concept}first> <${vocabulary}resultConcept> <${concept}second> } }\n`);
  await assert.rejects(buildGlossaryDataset({...args,revision:commit()}),/required native stage failed: -m/);
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
  const {write,commit,args}=fixture(t);
  write(profile.reviewedVocabulary,
    `@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<${concept}first> a skos:Concept ; rdfs:isDefinedBy <${rootUrl+first}> .
<${concept}second> a skos:Concept ; rdfs:isDefinedBy <${rootUrl+second}> .
<${concept}held> a skos:Concept ; rdfs:isDefinedBy <${rootUrl+child}> .
`);
  await assert.rejects(buildGlossaryDataset({...args,revision:commit()}),/reviewed vocabulary .* outside the selected audience/);
  assert.equal(existsSync(args.output),false);
});

test("an owner-authored list stays complete and is not downgraded by strict Term observation",async t=>{
  const {root,write,commit,args}=fixture(t);
  const third="content/text/glossary/terms/third.md";
  write(third,"---\nidentity: third\nname: Third\ndescription: Another reviewed result\n---\n");
  const original=readFileSync(join(root,first),"utf8");
  write(first,original.replace("result-concept: second","depends-on: [second, third]"));
  const originalConfig=readFileSync(join(root,"research.toml"),"utf8");
  write("research.toml",originalConfig.replace(`"${second}"]`,`"${second}","${third}"]`));
  const originalCore=readFileSync(join(root,profile.reviewedVocabulary),"utf8");
  write(profile.reviewedVocabulary,originalCore+
    `<${concept}third> a skos:Concept ; rdfs:isDefinedBy <${rootUrl+third}> .\n`);
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
