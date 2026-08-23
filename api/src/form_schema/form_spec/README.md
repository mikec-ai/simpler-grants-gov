# Portable form-spec adapter

This package is the Simpler-specific boundary for portable artifacts produced by
[`mikec-ai/grants-form-spec`](https://github.com/mikec-ai/grants-form-spec). It contains no
question definitions and does not depend on TypeSpec. It reads versioned JSON artifacts and
projects them into the existing Simpler schema, UI, rule, and shared-schema contracts.

Forms may also publish an optional `targets/grants-gov-xml.json` profile. The profile owns
the form's root element, namespaces, XSD identity, canonical response-to-XML mapping, and
standard attachment child wire fields.
The adapter loads that data and applies the same legacy-name projection used for the JSON
Schema; it contains no budget-family names, durations, wrappers, or per-form mapping code.

The adapter owns only consumer concerns:

- canonical `camelCase` to Simpler's legacy field names;
- reference retargeting into Simpler's shared-schema resolver;
- compatibility transformations required by the current renderer; and
- mechanical translation of portable XML nodes and declared attachment fields into the
  existing generic XML runtime vocabulary;
- selection and verification of the exact runtime artifacts shipped with the API.

Portable form registration is also declarative. `registrations.json` is the SGG-owned opt-in
list and contains only SGG instruction identifiers. Form UUIDs, names, versions, and `FormType`
come from each producer manifest. The historical per-form Python modules remain compatibility
import paths; they all return the same cached object built from that registration.

`artifacts/artifact-manifest.json` records the producer repository and commit, the digest of
the complete producer bundle, the selection policy, and a digest for every vendored file.
`verify_artifacts()` fails closed before a form can load if any selected file changes. For every
selected XML profile it also resolves the XSD filename from the declared URI and checks the
declared SHA-256 against the vendored official XSD. This is generic integrity enforcement: it
does not download schemas or contain a form-family lookup table.

To refresh a form from a locally downloaded producer bundle:

```shell
cd api
uv run python bin/sync_form_spec_artifacts.py \
  /path/to/grants-form-artifacts.tar.gz \
  --form key-contacts \
  --form sf424 \
  --target src/form_schema/form_spec/artifacts
```

The synchronization command accepts repeated `--form` flags, includes optional target artifacts
declared by each form manifest, and follows `$ref` links to select the combined transitive question
closure. Adding another form therefore does not require copying the whole question bank or editing
a form-specific Python generator.

For a routine pin update, use the higher-level command. It makes an isolated local clone at the
explicit revision, runs the producer's complete preflight, preserves the current form allowlist,
checks XSD pins, and atomically replaces the selection:

```shell
cd api
uv run python bin/update_form_spec_artifacts.py \
  --producer /path/to/grants-form-spec \
  --revision <full-producer-commit>
```

Portable forms cannot inject an alternate Python XML mapping into `build_runtime_form`; the
optional XML profile in the producer package is their only mapping source. Legacy forms continue
to use their existing inline schemas until they are migrated. Likewise, the centralized
`jsonschema_resolver` patch remains a compatibility boundary for the current application, while
portable artifacts themselves use standard JSON Schema references and composition.
