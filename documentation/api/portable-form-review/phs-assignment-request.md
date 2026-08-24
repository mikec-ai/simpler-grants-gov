# PHS Assignment Request human-review handoff

This packet describes automated implementation evidence and the decisions that still require
authorized human reviewers. It does **not** approve the form for privacy, security, policy,
semantic, accessibility, operational, or production release.

## Pinned source boundary

- Grants.gov form: PHS Assignment Request Form, legacy form ID 833, version 4.0.
- Official XSD SHA-256: `7e697ee33ea6f72271c0d74fc48c61f4f81faa242a712a4c73e7898f6c4ab976`.
- Official DAT SHA-256: `e08625bf4ebaee23a66e1ef85346c83e86726a58e36a6c5705f66fffaf867255`.
- Read-only XFA PDF SHA-256: `0fdcbdd7bc136ae2872b76fc61a6cb719d8d02d9a1967257a7c9c2e957e4680a`.
- Normalized NIH Forms I G.600 instruction capture SHA-256:
  `6aef68689060890e9c3cc650a040ea8b36f893527049e582b9474032368b1120`.
- Crosswalk revision: `4312f6504b060e2b9ffdbd2307fc41130c3123a0`; source-set SHA-256:
  `63ef51469ecffd0b7a39bd58f827ebe88bc60e8d368ed0789e4608a862660b4b`.

The package records 13 exact occurrence-to-source mappings as **proposed**. It does not claim
accepted cross-form semantic equivalence. The read-only PDF's illustrative `B10` study-section
code conflicts with the DAT's `BP10`; authored help intentionally omits that disputed example.

## Automated handoff evidence

The focused consumer checks use the banked package through generic Simpler boundaries and prove:

- all 13 source-defined optional slots render through the lower-environment preview form;
- the empty response and a response filling all three awarding-component slots, all three
  study-section slots, all five expertise slots, rationale, and reviewer exclusion validate;
- the representative response survives the JSON persistence boundary and submit-time validation;
- source-declared 7-, 20-, 40-, and 1,000-character limits execute in Simpler validation;
- all representative values serialize through the portable XML profile and validate against the
  exact pinned official XSD;
- the form remains absent from production registrations.

The generic browser matrix supplies a separately pinned receipt for Apply rendering, edit,
save/reload, automated accessibility scanning, keyboard reachability, and locked print rendering.
Automated accessibility results are test evidence, not human accessibility approval.

## Privacy and security questions requiring an authorized decision

The `notReview` response can name individuals, affiliations, relationships, and reasons for
exclusion. Before registration or release, reviewers must decide and record:

1. Who may view or modify reviewer-exclusion requests while an application is in progress, after
   submission, during review, and during post-award retention?
2. Must reviewer-exclusion content be hidden from applicant collaborators, organization users,
   grantors, support staff, logs, analytics, notifications, and ordinary administrative exports?
3. Which API, database, audit-log, support, backup, and data-warehouse paths contain the field, and
   do existing authorization checks cover each path?
4. What event-level audit evidence is required for reads, edits, exports, and administrative access
   without copying the sensitive field value into logs?
5. Which submission XML, printable application, downloadable package, and agency retrieval exports
   may contain the response, and which audiences are authorized to receive each artifact?
6. What retention, deletion, legal-hold, records-management, and incident-response rules apply to
   the response and its replicas?
7. Does the field require a sensitivity marking, applicant warning, restricted rendering, field-
   level encryption, or redaction beyond the controls already applied to application responses?
8. What security and privacy tests must pass before a release decision, and who has authority to
   accept the residual risk?

Answers must be supported by policy and operational evidence. The existence of generic application
authorization, audit logging, or storage controls is not itself proof that their treatment is
appropriate for reviewer-exclusion content.

## Other open human gates

- Confirm the 13 labels, instructions, optionality, limits, and XML paths against the official
  source set, including disposition of the `B10`/`BP10` conflict.
- Decide whether bounded free strings remain appropriate for awarding components and study sections;
  no lookup or enumeration was inferred from source evidence.
- Complete human accessibility review of interaction, reading order, labels, errors, zoom/reflow,
  keyboard operation, assistive technology, and print output.
- Complete NIH policy, records, operational support, and release review.
- Make registration a separate approved change. Banking and preview evidence do not release a form.
