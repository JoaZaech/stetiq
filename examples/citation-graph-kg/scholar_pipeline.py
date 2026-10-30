"""Builds scholar-kg from the university's research-output data.

Sources, under data/:

| Source            | Gives                                                            |
| ----------------- | ---------------------------------------------------------------- |
| papers.json       | Paper, AUTHORED, PUBLISHED_IN, FUNDED_BY                         |
| authors.csv       | Author (name, department)                                        |
| venues.csv        | Venue (name, kind)                                               |
| grants.csv        | Grant (id, title, funder)                                        |
| citations.csv     | CITES                                                            |
| orcid-sync.json   | Author.orcid, and the ORCID registry's own spelling of each name |

The loader is driven by the Declared Ontology stetiq hands the run: it derives
CO_AUTHORED edges only when the Ontology declares that relationship type, and labels a
Venue with its kind (Journal, Conference) only when the Ontology declares that subtype.
Author.orcid and Grant.funder are always written: the sync and the funder column are
there, whether or not the Ontology knows about them yet.

How an ORCID record finds its Author decides whether the graph has duplicate people:

- by name (default): a record whose name is spelled exactly as in authors.csv gets its
  ORCID iD; any other record becomes a new Author node with the ORCID spelling, linked
  to the record's works. Two records are spelled differently, so two people end up twice.
- `--merge-by-orcid`: a record with works is matched to the Author who wrote most of
  them, whatever the spelling (a record without works still goes by name); no record
  creates a node.

Run it as the Construction Entry Point (see stetiq.yaml):

    python scholar_pipeline.py --ontology declared.yaml --scope '{"database": "scholar"}' --merge-by-orcid

Environment: SCHOLAR_GRAPH_FILE, where the local graph file lives.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scholar_graph import DEFAULT_DATABASE, ScholarGraph, clean_name

from stetiq.ontology import Ontology, parse_yaml

EXAMPLE_DIR = Path(__file__).resolve().parent
DATA_DIR = EXAMPLE_DIR / "data"
DEFAULT_GRAPH_FILE = EXAMPLE_DIR / ".graphdb" / "scholar.json"


@dataclass(frozen=True)
class Sources:
    papers: list[dict[str, Any]]
    authors: list[dict[str, str]]
    venues: list[dict[str, str]]
    grants: list[dict[str, str]]
    citations: list[dict[str, str]]
    orcid_records: list[dict[str, Any]]


def load_sources(data_dir: Path = DATA_DIR) -> Sources:
    return Sources(
        papers=json.loads((data_dir / "papers.json").read_text(encoding="utf-8")),
        authors=_csv(data_dir / "authors.csv"),
        venues=_csv(data_dir / "venues.csv"),
        grants=_csv(data_dir / "grants.csv"),
        citations=_csv(data_dir / "citations.csv"),
        orcid_records=json.loads((data_dir / "orcid-sync.json").read_text(encoding="utf-8"))[
            "records"
        ],
    )


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@dataclass(frozen=True)
class BuildStats:
    nodes: int
    relationships: int
    orcid_matched: int  # ORCID records attached to an existing Author
    orcid_added: int  # ORCID records that became a new Author node
    co_authored: int  # CO_AUTHORED edges written (0 unless the Ontology declares it)


def build(
    graph: ScholarGraph,
    *,
    ontology: Ontology,
    merge_by_orcid: bool = False,
    data_dir: Path = DATA_DIR,
    database: str = DEFAULT_DATABASE,
) -> BuildStats:
    """Rebuild `database` in `graph` from the data, guided by the Declared Ontology."""
    src = load_sources(data_dir)
    declared_relationships = {r.label for r in ontology.relationship_types}
    venue_subtypes = {n.label for n in ontology.node_types if n.parent == "Venue"}
    graph.clear(database)
    relationships = 0

    venues = {
        v["venue_id"]: graph.add_node(
            ["Venue", *([v["kind"]] if v["kind"] in venue_subtypes else [])],
            {"name": v["name"], "kind": v["kind"]},
            database=database,
        )
        for v in src.venues
    }
    grants = {
        g["grant_id"]: graph.add_node(
            ["Grant"],
            {"id": g["grant_id"], "title": g["title"], "funder": g["funder"]},
            database=database,
        )
        for g in src.grants
    }
    authors = {
        a["author_id"]: graph.add_node(
            ["Author"], {"name": a["name"], "department": a["department"]}, database=database
        )
        for a in src.authors
    }
    papers: dict[str, int] = {}
    paper_authors: dict[str, list[str]] = {}
    for p in src.papers:
        papers[p["doi"]] = graph.add_node(
            ["Paper"],
            {
                "doi": p["doi"],
                "title": p["title"],
                "year": int(p["year"]),
                "abstract": p["abstract"],
            },
            database=database,
        )
        paper_authors[p["doi"]] = list(p["authors"])
        graph.add_relationship(papers[p["doi"]], "PUBLISHED_IN", venues[p["venue_id"]])
        relationships += 1
        for grant_id in p["grants"]:
            graph.add_relationship(papers[p["doi"]], "FUNDED_BY", grants[grant_id])
            relationships += 1
        for author_id in p["authors"]:
            graph.add_relationship(authors[author_id], "AUTHORED", papers[p["doi"]])
            relationships += 1
    for c in src.citations:
        graph.add_relationship(papers[c["citing_doi"]], "CITES", papers[c["cited_doi"]])
        relationships += 1

    # The ORCID sync: attach each record's ORCID iD to an Author.
    by_name = {a["name"]: a["author_id"] for a in src.authors}
    name_of = {a["author_id"]: a["name"] for a in src.authors}
    works_of = {
        a["author_id"]: {doi for doi, ids in paper_authors.items() if a["author_id"] in ids}
        for a in src.authors
    }
    matched = added = 0
    for record in src.orcid_records:
        works = set(record["works"])
        author_id = by_name.get(record["name"])
        if merge_by_orcid and works:
            # Who wrote most of this record's works? Ties go to the author whose name
            # normalises to the record's spelling, then to the lower author id.
            author_id = min(
                works_of,
                key=lambda a, works=works: (
                    -len(works & works_of[a]),
                    clean_name(name_of[a]) != clean_name(record["name"]),
                    a,
                ),
            )
        if author_id is not None:
            graph.set_property(authors[author_id], "orcid", record["orcid"])
            matched += 1
        else:
            node = graph.add_node(
                ["Author"], {"name": record["name"], "orcid": record["orcid"]}, database=database
            )
            added += 1
            for doi in sorted(works & papers.keys()):
                graph.add_relationship(node, "AUTHORED", papers[doi])
                paper_authors[doi].append(f"orcid:{record['orcid']}")
                authors[f"orcid:{record['orcid']}"] = node
                relationships += 1

    co_authored = 0
    if "CO_AUTHORED" in declared_relationships:
        pairs: set[tuple[int, int]] = set()
        for ids in paper_authors.values():
            nodes = sorted(authors[i] for i in ids)
            pairs |= {(a, b) for i, a in enumerate(nodes) for b in nodes[i + 1 :]}
        for a, b in sorted(pairs):
            graph.add_relationship(a, "CO_AUTHORED", b)
        co_authored = len(pairs)
        relationships += co_authored

    graph.save()
    nodes = len(venues) + len(grants) + len(authors) + len(papers)
    return BuildStats(nodes, relationships, matched, added, co_authored)


# --- Command line (the Construction Entry Point) ----------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the scholar-kg research-output graph.")
    parser.add_argument("--ontology", required=True, help="the Declared Ontology (stetiq YAML)")
    parser.add_argument(
        "--scope", default='{"database": "scholar"}', help="Graph Source scope JSON"
    )
    parser.add_argument(
        "--graph", default=os.environ.get("SCHOLAR_GRAPH_FILE", str(DEFAULT_GRAPH_FILE))
    )
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    parser.add_argument(
        "--merge-by-orcid",
        action="store_true",
        help="match ORCID records to authors by shared works instead of by name spelling",
    )
    args = parser.parse_args(argv)

    ontology = parse_yaml(Path(args.ontology).read_text(encoding="utf-8"))
    database = json.loads(args.scope).get("database") or DEFAULT_DATABASE
    stats = build(
        ScholarGraph(args.graph),
        ontology=ontology,
        merge_by_orcid=args.merge_by_orcid,
        data_dir=Path(args.data_dir),
        database=database,
    )
    print(json.dumps({"merge_by_orcid": args.merge_by_orcid, **stats.__dict__}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
