# How OpenMetadata's Incident Manager, Alerts and Announcements work

Research for [#188](https://github.com/JoaZaech/stetiq/issues/188), part of the wayfinder map [#186](https://github.com/JoaZaech/stetiq/issues/186). Terms such as Incident, Alert, Announcement and Task are **OpenMetadata's** here, not stetiq's. Sources were read on 2026-11-02 against OpenMetadata `main` (2.x) and docs v2.0.x.

## Answer in brief

A failing OpenMetadata test produces a server-side, stateful **Incident**: a time series of `New → Ack → Assigned → Resolved` records sharing one `stateId`, mirrored since 2.0 by a first-class **Task** that carries assignees, comments and the workflow. The server opens it when it receives a `Failed` result, auto-assigns it to the test case's owners, infers a severity, and measures time-to-response and time-to-resolution. A person closes it with a required reason and comment (the root cause), or, if the test opts in, a later passing result closes it. **Alerts** are server-side event subscriptions that poll the change-event log and push to Slack, MS Teams, Google Chat, email, webhooks or the activity feed. They can follow lineage to notify downstream owners. **Announcements** are scheduled, hand-written notices on an asset, separate from incidents. Only test *execution* runs at the edge (the Python ingestion framework or any external tool that POSTs results). Everything after the result lands, including state, routing and delivery, runs in the server.

stetiq stops earlier. A red Gate, a failed Consumer Gate or Drift ends in exit code `3` plus a recorded result or Drift event. ADR 0005 leaves routing to the user's scheduler, and no one owns, acknowledges or resolves the finding.

## 1. Where a failure comes from (edge)

- Tests run in the **ingestion framework** (Python, `ingestion/src/metadata/data_quality/`), not in the server. `DataTestsRunner` runs each test through a SQLAlchemy or Pandas interface against the source data, and `MetadataRestSink` posts each result to the test case's `testCaseResult` endpoint. ([Data Quality module deep dive, v1.13](https://docs.open-metadata.org/v1.13.x/developers/contribute/codebase-deep-dives/data-quality))
- Any external tool can do the same by calling `POST /api/v1/dataQuality/testCases/testCaseResults/{fqn}` with `timestamp`, `testCaseStatus` (`Success` / `Failed` / `Aborted`) and `testResultValue`, after the table has been ingested. ([Custom Tests, v2.0](https://docs.open-metadata.org/v2.0.x/how-to-guides/data-quality-observability/quality/custom-tests), [Test Case Results API](https://docs.open-metadata.org/v1.12.x/api-reference/data-quality/test-cases/results))
- Results carry instance-level detail: `passedRows`, `failedRows`, and a *failed rows sample* that the server deletes on the next success ([`TestCaseResultRepository.java`](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-service/src/main/java/org/openmetadata/service/jdbi3/TestCaseResultRepository.java), fields list and `addTestCaseResult`).

## 2. The Incident lifecycle (server)

### Data model

[`tests/testCaseResolutionStatus.json`](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-spec/src/main/resources/json/schema/tests/testCaseResolutionStatus.json) defines the incident as a time-series entity (`EntityTimeSeriesInterface`):

| Field | Meaning |
| --- | --- |
| `testCaseResolutionStatusType` | `New`, `Ack`, `Assigned`, `Resolved` (the only required field) |
| `stateId` | One UUID per failure cycle: "Statuses belonging to the same sequence will have the same ID. Unique across a failure cycle, i.e. new -> ack -> ... -> resolved." |
| `severity` | `Severity1` … `Severity5` |
| `testCaseResolutionStatusDetails` | `oneOf` [`assigned.json`](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-spec/src/main/resources/json/schema/tests/assigned.json) (required `assignee`) or [`resolved.json`](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-spec/src/main/resources/json/schema/tests/resolved.json) (required `testCaseFailureReason` ∈ `FalsePositive`, `MissingData`, `Duplicates`, `OutOfBounds`, `Other`, and required `testCaseFailureComment`; optional `resolvedBy`) |
| `failureSummary` | Text copied from the failed result that opened the incident |
| `metrics` | Name/value pairs: time to response, time to resolution |

### Transitions

All of the following comes from [`TestCaseResultRepository.java`](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-service/src/main/java/org/openmetadata/service/jdbi3/TestCaseResultRepository.java) and [`TestCaseResolutionStatusRepository.java`](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-service/src/main/java/org/openmetadata/service/jdbi3/TestCaseResolutionStatusRepository.java) on `main`.

1. **Open.** When a `Failed` result arrives and is the newest result for the test case, `getOrCreateIncident` returns the open incident Task for that test case or creates one: category `Incident`, type `TestCaseResolution`, named "Incident: <test>". The result is stamped with the incident id. A result older than the newest stored one is treated as history and "must not resolve or open incidents".
2. **Deduplicate.** A further failure while an incident is unresolved does not open a second one: `New` is skipped with "already have unresolved incident". Repeated failures join the same `stateId`.
3. **Auto-assign.** The new Task's assignees are the test case's owners. If there are any, `advanceAutoAssignedIncident` moves the incident straight from `New` to `Assigned`.
4. **Severity.** If no severity is set, `inferIncidentSeverity` runs `LogisticRegressionIncidentSeverityClassifier` over the *tested asset's* Tier, whether it has an owner, its follower count and its vote count. The source says the coefficients "were generated using synthetic data". Users can override the result ([Incident Manager docs](https://docs.open-metadata.org/latest/how-to-guides/data-quality-observability/incident-manager)).
5. **Ack / Assign.** People move the incident through the UI or API. Since 2.0 the Task workflow is the source of truth and the status time series mirrors it ([`IncidentTcrsSyncHandler.java`](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-service/src/main/java/org/openmetadata/service/events/lifecycle/handlers/IncidentTcrsSyncHandler.java)). The workflow allows only reassign or resolve from `Assigned` ([PR #36538](https://github.com/open-metadata/OpenMetadata/pull/36538)). Since 2.0.3 the `EditStatus` permission on `TestCase` covers status, severity and assignment ([Incident Manager docs](https://docs.open-metadata.org/latest/how-to-guides/data-quality-observability/incident-manager)).
6. **Resolve.** Resolving requires a reason and a comment. The docs present the comment as where the root-cause analysis goes ([Incident workflow](https://docs.open-metadata.org/v2.0.x/how-to-guides/data-quality-observability/incident-manager/workflow.md)). On `Resolved` the server records time-to-resolution, measured from the first record of the `stateId`. Time-to-response is measured from `New` to the first non-resolved transition.
7. **Auto-resolve (opt-in, 2.0).** If the test case sets `autoCloseIncident` (default `false`), a later `Success` result resolves the open incident as the governance bot with reason "AutoResolved" ([Breaking changes, Data Quality](https://docs.open-metadata.org/v2.1.x-SNAPSHOT/deployment/upgrade/breaking-changes/data-quality)).
8. **Reopen.** An `Ack`, `Assigned` or `Resolved` record written after a resolved incident reuses its `stateId`, so the timeline stays continuous. A *new failure* always starts a fresh incident.

### History

- The Incident Manager arrived in **1.3**: "summarizes all the test case results with information about the failure severity and resolution flow. Supports assigning a resolution task to the users" ([1.3.0 release](https://github.com/open-metadata/OpenMetadata/releases/tag/1.3.0-release)).
- In **2.0** incidents moved from feed threads (`thread_entity`, `type=Task`) onto a first-class Task entity (`task_entity`, `/v1/tasks`). The status time series "is unchanged". `incidentStatus` is now inlined on each TestCase ([Breaking changes, Data Quality](https://docs.open-metadata.org/v2.1.x-SNAPSHOT/deployment/upgrade/breaking-changes/data-quality)). On `main`, [`thread.json`](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-spec/src/main/resources/json/schema/entity/feed/thread.json)'s `threadType` is now only `Conversation`, `Announcement`, `Chatbot`.
- Comments on an incident are posts on its thread (`POST /api/v1/feed/{threadId}/posts`). The Incident tab shows the timeline, the root-cause analysis and the closure ([Incident workflow](https://docs.open-metadata.org/v2.0.x/how-to-guides/data-quality-observability/incident-manager/workflow.md)).

## 3. Alerts (server)

Source: [`events/eventSubscription.json`](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-spec/src/main/resources/json/schema/events/eventSubscription.json) and the [Alert Behavior Reference](https://docs.open-metadata.org/v2.0.x/how-to-guides/data-quality-observability/alerts-notifications/alert-behavior-reference.md).

- **Mechanism.** An alert is an `EventSubscription` that the server runs. It reads the change-event log on its own poll (`pollInterval` defaults to 60 s in the schema; the docs say 10 s when created through the API without one) and keeps its own offset. It does not replay events from before it was created.
- **Kinds** (`alertType`): `Notification`, `Observability`, `ActivityFeed`, `GovernanceWorkflowChangeEvent`, `Custom`. Observability alerts have **triggers**: Schema Changes, Metric Updates, Pipeline Status, Ingestion Pipeline Status, Test Case Status, Test Case Status Under Suite, Test Suite Status, Data Contract Status. Notification alerts (28 sources) have **filters** only.
- **Incidents route through Notification alerts, not Observability.** "Incidents are covered by Notification alerts only": use the Task source (or All). The Task source also fires for description, tag and approval requests and "can't be filtered to incidents only". A *failed test* (Observability, Test Case Status) and its *incident's progress* (Notification, Task) are therefore two separate alerts.
- **Destinations** (`subscriptionType`): `Webhook`, `Slack`, `MsTeams`, `GChat`, `Email`, `ActivityFeed`, `GovernanceWorkflowChangeEvent`. Recipients (`subscriptionCategory`) are `Users`, `Teams`, `Admins`, `Assignees`, `Owners`, `Mentions`, `Followers`, `External`.
- **Lineage fan-out.** A destination can set `notifyDownstream: true` with an optional `downstreamDepth`: "notifications will traverse lineage to include stakeholders of entities that consume data from the affected entity" (default `false`).
- **Delivery.** `batchSize` defaults to 100 and `retries` to 3 in the schema, but the docs say "OpenMetadata doesn't currently redeliver a failed event automatically": a failed delivery is recorded and skipped, and order within a batch is not guaranteed. Change events and delivery records are kept for 7 days by default. A destination's status is `active`, `awaitingRetry`, `retryLimitReached`, `failed` or `disabled`.

## 4. Announcements and the activity feed

- An **Announcement** is a thread of type `Announcement` on one data asset. It has a Markdown `description` and a required `startTime`/`endTime` window ([`thread.json`](https://github.com/open-metadata/OpenMetadata/blob/main/openmetadata-spec/src/main/resources/json/schema/entity/feed/thread.json) `announcementDetails`). It is written by hand to warn of "deprecation, deletion, or schema changes". It shows as a banner on the asset page, at the top right of the landing page and in the activity feed, and followers are notified ([Announcements](https://docs.open-metadata.org/latest/how-to-guides/guide-for-data-users/announcements)).
- Announcements are not tied to incidents or lineage. As a Notification alert source they support no filters ([Alert Behavior Reference](https://docs.open-metadata.org/v2.0.x/how-to-guides/data-quality-observability/alerts-notifications/alert-behavior-reference.md)).
- The **activity feed** is the in-app destination. Incidents, announcements and conversations all appear there for owners and followers.

## 5. Server vs edge

| Step | OpenMetadata | stetiq today |
| --- | --- | --- |
| Run the check | Edge: ingestion framework or external tool, against the source data | Edge: `stetiq gate`, `stetiq consumer gate`, `stetiq observe` in the user's CI or scheduler. The core judges artifacts, and the SDK runs Competency Questions in the user's process (ADR 0005) |
| Record the result | Server: `testCaseResult` time series, including failed-row samples | Server: Gate results, Consumer Gate verdicts, Observations and Drift events. No instance data (ADR 0001) |
| Open, deduplicate, own, prioritise the finding | Server: Incident and Task, `stateId`, owners auto-assigned, severity inferred | **None.** A Drift event is a record with no state, owner or resolution |
| Resolve with a reason | Server: required reason enum and comment, time-to-resolve | **None** |
| Route to people | Server: EventSubscription polls and pushes to Slack, Teams, GChat, email or webhook, with lineage fan-out | **Edge only.** Exit code `3` vs `1` lets "cron, Airflow task or CI step … tell the two apart" ([CLI guide](../guide/04-cli.md)). Routing Drift events belongs to the user's scheduler (ADR 0005). Signed webhooks, Slack and GitHub-issue Connectors for Consumer impact are **planned, not built** ([vision](../vision.md#connector), [Consumer Connector spec](../specs/consumer-connector.md)) |
| Announce a planned change | Server: hand-written Announcement with a time window | Planned: Consumer impact events on `promotion`/`candidate`, computed from the Ontology Diff, not hand-written |

## 6. Implications for stetiq (for #186, not decisions)

- **Incident state is the clearest missing concept.** stetiq records findings but has no lifecycle. A minimal borrow fits ADR 0005: a `stateId`-style grouping of consecutive Drift events, or of failing Consumer Gate verdicts, plus an `acknowledged` / `resolved` record with a reason enum. It is a computation over records stetiq already holds, needs no network reach, and the auto-resolve rule ("next passing Observation closes it") needs no clock, much as Pending Migration's grace period is judged from Observation timestamps. OpenMetadata's reason enum (`FalsePositive`, `MissingData`, `Duplicates`, `OutOfBounds`) is row-oriented. stetiq's equivalents would be structural, for example *expected / Pending Migration*, *Adoption needed*, *extraction regression*, *false positive*.
- **Server-side push delivery conflicts with ADR 0005** as OpenMetadata builds it, with the server polling events and calling Slack and webhooks. The planned Consumer Connector spec already describes stetiq POSTing signed webhooks, which is outbound reach from the core, so whoever specs it should check it against ADR 0005. The pull variant (`stetiq consumer events`) fits ADR 0005 cleanly.
- **Severity by asset popularity does not transfer.** OpenMetadata infers severity from Tier, owner, followers and votes, using a model trained on synthetic data. stetiq already has a better signal: Consumer impact levels (`affected` / `will_be_affected` / `unknown`) reached through Task → Consumer.
- **Announcements are a weaker form of stetiq's planned Consumer impact events**: hand-written, with no link to the change that caused them.

## Positioning notes (for the consolidation map #135)

- OpenMetadata's `notifyDownstream` sends a failed test or schema change along **lineage** to downstream owners. That is the closest OpenMetadata comes to "tell the Consumer when upstream changes hurt it", and a pitch should name the difference. OpenMetadata notifies by *who sits downstream in lineage*. stetiq judges *whether this Consumer's Tasks and Competency Questions lose answers* (Consumer Gate, Consumer impact), before the change merges, over the ontology rather than rows.
- OpenMetadata has a **Data Contract Status** Observability trigger, so contract failures are alertable there. The overlap between Data Contracts and the Consumer Gate is covered by its own ticket. This note only records that OpenMetadata alerts on contract status out of the box, which stetiq does not.
- OpenMetadata's incident loop runs on row-level failures and keeps failed-row samples. stetiq cannot copy that part (ADR 0001), and "no instance data leaves your process" is itself a positioning point.

## Open questions

- Whether `notifyDownstream` reaches beyond tables and dashboards, for example to ML models or API consumers, was not checked.
- Incident behaviour before 2.0 (1.3–1.x feed-thread tasks) was taken from the release notes and the breaking-changes page, not from older source code.
- The docs' 10 s default poll and the schema's 60 s default disagree. The difference does not matter here.
