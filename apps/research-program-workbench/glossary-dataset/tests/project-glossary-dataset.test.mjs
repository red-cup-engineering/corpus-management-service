import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
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
