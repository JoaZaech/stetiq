# Consumer Connector spec

> **Not implemented.** This is a planned integration contract, written so a later team can build it. No event, route, command or file format on this page exists in stetiq yet, and the names may change when it is built. The reasons for it are in [the vision](../vision.md).

A **Connector** sits at a **Consumer**'s edge and links it to stetiq. Through it the Consumer learns of Ontology changes that affect its **Tasks**, and enforces its **Consumer Gate**. This page specifies the contract between stetiq and a Connector: which events stetiq emits, what they carry, how a Connector receives them, and how it asks for a Consumer Gate verdict. Terms in **bold** are defined in [GLOSSARY.md](../../GLOSSARY.md).

## Ground rules

These follow from [ADR 0001](../adr/0001-ontology-not-instance-data.md) and [ADR 0005](../adr/0005-core-computes-over-artifacts-connectors-and-monitoring-live-at-the-edge.md), and any implementation must keep them:

- **The core never connects to a Consumer.** It computes events and verdicts over artifacts it already holds (Ontology Versions, Ontology Diffs, Use Case Versions, Observed Schemas, Evaluator results). Delivering an event and acting on a verdict happen at the edge, in code the Consumer runs.
- **No instance data, ever.** Events and verdicts carry Concepts, change classes, statistics and pass/fail results, never values from the graph. Executed Competency Question results arrive as they do today: the SDK runs the query in the user's process, judges the rows and drops them, and only the result reaches stetiq.
- **stetiq evaluates, the Connector enforces.** Nothing in stetiq blocks a Consumer from taking an Ontology Version, just as Gates do not block a Promotion.
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
    "verdict": "https://stetiq.example.com/api/v1/knowledge-graphs/plant-kg/consumers/maintenance-planner/consumer-gate-results"
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

`consumer events` prints the events for that Consumer since the given one, as the JSON above, and exits 3 if any has level `affected`. `consumer gate` asks for a verdict (below) and exits 3 if a Consumer Gate fails, as `stetiq gate` does today. The check can then open an issue in the Consumer's repository or fail the pull request that bumps the Ontology Version the Consumer pins.

Both commands need only *read* permission, so the Consumer's CI holds a read API Token.

## Asking for a verdict

Before a Consumer takes an Ontology Version, its Connector asks: "is version 6 safe for me?". stetiq answers by evaluating the Consumer's Consumer Gates against that version.

### Where Consumer Gates live

Like Gates, Consumer Gates are defined in the **Consumer's** repository, not in stetiq, so the team that depends on the Knowledge Graph owns what "safe" means for it. A `consumer_gates` list in that repository's `stetiq.yaml` reuses the existing Gate kinds and adds two that read Consumer impact and executed Competency Questions:

```yaml
knowledge_graph: plant-kg
consumer: maintenance-planner
consumer_gates:
  - check: consumer_impact
    max_level: will_be_affected   # fail on any `affected` Task
  - name: triage-questions-pass
    check: task_questions
    task: triage-breakdowns
    min_pass_ratio: 1.0           # executed Competency Question results
  - check: conformance
    min_score: 0.95
  - name: workorders-present
    check: observed_count
    concept: WorkOrder
    min: 1000
  - name: status-filled
    check: fill_rate
    concept: WorkOrder.status
    min: 0.95
```

Every Consumer Gate reads only the inputs the glossary allows: **Observed Schema** statistics, **Conformance**, the Ontology Diff, and executed Competency Question results. None reads instance data.

### The request

The Connector sends the definitions, and the server gathers the inputs and computes every outcome, exactly as `POST …/gate-results` works for Gates today:

```http
POST /api/v1/knowledge-graphs/plant-kg/consumers/maintenance-planner/consumer-gate-results
Authorization: Bearer <read token>
Content-Type: application/json

{
  "version": 6,
  "base_version": 5,
  "consumer_gates": [
    { "check": "consumer_impact", "max_level": "will_be_affected" },
    { "name": "triage-questions-pass", "check": "task_questions",
      "task": "triage-breakdowns", "min_pass_ratio": 1.0 }
  ]
}
```

`base_version` is the version the Consumer uses now. If it is left out, it defaults to the version the Contract Alias pointed to before the target version was promoted, or to the Contract Alias's current version for a Candidate. The Use Case Version is the latest one.

```json
{
  "knowledge_graph": "plant-kg",
  "consumer": "maintenance-planner",
  "version": 6,
  "base_version": 5,
  "use_case_version": 4,
  "passed": false,
  "outcomes": [
    {
      "name": "consumer_impact",
      "passed": false,
      "reasons": ["Task triage-breakdowns is affected: Relation PERFORMED_ON removed"]
    },
    {
      "name": "triage-questions-pass",
      "passed": true,
      "reasons": []
    }
  ],
  "recorded_at": "2026-11-03T09:20:05Z"
}
```

The verdict is recorded against the Consumer and the Ontology Version, so the Consumer's card can show "version 6: Consumer Gate failed". It never changes an Alias and never feeds the Promotion audit, which only counts Gate results.

A Consumer Gate fails if its input is missing, for example `task_questions` when no Construction Run on the target version has executed that Task's Competency Questions. A missing input is never read as a pass.

## Open questions for whoever builds this

- Whether a Consumer may have several Connectors (one webhook and one CI check, say), or exactly one.
- How long stetiq keeps events for `consumer events` to pull.
- Whether a Gate over Consumer impact on the upstream side (in the vision) and the `consumer_impact` Consumer Gate should share one implementation; they read the same computation from opposite ends.
