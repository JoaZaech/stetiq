# How OpenMetadata's glossary approval workflows work

Research for [#190](https://github.com/JoaZaech/stetiq/issues/190), part of the wayfinder map [#186](https://github.com/JoaZaech/stetiq/issues/186). Read on 2026-11-02.

**Sources.** OpenMetadata source is pinned to `main` at commit [`8ec9723`](https://github.com/open-metadata/OpenMetadata/tree/8ec972354c60f5fcabca1965de7708538afc3eb6) (2026-11-02). Below, `svc/` stands for `openmetadata-service/src/main/java/org/openmetadata/service/`, `spec/` for `openmetadata-spec/src/main/resources/json/schema/`, and `seed/` for `openmetadata-service/src/main/resources/json/data/governance/workflows/`. Released versions: 2.0.7 is the latest stable release (2026-10-27) and 2.1.0-rc1 is a pre-release (2026-10-28) (`gh release list -R open-metadata/OpenMetadata`). The docs are at docs.open-metadata.org. "Glossary Term", "Reviewer", "Task", "Ontology Release" and similar are OpenMetadata terms. stetiq terms are capitalised as in `GLOSSARY.md`.

## Answer in brief

- **Glossary terms.** A glossary term moves Draft → In Review → Approved or Rejected. This is driven by one seeded workflow, `GlossaryTermApprovalWorkflow`, which runs on OpenMetadata's governance workflow engine. That engine is a JSON node/edge graph compiled to BPMN and run by Flowable.
- **Reviewers and Tasks.** Reviewers are set on the glossary or on a parent term. The approval Task goes to them. One approval or one rejection decides it by default.
- **Edits to approved terms.** An edit to an approved term goes back into review. If that edit is rejected, the term is **rolled back** to its last approved version.
- **What approval blocks.** Approval holds back very little. The UI's tag picker offers only Approved terms. I found no server-side check that does the same.
- **Positioning finding.** On `main`, after 2.0.7 and in the 2.1.0 line, OpenMetadata added **native Ontologies with sealed, immutable Ontology Releases**. A release is reviewed as a whole through the same approval workflow. Only an approved release can be **activated**, and activation is also how a release is rolled back. This is close to stetiq's Candidate → Promotion of an Ontology Version via an Alias. It also adds an approval gate that stetiq does not have. OpenMetadata does not have stetiq's classified Ontology Diff, its Gates, or anything that judges a change by its Consumers.

## 1. Glossary term statuses

- **The status field.** A term's status is `entityStatus` (`spec/entity/data/glossaryTerm.json`). It is typed by the shared enum `spec/type/status.json`, which has these values: `Draft`, `In Review`, `Approved`, `Archived`, `Deprecated`, `Rejected`, `Unprocessed`. That enum is a "General lifecycle stage for entities", used by more than glossary terms.
- **Starting status.** `GlossaryTermRepository.initialEntityStatus` (`svc/jdbi3/GlossaryTermRepository.java`, around line 1040) sets it. A new term starts as **Draft** in three cases: its parent term or glossary has reviewers (inherited, with the parent term checked before the glossary), its `provider` is `automation`, or a lifecycle playbook owns its stage. In every other case it starts as **Approved**. The status is "Applied to every new term whatever stage its request asked for, so creating a term cannot skip the review."
- **What the docs say.** This matches the docs: "The new term will show up in the Glossary, but will be marked as Draft", and "If the glossary has no Reviewers assigned, the glossary terms are Approved by default" ([approval docs](https://docs.open-metadata.org/latest/how-to-guides/data-governance/glossary/approval)).

## 2. The default workflow: `GlossaryTermApprovalWorkflow`

The definition is `seed/GlossaryApprovalWorkflow.json`. Its trigger is `eventBasedEntity` on `glossaryTerm`, for the events `Created` and `Updated`. Changes to `entityStatus` itself are excluded, so the workflow does not re-trigger itself. The graph, branch by branch:

1. **Automation-proposed term** (`provider == automation` and not yet Approved). This is a separate branch, covered in section 4.
2. **No reviewers** (`CheckGlossaryTermHasReviewers` is false): the term is set to **Approved**.
3. **Reviewer as editor.** If the editor is themselves a reviewer (`isReviewer(updatedBy)`), the term is auto-approved (`SetGlossaryTermStatusToApprovedByReviewer`).
4. **No description.** If the term has no description (`CheckGlossaryTermIsReadyToBeReviewed`), it is set to **Draft** and the workflow ends. A term needs a description before it can enter review.
5. **New term** (`version == 0.1`): the term goes to **In Review**, and a `userApprovalTask` named `ApproveGlossaryTerm` is created. Approving sets it to **Approved**. Rejecting sets it to **Rejected**.
6. **Update to an existing term:** the term goes to **In Review**, and a `userApprovalTask` named `ApprovalForUpdates` is created. Approving sets it to **Approved**. Rejecting runs **`rollbackEntityTask`**, which "Rolls back an entity to its previous approved version. Always rolls back to the most recent 'Approved' status" (`spec/governance/workflows/elements/nodes/automatedTask/rollbackEntityTask.json`).

The approval tasks share this configuration: `assignees: {addReviewers: true, addOwners: false}`, `approvalThreshold: 1`, `rejectionThreshold: 1`, `assigneeStrategy: reviewers-and-assignees`, plus stage and transition metadata (`stageId: review`, transitions `approve`/`reject`).

## 3. Reviewers, Tasks and who may decide

- **Reviewer checks** (`svc/jdbi3/EntityRepository.java`, around lines 1630–1720):
  - When an entity is In Review, only a reviewer can move it to Approved or Rejected by a direct edit or a CSV import (`checkReviewerLeavesReview` and `checkUpdatedByReviewer`). A team reviewer counts any of its members.
  - A workflow's own approval task has already decided who may approve, so its writes skip this check.
  - When an active workflow owns the stage, a direct edit to the status is refused (`checkEntityStatusNotOwnedByWorkflow`).
- **Closing the approval task.** A status change closes the open approval task automatically, with a comment such as "Approved the glossary term", "Rejected the …" or "Closed due to … going back to DRAFT" (`closeApprovalTaskOnEntityStatusChange`).
- **Discussing a term.** Reviewers discuss the term on the Task thread and can @mention other users ([approval docs](https://docs.open-metadata.org/latest/how-to-guides/data-governance/glossary/approval)). From 2.0.6, "an approval by an administrator or owner that the workflow authorizes also updates the term" (same page).
- **Self-approval (2.0 behaviour)** ([2.0 breaking changes, data governance](https://docs.open-metadata.org/v2.0.x/deployment/upgrade/breaking-changes/data-governance.md)):
  - "Task authorization refuses to let a task's creator approve their own task, even where policy would otherwise allow it."
  - `emptyAssigneeStrategy: assignAdmins` "Falls back to all platform admins, excluding the requester, so self-approval can never happen". The default is `none`.
  - The doc warns that tasks with no assignee were "silently auto-approving".
  - Task actions (`CreateTask`, `ResolveTask`, …) are now policy-governed.
- **Tension with the editor auto-approval.** Step 3 of the default workflow lets a reviewer's own edit auto-approve, so a reviewer who edits a term does approve their own change. The no-self-approval rule applies to *tasks* only.

## 4. Automation-proposed terms

This is the part most relevant to LLM pipelines.

- **Provider types.** `providerType` (`spec/type/basic.json`) is `system`, `user` or `automation`. The schema describes the last as: "Some apps such as AutoPilot create entities with `automation` provider type."
- **Hard rule for automation proposals.** `GlossaryTermRepository.checkStageDecision` enforces: "A term an automation proposed is published only by a person's decision: a bot, or a workflow writing for one, never approves it, however the approval workflow is configured." A bot that tries gets an `AuthorizationException`: "A person must approve glossary term '%s', which an automation proposed".
- **Workflow branch.** The seeded workflow has a branch for automation proposals. If no reviewer resolves, it falls back to admins (`emptyAssigneeStrategy: assignAdmins`). A rejected *update* to an automation proposal is rolled back.
- **Shape of the rule.** The rule is: a machine may propose, and only a person may publish. It is the same human-in-the-loop rule stetiq's AI-drafting story would need.

## 5. The governance workflow engine

- **Workflow definitions.** A `WorkflowDefinition` (`spec/governance/workflows/workflowDefinition.json`) is an entity with a `trigger`, a list of `nodes` and a list of `edges`, plus `deployed` and `suspended` flags. It is versioned like any other entity.
- **Triggers:** `eventBasedEntity`, `periodicBatchEntity` and `noOp` (`spec/governance/workflows/elements/triggers/`).
- **Node subtypes** (`elements/nodeSubType.json`):
  - human: `userApprovalTask`
  - checks: `checkEntityAttributesTask` (JSON-logic rules), `checkChangeDescriptionTask`, `dataCompletenessTask`
  - mutations: `setEntityAttributeTask`, `setGlossaryTermStatusTask`, `setEntityCertificationTask`, `rollbackEntityTask`
  - other: `runAppTask`, `createAndRunIngestionPipelineTask`, `createAndRunAIAutomationTask`, `policyAgentTask`, `sinkTask`, `parallelGateway`, start and end events
- **Execution.** The definitions are compiled to BPMN and executed by **Flowable**. `svc/governance/workflows/WorkflowHandler.java` imports `org.flowable.bpmn.*`, and the builders are in `svc/governance/workflows/flowable/builders/`.
- **Seeded workflows.** The same engine runs about 20 seeded workflows (`seed/`): glossary, metric and AI-asset approval, plus description, tag, owner, tier and domain update tasks, incident lifecycle, and others.
- **History.** Glossary approval was the first workflow moved onto this framework, in 1.6. Before that, from 1.2, terms started as Draft and an approval Task was created for reviewers ([Collate blog on the 1.6 workflow system](https://www.getcollate.io/blog/how-collates-new-workflow-system-automates-data-governance); this is a vendor source).
- **Lifecycle playbooks.** `spec/governance/workflows/lifecycleConfiguration.json` adds optional "guided lifecycle" metadata (`version`, `entityType`, `gates`), so a workflow can be edited as stages. The "executable nodes and edges remain authoritative".

## 6. What approval actually blocks

- **Tag picker (UI only).** The UI's glossary-term tag picker searches only approved terms: `openmetadata-ui/src/main/resources/ui/src/utils/TagsUtils.tsx:165` uses `getQueryFilterToIncludeApprovedTerm()`. On the server, the tag-label check I found (`TagLabelUtil.checkDisabledTags`) refuses only *disabled* tags, not unapproved terms. The block therefore looks like UI-only, though I did not exhaustively verify every API path. The docs say nothing about restrictions before approval.
- **Rejected updates.** A rejected update is undone by rollback, so an approved term never stays in an unapproved shape.
- **Ontology releases.** For native ontologies (section 7), approval is a hard server-side block on activation.

## 7. Versioning, and the new native Ontology Releases

**Glossary terms.** Glossary terms use OpenMetadata's generic entity versioning: `version` starts at `0.1` (the workflow tests `version == 0.1` to mean "new"), and each change carries a `changeDescription`. Rollback restores the last version whose status was Approved. No separate release unit exists.

**Native Ontologies (new on `main`, 2.1.0 line).** These were added by PR [#35672](https://github.com/open-metadata/OpenMetadata/pull/35672), "Add native ontologies and governed releases", merged 2026-10-19. Follow-ups #35812 and #35990 merged 2026-10-20 and 2026-10-29. The schema files exist at tag `2.1.0-rc1-release` but not at `2.0.7-release`, so this is **pre-release only**.

- **What a release is.** `OntologyRelease` (`spec/entity/data/ontologyRelease.json`) is "Sealed ontology content, stored as immutable SQL members and reviewed through the existing approval workflow". Its fields:
  - `releaseRevision` (monotonic)
  - `semanticVersion`, with a MAJOR/MINOR/PATCH bump **chosen by the requester** (`svc/ontology/OntologyReleaseCapture.java`, `OntologyReleasePublication.nextVersion`), not derived from the diff
  - `releaseNotes`
  - `contentDigest` (SHA-256 of the sealed manifest)
  - `baseReleaseId` (the active release at capture, used as the review baseline)
  - `changeSummary`, with counts of `added`, `changed`, `removed` and `deprecated` (`spec/type/ontologyReleaseChangeSummary.json`)
  - `entityStatus`
  - `reviewTask`
- **Review unit.** The whole release is the unit of review. In the PR's words: "Per-definition approvals were excluded because publication approves the complete release."
- **Approval rule.** `Ontology.approvalRule` is `AnyReviewer` or `AllReviewers`, and it is frozen into the review task when review is requested (`spec/type/ontologyApprovalRule.json`).
- **Activation.** `svc/ontology/OntologyReleaseActivation.requireApprovedOwner` refuses with "Activation requires an approved, sealed release of this ontology". Activation is a compare-and-set on `activationRevision`. Rollback "activates an older approved release". Edits to the working model never change the active release, which is the one used for published queries.
- **Audit.** `OntologyReleaseEvent` is an append-only log of `CAPTURED`, `APPROVED`, `REJECTED` and `ACTIVATED` events. Each event records the user, the content digest, the previous release, the task and workflow ids, and the voters (`spec/type/ontologyReleaseEvent.json`).
- **Checks at capture.** Capture checks structure and the OWL 2 DL profile. Logical consistency is `NOT_RUN`. A separate SHACL "export gate" refuses to export a release that fails validation (`svc/ontology/OntologyExportGate.java`).
- **Unpublished work.** `publicationStatus.unpublishedChanges` counts the working-model members that differ from the active release.

## 8. Mapping onto stetiq

| OpenMetadata | stetiq (`GLOSSARY.md`) | Fit |
|---|---|---|
| Glossary term `Draft` / `In Review` | **Candidate**: an Ontology Version no Alias has pointed to yet | Partial. The OpenMetadata unit is a single term. stetiq's is a whole Ontology Version, which matches the native OntologyRelease better. |
| Native `OntologyRelease` (sealed, content digest, revision number) | **Ontology Version**: an immutable snapshot, numbered 1, 2, 3…, deduped by content hash | Strong. Both are immutable, content-hashed and monotonically numbered. |
| Active release, set by activation or rollback, compare-and-set | **Alias** / **Contract Alias** (`production`), moved by **Promotion** | Strong. OpenMetadata has one implicit "active" pointer per ontology. stetiq has named Aliases. |
| Activation requires `Approved` | Promotion "is not blocked by Gates, but the audit records whether the version's latest Gate result passed" | **Divergent.** OpenMetadata blocks on human approval. stetiq blocks on nothing and records the outcome. |
| `OntologyReleaseEvent` log (captured / approved / rejected / activated) | Promotion audit (actor = the token's user, plus `gate_result`) | Close. stetiq's audit has no approve or reject event because there is no approval step. |
| `changeSummary` counts plus a requester-chosen semver bump | **Ontology Diff**, with each change classed as cosmetic, additive, deprecating or breaking | stetiq goes further: it classifies each change, where OpenMetadata leaves the classification to a human. |
| Reviewers, `approvalRule`, approval Task | **Authority** (cut): "the person or function … who decides changes to its Ontology. A name only" | Authority was a name with no workflow. OpenMetadata shows what a working version needs: reviewers, a task, a threshold, and a block on activation. The MVP cut it (#142), and this research does not argue for restoring it before the pilot. |
| Owners | **Steward** (cut) | Out of scope for #186 ("repeats Steward/Authority"). |
| `provider: automation` term, which only a person may approve | Candidate from an *evolving* Construction Run (an LLM pipeline) | Good conceptual fit. "A machine proposes, a person publishes" is what stetiq's planned AI drafting needs. |
| No Consumer-aware check | **Gate**, **Consumer Gate**, **Consumer Drift** | OpenMetadata has no equivalent. Its review is a human reading a diff. Nothing evaluates what a downstream Consumer would lose. |

**What is worth borrowing, as concepts:**

- Rollback-on-reject for updates, so the published thing never sits in an unapproved shape.
- "A machine proposes, a person publishes" as a server-enforced rule for machine-provided Candidates.
- An approve/reject event in the Promotion audit, if stetiq ever adds an approval step.

All three are post-MVP and need validation in pilot interviews.

**What not to borrow:**

- The BPMN/Flowable workflow engine. It is heavy, and per-entity approval of single terms is the wrong unit for stetiq; OpenMetadata itself moved to whole-release review for ontologies.
- Any Authority-style approval gate before the pilot shows that users want one.

## 9. Pitch implication

OpenMetadata 2.1 (rc1, 2026-10-28) is moving into **governed ontology versioning**: native OWL-style ontologies, immutable releases, review of the whole release, activation and rollback, and an RDF projection into Fuseki. This competes with stetiq's "Ontology Version / Candidate / Promotion" story for anyone who already runs OpenMetadata.

stetiq still has a clear difference:

- **Judged by data, not by a reviewer.** OpenMetadata's gate before a release goes live is a *human approval*. stetiq's is *evidence*: Gates over Evaluator results, Conformance and a classified Ontology Diff, plus Consumer Gates that judge what each Consumer would lose.
- **Observed graph.** stetiq judges against the Observed Schema of the graph an LLM pipeline actually built (ADR 0001, aggregates only). OpenMetadata's releases have no notion of a Construction Run, an Observed Schema or a Consumer.

The pitch should say: "OpenMetadata now versions and approves ontologies; stetiq tells you whether a version is safe to promote for the pipelines and consumers that depend on it." That framing makes OpenMetadata a possible *upstream* of stetiq rather than a substitute.

Under the map's Notes, this belongs on the consolidation map [#135](https://github.com/JoaZaech/stetiq/issues/135) as a positioning note.
