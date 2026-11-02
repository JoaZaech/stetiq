# Promotion is never blocked; review happens in the user's repository

A Promotion moves an Alias to an Ontology Version, and stetiq never refuses it: not for a failing Gate, and not for a missing approval. It records the move instead: who promoted, when, and the version's latest Gate result. We considered borrowing OpenMetadata's glossary approval workflow (#195), where a term with reviewers stays in review until a reviewer approves it, and ruled against it. The review a Candidate needs already happens before stetiq sees a Promotion, in the user's repository: the change to the Ontology and the Use Case goes through the repository's pull request, CI evaluates its Gates and records the result (ADR 0007), and whoever promotes acts on that. What a Consumer would lose is judged by its Consumer Gate and enforced at the Consumer's edge, by the upstream pipeline's CI or the Consumer's Connector, not at Promotion (ADR 0008). An approval step inside stetiq would add a second, weaker review next to the one the repository already enforces, and it would need a notion of reviewers that stetiq does not have: an API Token grants only *read* or *edit* on a Knowledge Graph (ADR 0002), and the named Authority who decided Ontology changes was cut for the MVP (#142, #147).

## Considered Options

- **Adopt: an approval workflow in stetiq.** A Candidate gets reviewers and an approve/reject state, and Promotion is refused until it is approved. Rejected: it reverses the rule that Promotion is not blocked, even by Gates; it brings back Authority under another name; and it needs reviewer roles, review tasks and notifications that the read/edit token model does not provide.
- **Integrate: OpenMetadata as the approver.** stetiq pushes Candidates into OpenMetadata and promotes once its workflow approves them. Rejected: the core would depend on an external catalog and its availability, which runs against keeping integrations at the edge (ADR 0005), and the approval would happen outside the audit stetiq records.

## Consequences

- Any token with *edit* on a Knowledge Graph can promote, and a rollback is a Promotion like any other. Teams that want a second pair of eyes require it in their repository (branch protection, required reviews, a CI job that is the only holder of an *edit* token).
- If approvals are ever wanted inside stetiq, they enter as one more fact in the Promotion audit, recorded next to the Gate result, and they never block the move.
- The glossary steers away from "approval" for Promotion, as it does from "release" and "deploy".
