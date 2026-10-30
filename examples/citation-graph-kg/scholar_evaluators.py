"""The research office's own Evaluator, registered on the stetiq Clients.

It runs in the SDK process (next to the Graph Source); only its metrics reach the
server, where the `no-duplicate-authors` Gate in stetiq.yaml reads them.
"""

from __future__ import annotations

from scholar_graph import AUTHOR_COUNT, DUPLICATE_AUTHORS

from stetiq import ConstructionRunEvaluator, Evaluation


class AuthorDedupe(ConstructionRunEvaluator):
    """Did the loader create one Author node per person?

    Two Author nodes whose names agree once accents, hyphens and case are stripped are
    almost certainly the same person spelled two ways (the publication database versus
    the ORCID sync). Metrics: `authors` (Author nodes), `duplicate_groups` (normalised
    names with more than one node) and `duplicate_authors` (nodes beyond the first in
    each group, what the Gate caps at 0). Aggregates only (ADR 0001): both queries
    count in the Graph Source and no name leaves it.
    """

    name = "author_dedupe"

    def evaluate(self, run) -> Evaluation:
        [total] = run.graph_source.execute_read(AUTHOR_COUNT)
        [duplicates] = run.graph_source.execute_read(DUPLICATE_AUTHORS)
        return Evaluation(
            metrics={
                "authors": total["authors"],
                "duplicate_groups": duplicates["duplicate_groups"],
                "duplicate_authors": duplicates["duplicate_authors"],
            }
        )
