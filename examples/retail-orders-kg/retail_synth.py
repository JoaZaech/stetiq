"""Deterministic synthetic data for the retail-orders example.

The committed seeds in data/ (the category tree, 60 products, suppliers, warehouses and
the season calendar) are what makes the graph look real; everything else (customers,
orders, lines, shipments, returns) is generated here from `random.Random(SEED)`, so every
run of the demo and the test sees the same numbers. Nothing in this module talks to
stetiq: it only produces the rows the pipeline (retail_graph.py) writes into the Graph
Source.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SEED = 2026
DATA_DIR = Path(__file__).resolve().parent / "data"

# Size of the season-start graph. Duplicates are the customer feed's dirt: an exact
# duplicate repeats a known email with different case or whitespace, a guest checkout
# has no email at all but the same name and postcode as an account.
CUSTOMERS = 1000
EXACT_DUPLICATES = 60
GUEST_CHECKOUTS = 40
ORDERS = 2800
SEASON_START = dt.date(2026, 8, 30)

FIRST_NAMES = (
    "Anna",
    "Bram",
    "Chiara",
    "David",
    "Elin",
    "Farid",
    "Greta",
    "Hugo",
    "Ines",
    "Jonas",
    "Katja",
    "Luca",
    "Maren",
    "Nils",
    "Olga",
    "Pawel",
    "Rosa",
    "Sven",
    "Tessa",
    "Umut",
)
LAST_NAMES = (
    "Berg",
    "Costa",
    "Dahl",
    "Eriksen",
    "Fischer",
    "Garcia",
    "Hansen",
    "Ivanova",
    "Jansen",
    "Keller",
    "Lind",
    "Moreau",
    "Novak",
    "Olsen",
    "Peeters",
    "Rossi",
    "Schmidt",
    "Toth",
    "Varga",
    "Weber",
)
CITIES = (
    ("Hamburg", "20095"),
    ("Berlin", "10115"),
    ("Rotterdam", "3011"),
    ("Utrecht", "3511"),
    ("Lyon", "69001"),
    ("Paris", "75003"),
    ("Madrid", "28004"),
    ("Valencia", "46001"),
    ("Warsaw", "00-001"),
    ("Krakow", "30-001"),
    ("Milan", "20121"),
    ("Vienna", "1010"),
)
CHANNELS = (("web", 60), ("app", 35), ("phone", 5))
STATUSES = (("delivered", 70), ("shipped", 20), ("processing", 10))
CARRIERS = ("DHL", "DPD", "GLS", "PostNL", "InPost")
RETURN_REASONS = ("wrong size", "damaged", "not as described", "changed mind", "arrived late")
LINE_COUNTS = ((1, 25), (2, 35), (3, 25), (4, 15))


@dataclass(frozen=True)
class Category:
    code: str
    name: str
    parent: str | None  # code of the parent category; None for a department
    level: int  # 1 = department, 2 = category, 3 = subcategory


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    subcategory: str
    supplier: str
    price: float
    weight_kg: float | None


@dataclass(frozen=True)
class Week:
    number: int
    observed_on: str
    orders_factor: float
    shipped_share: float
    return_share: float
    events: tuple[str, ...]
    retention_passes: tuple[float, ...] = ()


@dataclass(frozen=True)
class Seeds:
    categories: tuple[Category, ...]
    products: tuple[Product, ...]
    suppliers: tuple[dict[str, str], ...]
    warehouses: tuple[dict[str, str], ...]
    weeks: tuple[Week, ...]

    @property
    def departments(self) -> tuple[Category, ...]:
        return tuple(c for c in self.categories if c.level == 1)


def load_seeds(data_dir: Path = DATA_DIR) -> Seeds:
    tree = yaml.safe_load((data_dir / "categories.yaml").read_text())
    categories: list[Category] = []
    for dept in tree["departments"]:
        categories.append(Category(dept["code"], dept["name"], None, 1))
        for cat in dept["categories"]:
            categories.append(Category(cat["code"], cat["name"], dept["code"], 2))
            for sub in cat["subcategories"]:
                categories.append(Category(sub["code"], sub["name"], cat["code"], 3))
    with (data_dir / "products.csv").open(newline="") as f:
        products = tuple(
            Product(
                sku=row["sku"],
                name=row["name"],
                subcategory=row["subcategory"],
                supplier=row["supplier"],
                price=float(row["price"]),
                weight_kg=float(row["weight_kg"]) if row["weight_kg"] else None,
            )
            for row in csv.DictReader(f)
        )
    with (data_dir / "suppliers.csv").open(newline="") as f:
        suppliers = tuple(csv.DictReader(f))
    with (data_dir / "warehouses.csv").open(newline="") as f:
        warehouses = tuple(csv.DictReader(f))
    calendar = json.loads((data_dir / "calendar.json").read_text())
    defaults = calendar["defaults"]
    weeks = tuple(
        Week(
            number=w["week"],
            observed_on=w["observed_on"],
            orders_factor=w["orders_factor"],
            shipped_share=w.get("shipped_share", defaults["shipped_share"]),
            return_share=w.get("return_share", defaults["return_share"]),
            events=tuple(w["events"]),
            retention_passes=tuple(w.get("retention_passes", ())),
        )
        for w in calendar["weeks"]
    )
    return Seeds(tuple(categories), products, suppliers, warehouses, weeks)


# --- customers ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CustomerRecord:
    """One row of the customer feed. The same person may appear several times."""

    id: str
    customer: str  # id of the person this row really is
    kind: str  # primary | exact | guest
    email: str | None
    name: str
    city: str
    postcode: str
    since: dt.date

    @property
    def normalised_email(self) -> str | None:
        return self.email.strip().lower() if self.email else None


def generate_customers(rng: random.Random) -> list[CustomerRecord]:
    """`CUSTOMERS` people, plus the duplicates the feed carries. Primary rows first."""
    primaries: list[CustomerRecord] = []
    for n in range(1, CUSTOMERS + 1):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        city, postcode = rng.choice(CITIES)
        primaries.append(
            CustomerRecord(
                id=f"C-{n:05d}",
                customer=f"C-{n:05d}",
                kind="primary",
                email=f"{first.lower()}.{last.lower()}{n}@example.com",
                name=f"{first} {last}",
                city=city,
                postcode=postcode,
                since=SEASON_START - dt.timedelta(days=rng.randint(30, 1400)),
            )
        )
    duplicates: list[CustomerRecord] = []
    for i, source in enumerate(rng.sample(primaries, EXACT_DUPLICATES + GUEST_CHECKOUTS)):
        exact = i < EXACT_DUPLICATES
        duplicates.append(
            CustomerRecord(
                id=f"C-{CUSTOMERS + i + 1:05d}",
                customer=source.customer,
                kind="exact" if exact else "guest",
                email=(" " + source.email.title()) if exact else None,
                name=source.name,
                city=source.city,
                postcode=source.postcode,
                since=source.since + dt.timedelta(days=rng.randint(1, 200)),
            )
        )
    return primaries + duplicates


# --- orders, lines, shipments, returns ----------------------------------------------------


@dataclass
class Batch:
    """What one build or one season week adds to the graph. `orders[*]["customer"]` is a
    customer feed row id in the season-start batch and a Customer node key later on."""

    orders: list[dict] = field(default_factory=list)
    lines: list[dict] = field(default_factory=list)
    shipments: list[dict] = field(default_factory=list)
    returns: list[dict] = field(default_factory=list)


@dataclass
class Sequence:
    """Id counters shared by every batch, so ids never collide across the season."""

    order: int = 0
    line: int = 0
    shipment: int = 0
    reset: int = 0

    def next(self, kind: str) -> str:
        value = getattr(self, kind) + 1
        setattr(self, kind, value)
        return f"{kind[0].upper()}-{value:06d}"


def _weighted(rng: random.Random, options):
    values, weights = zip(*options, strict=True)
    return rng.choices(values, weights=weights)[0]


def generate_batch(
    rng: random.Random,
    seq: Sequence,
    seeds: Seeds,
    customers: list[str],
    *,
    orders: int,
    first_day: dt.date,
    days: int = 7,
    shipped_share: float,
    return_share: float,
) -> Batch:
    """`orders` orders placed within `days` of `first_day` by random `customers`."""
    batch = Batch()
    # A few products are hits: weights fall off by catalogue position, reshuffled per batch.
    popularity = [1.0 / (1 + rng.random() * 6) for _ in seeds.products]
    for _ in range(orders):
        placed = first_day + dt.timedelta(days=rng.randrange(days))
        order_id = seq.next("order")
        total = 0.0
        k = _weighted(rng, LINE_COUNTS)
        for product in rng.choices(seeds.products, weights=popularity, k=k):
            quantity = _weighted(rng, ((1, 70), (2, 22), (3, 8)))
            line_id = seq.next("line")
            batch.lines.append(
                {
                    "id": line_id,
                    "order": order_id,
                    "product": product.sku,
                    "quantity": quantity,
                    "unit_price": product.price,
                }
            )
            total += quantity * product.price
            if rng.random() < return_share:
                batch.returns.append(
                    {
                        "id": seq.next("reset"),
                        "line": line_id,
                        "reason": rng.choice(RETURN_REASONS),
                        "returned_at": placed + dt.timedelta(days=rng.randint(5, 20)),
                        "refund": round(quantity * product.price, 2),
                    }
                )
        batch.orders.append(
            {
                "id": order_id,
                "customer": rng.choice(customers),
                "placed_at": placed,
                "status": _weighted(rng, STATUSES),
                "channel": _weighted(rng, CHANNELS),
                "total": round(total, 2),
            }
        )
        if rng.random() < shipped_share:
            batch.shipments.append(
                {
                    "id": seq.next("shipment"),
                    "order": order_id,
                    "warehouse": rng.choice(seeds.warehouses)["code"],
                    "shipped_at": placed + dt.timedelta(days=rng.randint(1, 3)),
                    "carrier": rng.choice(CARRIERS),
                    "tracking_number": f"TRK{rng.randrange(10**9):09d}",
                }
            )
    return batch


@dataclass(frozen=True)
class SeasonStart:
    """The data every one of the six Construction Runs builds from: the same feed rows."""

    records: tuple[CustomerRecord, ...]
    batch: Batch
    sequence: Sequence  # where the season's weekly batches continue counting


def generate_season_start(seeds: Seeds) -> SeasonStart:
    rng = random.Random(SEED)
    records = generate_customers(rng)
    seq = Sequence()
    # Orders are placed by feed rows, duplicates included: what the pipeline's dedupe
    # strategy makes of them is the Construction Run's business.
    batch = generate_batch(
        rng,
        seq,
        seeds,
        [r.id for r in records],
        orders=ORDERS,
        first_day=SEASON_START - dt.timedelta(days=84),
        days=84,
        shipped_share=0.9,
        return_share=0.05,
    )
    return SeasonStart(tuple(records), batch, seq)
