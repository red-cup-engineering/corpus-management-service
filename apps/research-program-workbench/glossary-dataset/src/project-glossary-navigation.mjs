import { semanticHex } from "@red-cup-engineering/semiotic-content-address-system";
import { basename } from "node:path";
import { gitBlobIdOf } from "@red-cup-engineering/git-engine/git-object-id";
import { readMarkdownFrontmatter } from "@red-cup-engineering/markdown-engineering-services-section/read-markdown-frontmatter";
import { readMarkdownSource } from "@red-cup-engineering/markdown-engineering-services-section/read-markdown-structure";
import { projectMarkdownFeatures } from "@red-cup-engineering/markdown-engineering-services-section/read-markdown-features";
import { DEFAULT_FRONTMATTER_REFERENCE_KEYS, deriveMarkdownVaultGraph } from "@red-cup-engineering/markdown-engineering-services-section/derive-markdown-vault-graph";
import { projectMarkdownLinkPath, parseMarkdownLinkDestination } from "@red-cup-engineering/markdown-engineering-services-section/resolve-markdown-link-target";
import { glossaryAudienceAdmits } from "@red-cup-engineering/term-engineering-services-section/glossary-skos";
import { iriTerm, literal } from "@red-cup-engineering/computer-triplet-serialized-content-engineering-services-section/rdf-terms";

import { admitProfile, safePath } from "./git-source.mjs";

const sha1 = /^[a-f0-9]{40}$/u;
export const hash = (...args) => semanticHex(args.map((value) => value ?? null));
export const sourcePredicates = {
  type: "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
  source: "http://purl.org/dc/terms/source",
};
export function documentIri(repository, path, revision = "main") {
  return "https://github.com/" + repository + "/blob/" + revision + "/" + path.split("/").map(encodeURIComponent).join("/");
}
export const blobDigest = gitBlobIdOf;

/** Verify, decode, and admit the exact input catalog used by builder and replay. */
export function prepareGlossaryNavigation({profile, revision, tree, documents, contentPaths, audience}) {
  admitProfile(profile);
  if (audience !== "authenticated" || !sha1.test(revision) || !sha1.test(tree)) throw new TypeError("authenticated audience and exact Git commit/tree are required");
  const texts = new Map(), ids = new Map(), inputs = [];
  const content = new Set(contentPaths);
  for (const {path, oid, bytes} of documents) {
    if (!safePath(path) || !path.startsWith(profile.glossaryRoot + "/") || !path.endsWith(".md")
        || !content.has(path) || texts.has(path) || !sha1.test(oid) || blobDigest(bytes) !== oid) throw new TypeError(`unqualified glossary blob: ${path}`);
    const text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes);
    const frontmatter = readMarkdownFrontmatter(text).frontmatter ?? {};
    texts.set(path, {path, filename: basename(path), text, frontmatter, features: projectMarkdownFeatures(readMarkdownSource(text))});
    ids.set(path, oid);
    inputs.push([path, oid]);
  }
  if (texts.size === 0 || content.size !== contentPaths.length
      || contentPaths.some((p) => !safePath(p) || !p.startsWith(profile.contentRoot + "/"))
      || contentPaths.some((p) => p.startsWith(profile.glossaryRoot + "/") && p.endsWith(".md") && !texts.has(p))) {
    throw new TypeError("glossary and exact content inventory do not agree");
  }
  const allowed = new Set([...texts.values()].filter(d => glossaryAudienceAdmits(d.frontmatter, audience)).map(d => d.path));
  return {texts, ids, inputs, content, allowed};
}

/** Compose the original Markdown occurrence view into its exact RDF graph rows. */
export function projectGlossaryNavigation({profile, revision, texts, content, allowed}) {
  const base = profile.namespace, vocab = base + "glossary-vocabulary:";
  const iri = (path) => documentIri(profile.repository, path);
  const rows = [];
  const link = (subject, predicate, value) => rows.push({subject, predicate, object:iriTerm(value)});
  const contentValue = (subject, predicate, value) => rows.push({subject, predicate, object:literal(String(value))});
  const observations = Object.create(null);
  const observed = deriveMarkdownVaultGraph({
    documents: [...texts.values()],
    frontmatterReferenceKeys: [...DEFAULT_FRONTMATTER_REFERENCE_KEYS, "see-also", "provenance.see-also"],
  });
  for (const [position, edge] of observed.edges.entries()) {
    const from = edge.sourcePath;
    if (!allowed.has(from)) continue;
    let status = edge.status, target;
    if (status === "resolved") {
      if (!allowed.has(edge.targetPath)) continue;
      target = iri(edge.targetPath);
      status = "resolved-in-glossary";
    } else if (status === "external") {
      try { target = iriTerm(edge.externalUrl).value; } catch { status = "unverified-local-or-external"; }
    } else if (status === "dangling" && ["markdown-link", "markdown-image"].includes(edge.kind)) {
      const address = parseMarkdownLinkDestination(edge.target);
      const path = projectMarkdownLinkPath(from, address.path);
      if (path.startsWith("../")) status = "outside-repository";
      else if (content.has(path) && !texts.has(path)) {
        status = "tracked-outside-glossary";
        target = iri(path);
      } else status = "unverified-local-or-external";
    }
    const id = base + "link:" + hash(revision, from, position, edge.kind, edge.target, edge.fragment);
    observations[status] = (observations[status] ?? 0) + 1;
    link(id, sourcePredicates.type, vocab + "LinkObservation");
    link(id, sourcePredicates.source, iri(from));
    contentValue(id, vocab + "linkKind", edge.kind);
    contentValue(id, vocab + "rawTarget", edge.target);
    contentValue(id, vocab + "resolution", status);
    if (edge.fragment) contentValue(id, vocab + "fragment", edge.fragment);
    if (edge.key) contentValue(id, vocab + "frontmatterKey", edge.key);
    if (target) link(id, vocab + "target", target);
  }
  return {rows, observations};
}
