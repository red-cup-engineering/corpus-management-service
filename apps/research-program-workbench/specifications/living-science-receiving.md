# Living Science receiving specification

The Workbench's [living-science source contract](../README.md#living-science-sections)
governs the receiving suite. Validate observed source and output behavior; do
not treat validation as a scientific proof or enlist archived materials to
satisfy a source check.

| Case | Required observation |
| --- | --- |
| LS-1: exact source scope | An enrolled document's literal link resolves to its exact file. A legacy namesake is not a substitute. A diagnostic removed without changing the enrolled path set is distinguishable from a note falling out of scope. |
| LS-2: source note receiving | A linked, enrolled, nested `type: reference` yields exactly one anchor when the received Markdown reader is independently rendered as HTML and its full source qualification, and is marked `R` in the manifest. The body link reaches that anchor. An unenrolled archive does not enter the resulting reader. |
| LS-3: selected citation evidence | Pandoc must resolve a citation through the selected bibliography. A decoy bibliography or a fenced citation example is not live evidence. If a live citation stops resolving, the last successfully composed reader and intermediates remain unchanged. |
| LS-4: reviewed vocabulary custody | The selected living member defines the reviewed concept; an archival namesake does not. Check mode detects output drift without writing. Invalid source provenance does not overwrite a prior graph. |

Tests construct a new source directory for each test and invoke the installed
Workbench packages. LS-2 and LS-3 require real Pandoc, not a mock or regex
substitute. The separately owned native question-producer check is not
covered by this suite.

## First-class question receiving

The Workbench's [first-class question contract](../README.md#first-class-science-question--research-program-focus)
and the original recorder's create-only contract govern this separate suite.
Use the issued archive of the exact original recorder, not hand-written
replacement question documents. Run the installed program planner from
outside the package source checkout.

| Case | Required observation |
| --- | --- |
| Q-1: exact recorded question | The native writer returns a create-only receipt under the owning Science section. The planner retains the exact byte digest and full Question section, including a supporting paragraph, while keeping differently spelled references distinct. A claimed source is not an authenticated witness, and graph readiness does not qualify a scientific result. |
| Q-2: explicitly selected program | Only distinct original files selected by the caller enter the program. Active questions share a component through an exact non-firm dependency. A selected resolved question remains visible without entering the active component. |
| Q-3: literal predecessor comparison | A caller-selected predecessor retains its exact digest; added text is reported as an original token span, not semantic novelty. |
| Q-4: refusal and custody | A duplicate record cannot overwrite the first original. Duplicate selection, an absent predecessor or malformed typed relation fails without producing a report or changing the authored files. |

The suite exercises the real recorder and planner only in isolated temporary
directories. It does not publish a question or claim scientific receiving.
