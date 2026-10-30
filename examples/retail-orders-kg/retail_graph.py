"""The retailer's graph database, stood in for by stetiq's `InMemoryGraphSource`.

`RetailGraph` is what the example's pipeline writes into and what stetiq's Client
observes: it implements the `GraphSource` protocol (`observe`, `execute_read`) by
delegating to an `InMemoryGraphSource` it rebuilds whenever the data changed. Keeping the
rows in plain dicts here (instead of only inside the in-memory store) is what lets the
season mutate the graph between Observations: a migration adds Bin nodes, a retention job
deletes Shipments, the weeks add Orders.

Every node carries the extra label `Retail`, the label the Knowledge Graph's Graph Source
scope is narrowed to. The `Audit` nodes another team keeps in the same database lack it,
so they are outside the scope and never show up in an Observed Schema.

Competency Questions are answered the way the plant example does it: by query text, with
canned aggregates (`add_query_result`). Only aggregates ever leave this module (ADR 0001).
"""

from __future__ import annotations

import datetime as dt
import random
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from retail_synth import Batch, CustomerRecord, Seeds

from stetiq import GraphSourceScope, InMemoryGraphSource

DATABASE = "retail"
SCOPE_LABEL = "Retail"
SCOPE = GraphSourceScope(database=DATABASE, label=SCOPE_LABEL)

DEDUPE_STRATEGIES = ("none", "exact", "fuzzy")
LOADERS_ORDERS = "orders"  # the catalogue always loads; shipments have a loader of their own
LOADERS_ALL = "orders,shipments"


@dataclass(frozen=True)
class BuildParams:
    """What a Construction Run of the pipeline is configured with (its logged params)."""

    dedupe_strategy: str = "fuzzy"
    batch_size: int = 1000
    loaders: str = LOADERS_ALL
    include_returns: bool = False

    def as_params(self) -> dict[str, object]:
        return {
            "dedupe_strategy": self.dedupe_strategy,
            "batch_size": self.batch_size,
            "loaders": self.loaders,
            "include_returns": self.include_returns,
        }


@dataclass(frozen=True)
class BuildStats:
    customers: int
    duplicate_customers_merged: int
    orders: int
    order_lines: int
    shipments: int
    returns: int


Node = dict[str, Any]
Relationship = tuple[str, str, str, str, str]  # (source label, key, type, target label, key)


class RetailGraph:
    def __init__(self, seeds: Seeds, use_case_file: Path) -> None:
        self.seeds = seeds
        doc = yaml.safe_load(use_case_file.read_text())
        self._queries = {q["id"]: q["query"] for q in doc["competency_questions"] if q.get("query")}
        self._nodes: dict[str, dict[str, Node]] = defaultdict(dict)
        self._relationships: list[Relationship] = []
        self._departments: set[str] = set()
        self._store: InMemoryGraphSource | None = None  # rebuilt lazily after changes
        self.observations = 0

    # --- GraphSource protocol -----------------------------------------------------------

    def observe(self, scope: GraphSourceScope):
        self.observations += 1
        return self._materialised().observe(scope)

    def execute_read(
        self, scope: GraphSourceScope, query: str, parameters: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return self._materialised().execute_read(scope, query, parameters)

    # --- what the pipeline does: a full rebuild of the scope --------------------------------

    def rebuild(
        self, records: tuple[CustomerRecord, ...], batch: Batch, params: BuildParams
    ) -> BuildStats:
        """Drop everything in the scope and load it again with these params."""
        if params.dedupe_strategy not in DEDUPE_STRATEGIES:
            raise ValueError(f"unknown dedupe_strategy {params.dedupe_strategy!r}")
        self._nodes.clear()
        self._relationships.clear()
        self._store = None
        self._load_catalog()
        key_of, merged = self._load_customers(records, params.dedupe_strategy)
        self.add_batch(
            batch,
            customer_of=lambda order: key_of[order["customer"]],
            shipments="shipments" in params.loaders.split(","),
            returns=params.include_returns,
        )
        return BuildStats(
            customers=len(self._nodes["Customer"]),
            duplicate_customers_merged=merged,
            orders=len(self._nodes["Order"]),
            order_lines=len(self._nodes["OrderLine"]),
            shipments=len(self._nodes["Shipment"]),
            returns=len(self._nodes["Return"]),
        )

    def _load_catalog(self) -> None:
        for c in self.seeds.categories:
            self._nodes["Category"][c.code] = {"code": c.code, "name": c.name}
            if c.level == 1:
                self._departments.add(c.code)
            else:
                self._relationships.append(
                    ("Category", c.code, "SUBCATEGORY_OF", "Category", c.parent)
                )
        for s in self.seeds.suppliers:
            self._nodes["Supplier"][s["code"]] = dict(s)
        for w in self.seeds.warehouses:
            self._nodes["Warehouse"][w["code"]] = dict(w)
        for p in self.seeds.products:
            self._nodes["Product"][p.sku] = {
                "sku": p.sku,
                "name": p.name,
                "price": p.price,
                "weight_kg": p.weight_kg,  # None for a few products: a lower fill rate
            }
            self._relationships.append(("Product", p.sku, "IN_CATEGORY", "Category", p.subcategory))
            self._relationships.append(("Product", p.sku, "SUPPLIED_BY", "Supplier", p.supplier))

    def _load_customers(
        self, records: tuple[CustomerRecord, ...], strategy: str
    ) -> tuple[dict[str, str], int]:
        """Customer nodes per dedupe strategy; returns (feed row id -> node key, merged rows).

        none: every feed row is a node. exact: rows with the same normalised email merge.
        fuzzy: exact, plus rows with the same name and postcode (the guest checkouts)."""
        key_of: dict[str, str] = {}
        by_email: dict[str, str] = {}
        by_name: dict[tuple[str, str], str] = {}
        merged = 0
        for r in records:  # primary rows come first, so duplicates find their account
            target = None
            if strategy in ("exact", "fuzzy") and r.normalised_email:
                target = by_email.get(r.normalised_email)
            if target is None and strategy == "fuzzy":
                target = by_name.get((r.name.lower(), r.postcode))
            if target is not None:
                key_of[r.id] = target
                merged += 1
                continue
            key_of[r.id] = r.id
            self._nodes["Customer"][r.id] = {
                "id": r.id,
                "email": r.normalised_email,
                "name": r.name,
                "city": r.city,
                "postcode": r.postcode,
                "since": r.since,
            }
            if r.normalised_email:
                by_email[r.normalised_email] = r.id
            by_name.setdefault((r.name.lower(), r.postcode), r.id)
        return key_of, merged

    # --- incremental writes (the weekly batches, the other teams' scripts) -------------------

    def add_batch(
        self,
        batch: Batch,
        *,
        customer_of: Callable[[dict], str] = lambda order: order["customer"],
        shipments: bool = True,
        returns: bool = True,
    ) -> None:
        self._store = None
        for o in batch.orders:
            self._nodes["Order"][o["id"]] = {k: v for k, v in o.items() if k != "customer"}
            self._relationships.append(("Customer", customer_of(o), "PLACED", "Order", o["id"]))
        for line in batch.lines:
            self._nodes["OrderLine"][line["id"]] = {
                k: line[k] for k in ("id", "quantity", "unit_price")
            }
            self._relationships.append(
                ("Order", line["order"], "CONTAINS", "OrderLine", line["id"])
            )
            self._relationships.append(
                ("OrderLine", line["id"], "OF_PRODUCT", "Product", line["product"])
            )
        if shipments:
            for s in batch.shipments:
                self._nodes["Shipment"][s["id"]] = {
                    k: s[k] for k in ("id", "shipped_at", "carrier", "tracking_number")
                }
                self._relationships.append(
                    ("Shipment", s["id"], "SHIPPED_FROM", "Warehouse", s["warehouse"])
                )
                self._relationships.append(("Shipment", s["id"], "FULFILLS", "Order", s["order"]))
        if returns:
            for r in batch.returns:
                self._nodes["Return"][r["id"]] = {
                    k: r[k] for k in ("id", "reason", "returned_at", "refund")
                }
                self._relationships.append(("Return", r["id"], "RETURNED", "OrderLine", r["line"]))

    def customer_keys(self) -> list[str]:
        return list(self._nodes["Customer"])

    def count(self, label: str) -> int:
        return len(self._nodes[label])

    def add_bins(self, rng: random.Random, *, per_warehouse: int = 24) -> tuple[int, int]:
        """The warehouse team's migration: Bin nodes and STORED_IN, straight into the
        database, with the Retail label but without telling anyone about the Ontology."""
        self._store = None
        bins: list[str] = []
        for w in self.seeds.warehouses:
            for n in range(per_warehouse):
                code = f"{w['code']}-A{n // 6 + 1:02d}-{n % 6 + 1:02d}"
                self._nodes["Bin"][code] = {
                    "code": code,
                    "aisle": n // 6 + 1,
                    "warehouse": w["code"],
                }
                bins.append(code)
        stored = 0
        for sku in self._nodes["Product"]:
            for code in rng.sample(bins, 2):
                self._relationships.append(("Product", sku, "STORED_IN", "Bin", code))
                stored += 1
        return len(bins), stored

    def purge_shipments(self, rng: random.Random, fraction: float) -> int:
        """The retention job: delete `fraction` of the Shipment nodes and their relationships."""
        self._store = None
        keys = sorted(self._nodes["Shipment"])
        doomed = set(rng.sample(keys, round(len(keys) * fraction)))
        for key in doomed:
            del self._nodes["Shipment"][key]
        self._relationships = [
            r for r in self._relationships if not (r[0] == "Shipment" and r[1] in doomed)
        ]
        return len(doomed)

    # --- the in-memory store ---------------------------------------------------------------

    def _materialised(self) -> InMemoryGraphSource:
        if self._store is None:
            self._store = self._build_store()
        return self._store

    def _build_store(self) -> InMemoryGraphSource:
        store = InMemoryGraphSource()
        ids: dict[tuple[str, str], int] = {}
        for label, nodes in self._nodes.items():
            for key, props in nodes.items():
                labels = [label, SCOPE_LABEL]
                if label == "Category" and key in self._departments:
                    labels.append("Department")
                ids[(label, key)] = store.add_node(labels, props, database=DATABASE)
        for source, source_key, type_, target, target_key in self._relationships:
            store.add_relationship(ids[(source, source_key)], type_, ids[(target, target_key)])
        # Another team's bookkeeping in the same database, without the Retail label.
        for n, job in enumerate(("nightly-export", "price-sync", "gdpr-erasure")):
            store.add_node(
                ["Audit"], {"job": job, "ran_at": dt.date(2026, 8, 29 + n)}, database=DATABASE
            )
        for question_id, query in self._queries.items():
            store.add_query_result(query, self._answer(question_id), database=DATABASE)
        return store

    # --- canned Competency Question answers: aggregates over the rows ------------------------

    def _answer(self, question_id: str) -> list[dict[str, Any]]:
        rels = defaultdict(list)
        for _, source_key, type_, _, target_key in self._relationships:
            rels[type_].append((source_key, target_key))
        match question_id:
            case "top-categories-by-revenue":
                parent = dict(rels["SUBCATEGORY_OF"])
                category_of = dict(rels["IN_CATEGORY"])
                product_of = dict(rels["OF_PRODUCT"])
                revenue: Counter[str] = Counter()
                for key, line in self._nodes["OrderLine"].items():
                    node = category_of[product_of[key]]
                    while node in parent:
                        node = parent[node]
                    revenue[node] += line["quantity"] * line["unit_price"]
                return [
                    {"department": self._nodes["Category"][code]["name"], "revenue": round(v, 2)}
                    for code, v in revenue.most_common()
                ]
            case "return-rate-per-product":
                product_of = dict(rels["OF_PRODUCT"])
                lines_per_product = Counter(product_of.values())
                returned = Counter(product_of[line] for _, line in rels["RETURNED"])
                return [
                    {"sku": sku, "return_rate": round(n / lines_per_product[sku], 4)}
                    for sku, n in returned.most_common()
                ]
            case "lines-per-order":
                orders = self.count("Order")
                return [{"lines_per_order": self.count("OrderLine") / orders}] if orders else []
            case "suppliers-behind-orders":
                supplier_of = dict(rels["SUPPLIED_BY"])
                product_of = dict(rels["OF_PRODUCT"])
                orders_per_supplier: dict[str, set[str]] = defaultdict(set)
                for order, line in rels["CONTAINS"]:
                    orders_per_supplier[supplier_of[product_of[line]]].add(order)
                return [
                    {"supplier": self._nodes["Supplier"][code]["name"], "orders": len(orders)}
                    for code, orders in sorted(
                        orders_per_supplier.items(), key=lambda i: -len(i[1])
                    )
                ]
            case "category-tree-depth":
                parent = dict(rels["SUBCATEGORY_OF"])

                def depth(code: str) -> int:
                    return 1 + depth(parent[code]) if code in parent else 1

                return [{"depth": max(depth(c) for c in self._nodes["Category"])}]
            case "orders-per-warehouse":
                per_warehouse = Counter(target for _, target in rels["SHIPPED_FROM"])
                return [
                    {"warehouse": self._nodes["Warehouse"][code]["name"], "shipments": n}
                    for code, n in per_warehouse.most_common()
                ]
            case "repeat-customers":
                placed = Counter(source for source, _ in rels["PLACED"])
                return [{"repeat_customers": sum(1 for n in placed.values() if n > 1)}]
        raise KeyError(f"no canned answer for Competency Question {question_id!r}")
