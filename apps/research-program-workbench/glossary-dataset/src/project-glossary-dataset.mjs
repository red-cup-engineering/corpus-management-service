import { projectGlossaryIndex } from "@red-cup-engineering/term-engineering-services-section/glossary-index";
import { TERM_VOCABULARY } from "@red-cup-engineering/term-engineering-services-section/glossary-skos";
import { RELATION_PREDICATE_RANGES } from "@red-cup-engineering/term-engineering-services-section/term-carrier";
import { buildNamedGraph } from "@red-cup-engineering/computer-triplet-serialized-content-engineering-services-section/rdf-named-graph";
import { iriTerm, literal } from "@red-cup-engineering/computer-triplet-serialized-content-engineering-services-section/rdf-terms";
import { serializeNQuads } from "@red-cup-engineering/computer-triplet-serialized-content-engineering-services-section/n-quads";
import { canonicalizeNQuads } from "@red-cup-engineering/computer-triplet-serialized-content-engineering-services-section/rdf-canonicalization";

import { documentIri, hash, prepareGlossaryNavigation, projectGlossaryNavigation, sourcePredicates } from "./project-glossary-navigation.mjs";

export { blobDigest } from "./project-glossary-navigation.mjs";
export { admitProfile, safePath } from "./git-source.mjs";
const fieldName = /^[a-z0-9]+(?:-[a-z0-9]+)*$/u;
const namespace = {
  ...sourcePredicates,
  label: "http://www.w3.org/2000/01/rdf-schema#label",
  derivedFrom: "http://www.w3.org/ns/prov#wasDerivedFrom",
  schema: "https://schema.org/",
};
const graphKinds = ["reviewed-vocabulary", "documents", "navigation", "authored-assertions"];
/** Compose already source-bound data. No network, checkout traversal, publication, or filesystem writes. */
export async function projectGlossaryDataset({ profile, revision, tree, documents, contentPaths, reviewed, authored, audience }) {
  const {texts, ids, inputs, content, allowed} = prepareGlossaryNavigation({profile, revision, tree, documents, contentPaths, audience});
  const base = profile.namespace, vocab = base + "glossary-vocabulary:";
  const iri = (path, version) => documentIri(profile.repository, path, version);
  const graphName = (kind) => base + "graph:" + kind;
  const candidates = [...texts.values()].filter((d) => allowed.has(d.path) && d.filename !== "README.md");
  const index = projectGlossaryIndex({ root: profile.repository.split("/")[1], documents: candidates });
  const byPath = new Map(index.records.map((r) => [r.path, r]));
  const identities = new Map();
  for (const doc of candidates) {
    const identity = doc.frontmatter.identity ?? byPath.get(doc.path)?.identity;
    if (typeof identity !== "string" || !fieldName.test(identity)) continue;
    const matches = identities.get(identity) ?? [];
    matches.push(doc.path);
    identities.set(identity, matches);
  }
  const graphs = new Map(graphKinds.slice(1).map((kind) => [kind, []]));
  const add = (g, subject, predicate, object) => graphs.get(g).push({subject, predicate, object});
  const link = (g, s, p, o) => add(g, s, p, iriTerm(o));
  const contentValue = (g, s, p, o) => add(g, s, p, literal(String(o)));
  const doc = "documents", nav = "navigation", assertions = "authored-assertions";
  for (const {path, filename, frontmatter} of texts.values()) {
    if (!allowed.has(path)) continue;
    const s = iri(path), record = byPath.get(path);
    link(doc, s, namespace.type, namespace.schema + "DigitalDocument");
    contentValue(doc, s, vocab + "path", path);
    contentValue(doc, s, vocab + "gitBlob", ids.get(path));
    contentValue(doc, s, vocab + "termSchemaStatus", filename === "README.md" ? "not-a-term-carrier" : record ? "admitted" : "not-admitted");
    contentValue(doc, s, namespace.label, frontmatter.name ?? frontmatter.title ?? filename);
    link(doc, s, namespace.derivedFrom, iri(path, revision));
    if (record?.identity) contentValue(doc, s, vocab + "termIdentity", record.identity);
  }
  const {rows, observations} = projectGlossaryNavigation({profile, revision, texts, content, allowed});
  graphs.set(nav, rows);
  const claims = new Set();
  let authoredResolved = 0;
  function observation({id, source, key, raw, status, target}) {
    if (claims.has(id)) return;
    claims.add(id);
    link(assertions, id, namespace.type, vocab + "AuthoredRelationObservation");
    link(assertions, id, namespace.source, source);
    contentValue(assertions, id, vocab + "predicateKey", key);
    contentValue(assertions, id, vocab + "rawTarget", raw);
    contentValue(assertions, id, vocab + "projectionStatus", status);
    if (target) link(assertions, id, vocab + "target", target);
    if (status !== "observed-unprojected") authoredResolved++;
  }
  if (authored?.schema !== "research-vocabulary.authored-relations.v1" || authored.audience !== audience
      || !Array.isArray(authored.assertions) || !Array.isArray(authored.unresolved) || authored.unresolved.length
      || !Array.isArray(reviewed?.bindings) || typeof reviewed.nquads !== "string" || !reviewed.nquads) {
    throw new TypeError("resolved Research Workbench evidence and reviewed RDF are required");
  }
  const reviewedAddresses = new Set(reviewed.bindings.map(([concept, source]) => JSON.stringify([concept, source])));
  const addressPaths = new Map([...allowed].map((path) => [iri(path), path]));
  if (reviewed.bindings.some(([, document]) => !addressPaths.has(document))) {
    throw new TypeError("reviewed vocabulary refers to a defining document outside the selected audience");
  }
  const selectedFields = new Map();
  for (const {subject, predicate, object, source, targetSource, field, rawValue} of authored.assertions) {
    const path = addressPaths.get(source);
    const frontmatter = path ? texts.get(path).frontmatter : {};
    const original = Object.hasOwn(frontmatter, field) ? frontmatter[field] : undefined;
    const values = Array.isArray(original) ? original : [original];
    if (!path || !addressPaths.has(targetSource) || typeof field !== "string" || !fieldName.test(field)
        || typeof rawValue !== "string" || !values.includes(rawValue)
        || !values.every(value => typeof value === "string" && fieldName.test(value))
        || new Set(values).size !== values.length
        || !reviewedAddresses.has(JSON.stringify([subject, source]))
        || !reviewedAddresses.has(JSON.stringify([object, targetSource]))) {
      throw new TypeError("authored relation endpoints are not bound to admitted original reviewed documents");
    }
    const id = base+"assertion:"+hash(revision,path,field,rawValue);
    if (claims.has(id)) throw new TypeError("duplicate authored relation evidence");
    const selected = JSON.stringify([path,field]);
    const receive = selectedFields.get(selected) ?? {count:0, expected:values.length, predicate};
    if (receive.predicate !== predicate) throw new TypeError("inconsistent predicate for one authored field");
    receive.count++;
    selectedFields.set(selected, receive);
    link(assertions, subject, predicate, object);
    observation({id,source,key:field,raw:rawValue,status:"admitted-carrier",target:object});
  }
  if ([...selectedFields.values()].some(({count,expected}) => count !== expected)) {
    throw new TypeError("incomplete authored relation field evidence");
  }
  // The owner-authored, exact reviewed evidence already accounts for these
  // observations. The strict Term lens must not duplicate or downgrade them.
  for (const {path, frontmatter} of candidates) {
    const record = byPath.get(path);
    const original = new Map(Object.entries(frontmatter.relations ?? {}));
    for (const key of Object.keys(frontmatter)) if (Object.hasOwn(RELATION_PREDICATE_RANGES, key)) original.set(key, frontmatter[key]);
    for (const [key, value] of original) {
      for (const raw of Array.isArray(value) ? value : [value]) {
        if (typeof raw !== "string") continue;
        const id = base+"assertion:"+hash(revision,path,key,raw);
        if (claims.has(id)) continue;
        const range = RELATION_PREDICATE_RANGES[key], known = record?.relations?.[key];
        const admitted = (Array.isArray(known) ? known : [known]).includes(raw.trim());
        const matches = admitted && range === "carrier" ? identities.get(raw.trim()) ?? [] : [];
        const target = matches.length === 1 && byPath.has(matches[0]) ? iri(matches[0]) : undefined;
        const status = target ? "admitted-carrier" : admitted && range === "literal" ? "admitted-literal" : "observed-unprojected";
        observation({id,source:iri(path),key,raw,status,target});
        if (target) link(assertions, iri(path), TERM_VOCABULARY + key, target);
        else if (status === "admitted-literal") contentValue(assertions, iri(path), TERM_VOCABULARY + key, raw);
      }
    }
  }
  const generated = [...graphs].filter(([,rows])=>rows.length).map(([kind,rows]) => serializeNQuads(buildNamedGraph(rows, graphName(kind))));
  const nquads = await canonicalizeNQuads(generated.join("") + "\n" + reviewed.nquads);
  return {
    nquads, glossaryBlobs: inputs,
    coverage: {
      revision, tree, audience, trackedGlossaryMarkdown: texts.size, projectedDocuments: allowed.size,
      termSchemaAdmitted: byPath.size, termSchemaNotAdmitted: index.refused.length, observationCounts: observations,
      authoredObservations: claims.size, projectedAuthoredObservations: authoredResolved,
      unprojectedAuthoredObservations: claims.size-authoredResolved,
    },
  };
}
