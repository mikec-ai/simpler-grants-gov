# R&R Senior/Key Person Expanded lifecycle gate matrix

This is a technical canary for a vendored portable form package. It is not a
production-readiness decision, human acceptance, or a release opt-in. The package stays
out of `registrations.json` until every release gate has an accountable review.

| Area | Technical evidence in this repository | Current gate |
| --- | --- | --- |
| Portable loading and identity | The generic loader projects the pinned package and constructs a typed `Form` identity. There is no form-specific adapter branch. | Technically proven; production registration remains disabled. |
| Repeated people | Artifact-backed widget tests exercise add, delete, edit, lock, and the declared 99-row maximum. API validation covers the 99/100 boundary and nested required fields. | Technically proven at component and validation boundaries; end-to-end accessibility review remains open. |
| Persistence | A DB-backed application-service test saves and reloads repeated people through `update_application_form`. | Technically proven in supported DB test/CI; operational production exercise remains open. |
| Attachments | Validation checks ownership for all seven paths: PI nested fields, repeated-person nested fields, and the three top-level overflow capture fields. Save-time audit tests use the projected UI schema. Locked print tests hydrate repeated-person values and filenames. | Structural behavior proven; the source and semantic meaning of the three overflow capture fields still needs human review. |
| Conditions | Item-scoped and root-scoped declarations are projected and unit-tested. | Generic condition producer/adapter integration and source reconciliation are pending; do not claim complete conditional behavior. |
| Validation and submit service | Valid and invalid response vectors run through Simpler validation. A DB-backed service test proves a valid response passes `submit_application` and changes application status. | Submission validation/status scaffolding only; downstream delivery, XML, and agency acceptance are not proven. |
| XML | The manifest intentionally has no Grants.gov XML target and tests assert that absence. | Blocked on the producer XML profile and official XSD/DAT reconciliation. Do not duplicate mappings in the adapter. |
| Source and semantics | Extraction provenance and hashes are pinned in package evidence. | `semanticReview.status` is `unreviewed`; extracted similarity is not semantic acceptance. |
| Form and instruction identifiers | The runtime form UUID is deterministic. No instruction UUID is assigned. | Identifier governance and approved instructions are human gates. |
| Accessibility | Generic widgets use the shared Simpler controls and focused interaction tests. | Keyboard, screen-reader, error announcement, focus, and full-page accessibility validation remain required. |
| Release | The package is locally vendored and technically loadable. | Product/policy approval, human semantic review, accessibility acceptance, instruction approval, XML conformance, and explicit registration are required before release. |

## Integration order

1. Integrate the generic condition producer and adapter after their independent review.
2. Add the producer-owned Grants.gov XML mapping and exact XSD conformance tests.
3. Re-run this lifecycle suite, including DB-backed persistence and submit validation.
4. Complete the human gates above before adding the form to production registration.
