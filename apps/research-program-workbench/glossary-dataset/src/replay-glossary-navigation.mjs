import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { buildNamedGraph } from "@red-cup-engineering/computer-triplet-serialized-content-engineering-services-section/rdf-named-graph";
import { serializeNQuads } from "@red-cup-engineering/computer-triplet-serialized-content-engineering-services-section/n-quads";
import { canonicalizeNQuads } from "@red-cup-engineering/computer-triplet-serialized-content-engineering-services-section/rdf-canonicalization";
import { readPinnedGlossarySource } from "./git-source.mjs";
import { prepareGlossaryNavigation, projectGlossaryNavigation } from "./project-glossary-navigation.mjs";
import { observeNodeProviders } from "./snapshot-receipt.mjs";

/** Replay just the navigation graph from native Git, not a claimed snapshot. */
export async function replayGlossaryNavigation({repository, revision, profile:profilePath, audience}) {
  if (audience !== "authenticated" || ![repository, revision, profilePath].every(v=>typeof v==="string" && v.length))
    throw new TypeError("an authenticated audience, native Git repository, exact revision and Science profile path are required");
  observeNodeProviders();
  const {source, profile, documents, contentPaths} = readPinnedGlossarySource({repository, revision, profilePath});
  const {texts, content, allowed} = prepareGlossaryNavigation({profile, revision, tree:source.tree, documents, contentPaths, audience});
  const {rows} = projectGlossaryNavigation({profile, revision, texts, content, allowed});
  // The full projector omits graphs with no statements. Empty N-Quads is the
  // exact observation in that case, not a synthetic empty RDF graph.
  if (!rows.length) return "";
  return canonicalizeNQuads(serializeNQuads(buildNamedGraph(rows, profile.namespace + "graph:navigation")));
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const {values} = parseArgs({
      options: {repository:{type:"string"}, revision:{type:"string"}, profile:{type:"string"}, audience:{type:"string"}},
    });
    process.stdout.write(await replayGlossaryNavigation(values));
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
