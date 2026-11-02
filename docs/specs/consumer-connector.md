# Consumer Connector spec

> **Mostly not implemented.** This is a planned integration contract, written so a later team can build it. What has shipped is the **Consumer Gate** itself: Consumer Gates declared on each Consumer in the Use Case, the one kind `row_count_drop`, the verdict route and `stetiq consumer gate`, described in [Asking for a verdict](#asking-for-a-verdict) as they are built. The events, their payload, their delivery and `stetiq consumer events` do not exist yet, and their names may change when they are built. The reasons for it are in [the vision](../vision.md).

A **Connector** sits at a **Consumer**'s edge and links it to stetiq. Through it the Consumer learns of Ontology changes that affect its **Tasks**, and enforces its **Consumer Gate**. This page specifies the contract between stetiq and a Connector: which events stetiq emits, what they carry, how a Connector receives them, and how it asks for a Consumer Gate verdict. Terms in **bold** are defined in [GLOSSARY.md](../../GLOSSARY.md).

## Ground rules

These follow from [ADR 0001](../adr/0001-ontology-not-instance-data.md) and [ADR 0005](../adr/0005-core-computes-over-artifacts-connectors-and-monitoring-live-at-the-edge.md), and any implementation must keep them:

- **The core never connects to a Consumer.** It computes events and verdicts over artifacts it already holds (Ontology Versions, Ontology Diffs, Use Case Versions, Observed Schemas, Evaluator results). Delivering an event and acting on a verdict happen at the edge, in code the Consumer runs.
- **No instance data, ever.** Events and verdicts carry Concepts, change classes, statistics and pass/fail results, never values from the graph. Executed Competency Question results arrive as they do today: the SDK runs the query in the user's process, judges the rows and drops them, and only the result reaches stetiq.
- **stetiq evaluates; whoever checks the verdict enforces.** Nothing in stetiq blocks a Consumer from taking an Ontology Version, just as Gates do not block a Promotion. Today the upstream pipeline's CI enforces a Consumer Gate before a change merges (`stetiq consumer gate`); a Connector will also enforce it before the Consumer takes a version.
- **Consumers are identified by their Use Case id.** A Connector is set up for one Consumer of one **Knowledge Graph**, named by the Consumer's `id` in the **Use Case**, which is stable across **Use Case Versions**.

## Events

stetiq emits an event when an Ontology change reaches at least one Consumer's Tasks. Consumer impact decides which Consumers that is: it follows each change in the **Ontology Diff** through Concept → Competency Question → Task → Consumer, and gives each Task a level:

| Level | Cause |
| --- | --- |
| `affected` | A breaking change removes or changes a Concept one of the Task's Competency Questions needs. |
| `will_be_affected` | A deprecating change marks such a Concept as deprecated. |
| `unknown` | A Competency Question only the question mapper could map onto the Ontology, so stetiq cannot tell. It is never reported as unaffected. |

Cosmetic and additive changes affect no Task, so on their own they emit nothing.

| Event | When | Diff |
| --- | --- | --- |
| `promotion` | A **Promotion** moves the **Contract Alias** to an Ontology Version, including a rollback to an earlier one. | From the version the Contract Alias pointed to before, to the version it points to now. |
| `candidate` | A new **Candidate** is registered whose Diff has a breaking or deprecating change. This gives Consumers warning before any Promotion. | From the Contract Alias's version to the Candidate. |

A Promotion of an Alias other than the Contract Alias (for example `staging`) emits nothing by default. A Connector may opt in to other Aliases, in which case `alias` in the payload names them.

Each event is sent once per affected Consumer, carrying only that Consumer's Tasks. A Consumer never sees another Consumer's Tasks.

## Payload

Every event is one JSON object. The example is a `promotion` that moves `production` from Ontology Version 5 to 6 in `plant-kg`, as the Consumer `maintenance-planner` receives it.

```json
{
  "spec_version": 1,
  "event": "promotion",
  "event_id": "8f3c2a1e-4b7d-4e19-9a0c-2d5e6f7a8b9c",
  "occurred_at": "2026-11-03T09:14:22Z",
  "knowledge_graph": "plant-kg",
  "alias": "production",
  "base_version": 5,
  "target_version": 6,
  "use_case_version": 4,
  "actor": "j.doe",
  "gate_result": { "passed": true, "recorded_at": "2026-11-03T08:52:10Z" },
  "consumer": {
    "id": "maintenance-planner",
    "name": "Maintenance planner",
    "kind": "application",
    "level": "affected",
    "tasks": [
      {
        "id": "triage-breakdowns",
        "level": "affected",
        "competency_questions": [
          {
            "id": "cq-open-workorders-per-machine",
            "level": "affected",
            "changes": [
              {
                "class": "breaking",
                "kind": "relation",
                "concept": "PERFORMED_ON",
                "summary": "Relation PERFORMED_ON removed"
              }
            ]
          },
          {
            "id": "cq-workorder-status",
            "level": "will_be_affected",
            "changes": [
              {
                "class": "deprecating",
                "kind": "attribute",
                "concept": "WorkOrder.state",
                "replaced_by": "WorkOrder.status",
                "summary": "Attribute WorkOrder.state deprecated, replaced by WorkOrder.status"
              }
            ]
          }
        ]
      },
      {
        "id": "plan-spare-parts",
        "level": "unknown",
        "competency_questions": [
          { "id": "cq-parts-at-risk", "level": "unknown", "changes": [] }
        ]
      }
    ]
  },
  "links": {
    "ontology_diff": "https://stetiq.example.com/ui/knowledge-graphs/plant-kg/diff?base=5&target=6",
    "verdict": "https://stetiq.example.com/api/v1/knowledge-graphs/plant-kg/consumer-gate-results?consumer=maintenance-planner"
  }
}
```

| Field | Meaning |
| --- | --- |
| `spec_version` | The version of this contract. Additive fields keep the number; anything else bumps it. |
| `event` | `promotion` or `candidate`. |
| `event_id` | Unique per event and Consumer. A Connector uses it to drop duplicates, because delivery is at least once. |
| `knowledge_graph` | The Knowledge Graph's name. |
| `alias` | The Alias that moved (`promotion`), or the Contract Alias the Candidate is compared with (`candidate`). |
| `base_version`, `target_version` | The two Ontology Versions the Diff is between. For a rollback, `target_version` is lower than `base_version`. |
| `use_case_version` | The Use Case Version whose Consumers, Tasks and Competency Questions the impact was computed against. |
| `actor` | Who promoted (the API Token's user, as in the audit log). Absent for `candidate`. |
| `gate_result` | Whether the target version's latest recorded **Gate** result passed, as the Promotion audit records it. Absent if it has none. |
| `consumer` | The receiving Consumer, its overall `level` (the most severe of its Tasks), and its affected Tasks only. |
| `tasks[].competency_questions[].changes[]` | Each Ontology Diff change behind that question's level, with its `class` (`cosmetic`, `additive`, `deprecating`, `breaking`), the `kind` of Concept (`class`, `relation`, `attribute`, `vocabulary_value`) and the Concept's label, plus `replaced_by` when a Deprecation names one. `summary` is for people; no code may parse it. |
| `links` | Where a person can see the Diff, and where the Connector asks for a verdict. |

## Delivery

A Connector receives events in one of two ways. Both run at the edge.

### Webhook

stetiq sends each event as an HTTP `POST` with `Content-Type: application/json` to a URL registered for the Consumer.

- **Signed.** The body is signed with HMAC-SHA256 under a secret shared at registration, sent as `X-Stetiq-Signature: sha256=<hex>`, with `X-Stetiq-Event` and `X-Stetiq-Event-Id` headers. The receiver rejects a request whose signature does not match.
- **At least once.** A response other than 2xx is retried with backoff for 24 hours. The receiver deduplicates on `event_id`.
- **Fire and forget for stetiq.** A failed delivery never fails, delays or rolls back the Promotion or the Candidate. It is recorded and shown on the Consumer's card.
- **Registration.** A person with *edit* permission on the Knowledge Graph registers the URL and secret for a Consumer id. The URL is stored with the Knowledge Graph, not in the Use Case, so changing it does not create a Use Case Version.

Sending an outbound HTTP request is the one network action this adds to the core. It reaches only a URL the Consumer's team registered, carries only the payload above, and never reads anything back, so it does not reopen ADR 0005's question of server-owned connectors to graph databases. A team that wants the core to make no outbound call at all uses the CI check instead.

### CI check in the Consumer's repository

The Consumer's repository runs a check on a schedule or on each change, which pulls instead of being pushed to:

```bash
stetiq consumer events plant-kg --consumer maintenance-planner --since <event_id>
stetiq consumer gate plant-kg --consumer maintenance-planner --version 6
```

`consumer events` (planned) prints the events for that Consumer since the given one, as the JSON above, and exits 3 if any has level `affected`. `consumer gate` (built) asks for a verdict (below) and exits 3 if a Consumer Gate fails, as `stetiq gate` does. The check can then open an issue in the Consumer's repository or fail the pull request that bumps the Ontology Version the Consumer pins.

`consumer events` needs only *read* permission. `consumer gate` records its verdict, so it needs *edit*, as `stetiq gate` does; a Consumer's CI that should hold only a read token reads recorded verdicts with `stetiq consumer gate-results` instead.

## Asking for a verdict

"Is the next version safe for this Consumer?" stetiq answers by evaluating the Consumer's Consumer Gates against a **Candidate** Construction Run and recording the verdict. This part is built.

### Where Consumer Gates live

Consumer Gates are declared on the Consumer in the **Use Case** (`consumer_gates` in `use-case.yaml`), not in the Consumer's repository `stetiq.yaml`, and they are versioned with the **Use Case Version** ([ADR 0008](../adr/0008-consumer-gates-are-declared-in-the-use-case.md)). The Consumer's team still owns what "safe" means for it, a newly declared Consumer is gated without changing the pipeline's CI, and the server holds both the definitions and the inputs, so the verdicts it records are its own.

```yaml
consumers:
  - id: maintenance-planner
    name: Maintenance planner
    tasks:
      - id: triage-breakdowns
        description: Triage breakdowns
        competency_questions: [cq-open-workorders-per-machine, cq-workorder-status]
    consumer_gates:
      - name: triage-rows-hold      # optional; defaults to the check
        check: row_count_drop
        task: triage-breakdowns     # one of this Consumer's Tasks
        max_drop: 0.10              # fraction 0-1
```

`row_count_drop` is the one kind built: for each Competency Question of `task`, the executed row count on the Candidate run may not drop by more than `max_drop` from the baseline's. These kinds stay planned, and naming one says so:

| Check | Would judge |
| --- | --- |
| `consumer_impact` | The Consumer impact level of the Ontology Diff, e.g. `max_level: will_be_affected`. |
| `task_questions` | The pass ratio of a Task's executed Competency Questions. |
| `conformance` | The Candidate run's Conformance score. |
| `observed_count` | A Class's or Relation's count in the Observed Schema. |
| `fill_rate` | An Attribute's fill rate in the Observed Schema. |

Every Consumer Gate reads only the inputs the glossary allows: **Observed Schema** statistics, **Conformance**, the Ontology Diff, and executed Competency Question results. None reads instance data: `row_count_drop` reads the row counts the SDK recorded when it executed the questions in the user's process.

### The baseline

A Consumer Gate judges what the Consumer would lose against the Ontology Version it takes. Until a Connector can say which version that is, it is the **Contract Alias**'s: the baseline is the latest finished Construction Run, other than the Candidate, standing for the Contract Alias's version (a run stands for its Candidate version, or else for the version it consumed). With no baseline run, every Consumer Gate fails. A Competency Question that was not in the Use Case Version the baseline run was judged by (declared since) is new: it has no baseline, so it is listed in the outcome's `new_questions` and a reason, and it is not compared and fails nothing. A question that was in that Use Case Version but has no row count on the baseline still fails. A Consumer that pins its own version needs a Connector, which is planned.

### The request

The request names the Candidate and, optionally, one Consumer. It carries no definitions and no outcomes: the server reads the Consumer Gates from its latest stored Use Case Version and the row counts from its stored `competency_question_execution` results, so a client cannot weaken a rule or send a passing verdict. A body with any other field is refused.

```http
POST /api/v1/knowledge-graphs/plant-kg/consumer-gate-results
Authorization: Bearer <edit token>
Content-Type: application/json

{ "run": "81a4c0e2f3b5d6e7f8a9b0c1d2e3f4a5", "consumer": "maintenance-planner" }
```

`run` names a finished Construction Run of that Knowledge Graph; `version` instead takes the latest finished run standing for that Ontology Version; neither takes the latest finished run. `run` and `version` together are refused (422). Without `consumer`, every Consumer that declares a Consumer Gate is evaluated. The response holds one recorded result per evaluated Consumer:

```json
[
  {
    "knowledge_graph": "plant-kg",
    "consumer": "maintenance-planner",
    "use_case_version": 4,
    "run_id": "81a4c0e2f3b5d6e7f8a9b0c1d2e3f4a5",
    "ontology_version": 6,
    "baseline_run_id": "5d0c1f2e9a7b4c3d8e6f1a2b3c4d5e6f",
    "baseline_ontology_version": 5,
    "passed": false,
    "outcomes": [
      {
        "gate": { "name": "triage-rows-hold", "check": "row_count_drop",
                  "task": "triage-breakdowns", "max_drop": 0.1 },
        "passed": false,
        "reasons": ["triage-breakdowns / cq-open-workorders-per-machine: 5 → 2 rows (−60.0%, limit −10%)"],
        "findings": [
          { "task": "triage-breakdowns", "competency_question": "cq-open-workorders-per-machine",
            "before": 5, "after": 2, "change": -0.6, "limit": 0.1 }
        ],
        "new_questions": []
      }
    ],
    "evaluated_at": "2026-11-03T09:20:05Z"
  }
]
```

`findings` lists each failing question as fields: the counts and relative `change`, or, when it could not be compared, `missing` (`no_baseline_run`, `baseline_missing`, `baseline_error`, `candidate_missing`, `candidate_error`) with whichever counts exist. `new_questions` lists the Task's questions that are new since the baseline run's Use Case Version and were not compared. Code reads `findings` and `new_questions`; `reasons` is for people and no code may parse it. A verdict names the symptom, never a cause ([ADR 0001](../adr/0001-ontology-not-instance-data.md)).

`GET` on the same path (needs *read*) lists recorded results oldest first, filtered by `?consumer=` and `?version=` (the Ontology Version the judged run stands for). The web UI shows a Consumer's latest one on its card. A verdict never changes an Alias and never feeds the Promotion audit, which only counts Gate results.

A Consumer Gate fails if its input is missing, for example a question with no row count on either run. A missing input is never read as a pass.

## Open questions for whoever builds this

- Whether a Consumer may have several Connectors (one webhook and one CI check, say), or exactly one.
- How long stetiq keeps events for `consumer events` to pull.
- Whether a Gate over Consumer impact on the upstream side (in the vision) and the `consumer_impact` Consumer Gate should share one implementation; they read the same computation from opposite ends.
