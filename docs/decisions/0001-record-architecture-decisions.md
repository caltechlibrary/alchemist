# 1. Record architecture decisions

- Status: accepted
- Date: 2026-08-31

## Context and Problem Statement

Some of Alchemist's design choices are only legible as the absence of
something: a simpler approach was tried, failed for a non-obvious reason, and
the shipped code is shaped by that failure. Nothing in the code records this.
The next person to read it -- human or LLM -- sees only the surviving design
and is free to "simplify" it back into the thing that already didn't work.

Ad hoc planning documents are a poor home for that knowledge: they mix
durable rationale with build checklists that expire the moment the work
merges, and they go stale silently, describing what was intended rather than
what shipped.

## Decision

Record architecturally significant decisions as ADRs in `docs/decisions/`,
following [MADR](https://adr.github.io/madr/). The format originates with
Michael Nygard's [Documenting Architecture
Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).

Conventions:

- One file per decision, `NNNN-title-in-kebab-case.md`, numbered sequentially
  in the order recorded (not the order decided).
- Each has a status: `proposed`, `accepted`, `rejected`, `deprecated`, or
  `superseded by ADR-NNNN`.
- **ADRs are immutable once accepted.** A decision that changes is not edited;
  a new ADR supersedes it, and the old one is marked as superseded. The record
  of having believed the old thing is the point.
- Corrections of *fact* about what shipped are fine to amend in place, dated
  and noted. Changes of *decision* get a new ADR.
- Record the rejected options and why. That is usually the most valuable part
  and the part that cannot be recovered from the code.

## Consequences

Design rationale gets a stable, linkable home, and the repository root stays
free of ad hoc `.md` files.

The cost is discipline: an ADR nobody writes is worthless, and one nobody
supersedes when the decision changes is worse than worthless. ADRs are for
decisions with consequences that outlive the change that introduced them --
not a log of every change, which is what `CHANGELOG.md` and git history are
for.

Planning documents and build checklists are not ADRs and do not belong in the
repository. If a plan produced a decision worth keeping, the decision
graduates into an ADR; the plan does not.
