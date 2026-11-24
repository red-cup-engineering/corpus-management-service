---
name: managing-project-corpus-knowledge
description: Admits one ActivityStreams Offer, derive separated knowledge-form MAPE stages, and return explicit advice without customer writes or contradiction erasure. Use when asked to admit one ActivityStreams Offer, derive separated knowledge-form MAPE stages, and return explicit advice without customer writes or contradiction erasure.
---
# managing-project-corpus-knowledge

Admit one ActivityStreams Offer, derive separated knowledge-form MAPE stages, and return explicit advice without customer writes or contradiction erasure.

Authored executable: `scripts/manage-project-corpus-knowledge.js`.

input-shape:
lib/schemas/activity-offer.schema.json

output-shape:
ActivityStreams Accept or Reject

preconditions:
[
  "the ActivityStreams Offer addresses this node under the bilateral contract",
  "the capability is attenuated to the supplied corpus digest"
]

postconditions:
[
  "the result is an ActivityStreams Accept or explicit Reject",
  "admitted stages are content-addressed and locally witnessed",
  "customer territory is unchanged"
]

witness:
{
  "records": [
    "data/journals/events/...jsonl CloudEvents router notification",
    "data/journals/eavt/...jsonl EAVT rows"
  ]
}
