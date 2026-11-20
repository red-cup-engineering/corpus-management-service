"""Use the RDF Conformance runtime's RDFLib reader for a pinned Turtle graph."""
import json
import sys
from pathlib import Path

from rdflib import Dataset, Graph, RDF, RDFS, SKOS, URIRef

source, graph_name = sys.argv[1:]
core = Graph().parse(data=Path(source).read_text(encoding="utf-8"), format="turtle",
                     publicID="urn:x-glossary:reviewed-source")
if not len(core):
    raise ValueError("reviewed vocabulary cannot be empty")
reviewed = Dataset(default_union=False)
target = reviewed.graph(URIRef(graph_name))
for triple in core:
    target.add(triple)
bindings = sorted(
    (str(concept), str(document))
    for concept in core.subjects(RDF.type, SKOS.Concept, unique=True)
    for document in core.objects(concept, RDFS.isDefinedBy)
    if isinstance(concept, URIRef) and isinstance(document, URIRef)
)
if not bindings:
    raise ValueError("reviewed SKOS vocabulary has no document bindings")
print(json.dumps({"nquads": reviewed.serialize(format="nquads"), "bindings": bindings}))
