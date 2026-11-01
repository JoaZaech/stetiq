# Consumer Gates are declared in the Use Case and evaluated by the server against the Contract Alias baseline

A Consumer Gate is a rule one Consumer sets for taking a new Ontology Version. We declare it on that Consumer in the Use Case (`consumer_gates` in `use-case.yaml`), versioned with the Use Case Version, and the server evaluates it against the latest finished Construction Run on the Contract Alias's version. The Consumer's team owns what "safe" means for it, because the rule sits on its own Consumer. A newly declared Consumer is gated as soon as its Use Case Version is registered, without anyone editing the upstream pipeline's CI, because `stetiq consumer gate` evaluates every Consumer the latest Use Case Version declares. And the server already holds both the definitions (the stored Use Case Version) and the inputs (the row counts `competency_question_execution` recorded per run), so a client only names the run to judge and cannot send a weaker rule or a passing verdict; the verdict the server records is its own. Gates are the contrast: their definitions live in the repository's `stetiq.yaml`, which the server never reads, and arrive with each request (see ADR 0007's context). This reverses the Consumer Connector spec's earlier placement of Consumer Gates in the Consumer's repository `stetiq.yaml`.

## Considered Options

- **In the Consumer's repository `stetiq.yaml`, sent with each verdict request** (the Connector spec's first draft). Rejected: it needs a Connector or the Consumer's own CI before any Consumer is gated, the pipeline's CI could not see the rules, and the server would record verdicts over definitions it took on the client's word.
- **In the upstream pipeline's `stetiq.yaml`, beside its Gates.** Rejected: the pipeline's team would own every Consumer's rules, and each new Consumer would mean a change to the pipeline's repository.

## Consequences

- Changing a Consumer's Consumer Gates yields a new Use Case Version, like any other Consumer change, and each verdict records the Use Case Version it was judged by. A Use Case without Consumer Gates keeps its content hash.
- The baseline is the Contract Alias's version for every Consumer. A Consumer that pins a version of its own needs a Connector to say which, which is planned.
- Consumer Gate verdicts never feed the Promotion audit or move an Alias: Promotion keeps trusting only Gate results.
- Evaluation needs *edit*, because it records; listing verdicts needs *read*.
