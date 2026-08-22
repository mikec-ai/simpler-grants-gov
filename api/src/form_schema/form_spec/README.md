# Portable form-spec adapter

This package is the Simpler-specific boundary for portable artifacts produced by
[`mikec-ai/grants-form-spec`](https://github.com/mikec-ai/grants-form-spec). It contains no
question definitions and does not depend on TypeSpec. It reads versioned JSON artifacts and
projects them into the existing Simpler schema, UI, rule, and shared-schema contracts.

The adapter owns only consumer concerns:

- canonical `camelCase` to Simpler's legacy field names;
- reference retargeting into Simpler's shared-schema resolver;
- compatibility transformations required by the current renderer; and
- selection and verification of the exact runtime artifacts shipped with the API.

`artifacts/artifact-manifest.json` records the producer repository and commit, the digest of
the complete producer bundle, the selection policy, and a digest for every vendored file.
`verify_artifacts()` fails closed before a form can load if any selected file changes.

To refresh a form from a locally downloaded producer bundle:

```shell
cd api
uv run python bin/sync_form_spec_artifacts.py \
  /path/to/grants-form-artifacts.tar.gz \
  --form key-contacts \
  --target src/form_schema/form_spec/artifacts
```

The synchronization command follows `$ref` links to select the form's transitive question
closure. Adding another form therefore does not require copying the whole question bank or
editing a form-specific Python generator.
