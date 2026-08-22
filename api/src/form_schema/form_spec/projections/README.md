# Per-form legacy naming

The projection turns the specification's `camelCase` names into this codebase's `snake_case`
ones. Most of that is mechanical. A few field names are not a transformation of anything —
SF-424-Short spells a contact's telephone number `phone_number` where the question calls it
`phone` — and those are named here, one file per form.

Keyed by canonical data path (`keyContacts.projectRole`), or by a bare member name to cover
every place that member appears. An exact path wins over a bare name.

Each entry carries a target and a `why`, because an entry without a reason is
indistinguishable from a typo, and the whole point of collecting them here is that the total
stays countable. For example:

```json
{
  "renames": {
    "phone": {
      "to": "phone_number",
      "why": "This legacy form stores the shared phone question under phone_number."
    }
  }
}
```

These files live outside `artifacts/`, which is rebuilt from the emitted output.

The same file may declare `schemaAnnotations` when the legacy runtime requires a portable
constraint or annotation to appear directly on a property rather than through its shared
question reference. Each declaration contains `values` and a `why`; the adapter applies the
data mechanically.
