# 2. Leave `file_version` ordering and `use_statement` labelling to cascflow

- Status: accepted
- Date: 2026-09-30

## Context and Problem Statement

Alchemist hands `file_version` dicts to
`cascflow.save_digital_object_file_versions()` from
`create_digital_object_file_versions()` (both branches, whether the
`digital_object` already existed or was just created) and from `main()`'s
legacy-S3 migration path. What comes back out in ArchivesSpace is not what
Alchemist passed in, and nothing in this repository says so:

- The entries are **reordered** into a canonical sequence, not the order
  Alchemist listed them.
- Some of Alchemist's *existing* entries are **relabelled** with a
  `use_statement` Alchemist never writes.
- Entries Alchemist didn't touch are **demoted** to `publish: false` and
  `is_representative: false`.
- The `digital_object` itself has its `digital_object_id`, `title` and
  `publish` fields overwritten as a side effect of saving file_versions.

Two things make this worth recording rather than leaving to be rediscovered.

First, Alchemist is not the only writer. Distillery writes a preservation
`file_version` onto the *same* `digital_object`s, pointing at the OCFL object
root in preservation storage. The canonical order exists precisely
because two pipelines interleave on one record; read from inside Alchemist
alone, an ordering rule looks arbitrary.

Second, the ordering is load-bearing in a way that is invisible locally:
**`image-thumbnail` must sort first because ArchivesSpace's
representative-image linking in the public UI depends on its position.** A
reasonable-looking "simplification" that emits file_versions in a different
order, or that sorts them by `use_statement` alphabetically, breaks thumbnails
in the public interface with no error anywhere.

## Decision Drivers

- One implementation of the ordering, not one per pipeline that writes
  file_versions.
- A reader of Alchemist should be able to find out why its output is
  rearranged from this repository alone.
- Adding a `use_statement` is not a local change: ArchivesSpace rejects any
  value absent from its own `use_statement` enumeration.

## Considered Options

1. Leave the conventions implicit in cascflow's source.
2. Sort and label file_versions in Alchemist before calling cascflow.
3. Record the conventions here, keep the single implementation in cascflow.

## Decision Outcome

**Option 3.** cascflow remains the only implementation;
`FILE_VERSION_USE_STATEMENT_ORDER` and `sort_file_versions()` are not
reimplemented, shadowed or pre-empted in Alchemist. This ADR is the reference
for what that costs Alchemist.

The rules cascflow applies, as of cascflow v5.0.0:

| Position | `use_statement` | Written by |
|---|---|---|
| 1 | `image-thumbnail` | Alchemist |
| 2 | `Persistent-URL` | Alchemist |
| 3 | `Web-Access` | Alchemist |
| 4 | `OCFL-Object-Root` | Distillery |
| 5 | `OCFL-Object-Inventory` | the storage audit tool (S3 copy) |
| 6 | `URL-Redirected` | nothing; assigned by the relabel below |

An unrecognized `use_statement` sorts after all recognized ones, stably.

The merge is keyed by `file_uri`. An existing entry whose `file_uri` is absent
from the incoming list is kept, but demoted to `publish: false` and
`is_representative: false`. If that entry is an `image-thumbnail` or
`Web-Access` one **and** its `file_uri` does not contain the object's current
ARK, it is relabelled `URL-Redirected`, sending it to the end of the order.
That ARK test is the whole point of the rule: it separates an entry retired by
the ARK migration from one merely superseded by a newer same-scheme entry
(re-sequenced ptifs, for instance), which keeps its original
`use_statement`.

### Consequences

Alchemist cannot assume the order it emits is the order stored, and must not
be written as though it could.

A cascflow pin bump can change Alchemist's ArchivesSpace output with no change
to Alchemist's own code. That is not hypothetical: pinning v5.0.0 moved
Distillery's preservation entry from last place -- below the retired
`URL-Redirected` entries -- to position 4, in records Alchemist also writes to.
Read the cascflow changelog on a pin bump, not just Alchemist's.

Introducing a new `use_statement` means a cascflow change (to add it to the
order) plus a one-time addition to the ArchivesSpace instance's `use_statement`
enumeration, which is outside every repository here. A value missing from the
enumeration is rejected by the backend.

Publishing is not opt-in: saving file_versions sets `publish: true` on the
`digital_object`.

## More Information

- `cascflow/src/cascflow/cascflow.py`:
  `FILE_VERSION_USE_STATEMENT_ORDER`, `sort_file_versions()`,
  `save_digital_object_file_versions()`.
