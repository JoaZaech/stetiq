"""Generates the registry exports under data/ deterministically (random.Random(7)).

The hospital's trial registry exports its tables once a month. Two exports are committed:

- `export-2026-05`: the May export. Four participants have no row in consent.csv (the
  consent forms were scanned late), sites.csv has no country column and visits.csv has
  no window_days column.
- `export-2026-06`: the June export. Consent is complete and the columns the data
  standards team asked for (Site.country, Visit.window_days, Trial.status) are present.

Everything about a participant is pseudonymous (`P-xxxxx`, an age band, an enrolment
date): the registry never exports names, dates of birth or contact details, and the
Ontology never has a place for them (ADR 0001, and the `pii_free` Evaluator).

Run `python trials_data.py` from this folder to regenerate both exports. The test
reads the committed files and never regenerates them.
"""

from __future__ import annotations

import csv
import datetime as dt
import random
from pathlib import Path
from typing import Any

EXAMPLE_DIR = Path(__file__).resolve().parent
DATA_DIR = EXAMPLE_DIR / "data"
SEED = 7

TRIALS = [
    ("TR-2024-011", "Low-dose aspirin after transient ischaemic attack", "III", "recruiting"),
    ("TR-2024-017", "Continuous glucose monitoring in type 2 diabetes", "II", "recruiting"),
    ("TR-2024-023", "Early mobilisation after hip fracture surgery", "III", "active"),
    ("TR-2025-004", "Inhaled corticosteroid step-down in mild asthma", "IV", "active"),
    ("TR-2025-009", "Wearable arrhythmia detection after cardiac surgery", "II", "recruiting"),
    ("TR-2025-012", "Statin intensification in chronic kidney disease", "III", "completed"),
]
SITES = [
    ("S-01", "Basel", "CH"),
    ("S-02", "Zürich", "CH"),
    ("S-03", "Freiburg", "DE"),
    ("S-04", "Strasbourg", "FR"),
    ("S-05", "Bern", "CH"),
    ("S-06", "Lyon", "FR"),
    ("S-07", "Stuttgart", "DE"),
    ("S-08", "Lausanne", "CH"),
]
SPECIALTIES = ["cardiology", "endocrinology", "orthopaedics", "pulmonology", "nephrology"]
# (code, name, class, trial)
INTERVENTIONS = [
    ("DRG-ASA-75", "aspirin 75 mg", "Drug", "TR-2024-011"),
    ("DRG-CLO-75", "clopidogrel 75 mg", "Drug", "TR-2024-011"),
    ("DEV-CGM-3", "continuous glucose monitor", "Device", "TR-2024-017"),
    ("DRG-MET-500", "metformin 500 mg", "Drug", "TR-2024-017"),
    ("PRC-MOB-24", "mobilisation within 24 h", "Procedure", "TR-2024-023"),
    ("PRC-PHY-STD", "standard physiotherapy", "Procedure", "TR-2024-023"),
    ("DRG-BUD-200", "budesonide 200 µg", "Drug", "TR-2025-004"),
    ("DEV-ECG-PATCH", "adhesive ECG patch", "Device", "TR-2025-009"),
    ("DEV-HOLTER", "24 h Holter monitor", "Device", "TR-2025-009"),
    ("DRG-ATO-80", "atorvastatin 80 mg", "Drug", "TR-2025-012"),
    ("DRG-ATO-20", "atorvastatin 20 mg", "Drug", "TR-2025-012"),
]
# (code, term, trial): ICD-10-like codes; the body system stays in the gold vocabulary only
CONDITIONS = [
    ("G45.9", "Transient cerebral ischaemic attack", "TR-2024-011"),
    ("E11", "Type 2 diabetes mellitus", "TR-2024-017"),
    ("S72.0", "Fracture of neck of femur", "TR-2024-023"),
    ("J45.2", "Mild intermittent asthma", "TR-2025-004"),
    ("I48.9", "Atrial fibrillation, unspecified", "TR-2025-009"),
    ("N18.3", "Chronic kidney disease, stage 3", "TR-2025-012"),
]
AGE_BANDS = ["40-49", "50-59", "60-69", "70-79", "80+"]
DEVIATIONS = ["visit out of window", "missed assessment", "unapproved concomitant medication"]
PARTICIPANTS = 150
SITES_PER_TRIAL = 3
# Pseudonyms whose consent row is missing from the May export.
LATE_CONSENT = 4


def generate(seed: int = SEED) -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(seed)
    tables: dict[str, list[dict[str, Any]]] = {}
    tables["trials"] = [
        {"registry_id": i, "title": t, "phase": p, "status": s} for i, t, p, s in TRIALS
    ]
    tables["sites"] = [{"site_id": i, "city": c, "country": k} for i, c, k in SITES]
    tables["investigators"] = [
        {
            "staff_id": f"INV-{n:03d}",
            "specialty": SPECIALTIES[(n - 1) % len(SPECIALTIES)],
            "orcid": f"0000-0002-{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}",
            "site_id": SITES[(n - 1) % len(SITES)][0],
        }
        for n in range(1, 11)
    ]
    trial_sites = {t[0]: sorted(rng.sample([s[0] for s in SITES], SITES_PER_TRIAL)) for t in TRIALS}
    tables["trial_sites"] = [
        {"registry_id": t, "site_id": s} for t, sites in trial_sites.items() for s in sites
    ]
    tables["interventions"] = [
        {"code": c, "name": n, "class": k, "registry_id": t} for c, n, k, t in INTERVENTIONS
    ]
    tables["conditions"] = [
        {"code": c, "term": term, "registry_id": t} for c, term, t in CONDITIONS
    ]
    tables["arms"] = [
        {"code": f"{t[0]}/{arm}", "kind": kind, "registry_id": t[0]}
        for t in TRIALS
        for arm, kind in (("A", "experimental"), ("B", "control"))
    ]

    participants, consent, events, visits = [], [], [], []
    for n in range(1, PARTICIPANTS + 1):
        pseudonym = f"P-{10000 + n * 37 % 90000:05d}"
        trial = TRIALS[(n - 1) % len(TRIALS)][0]
        site = rng.choice(trial_sites[trial])
        enrolled = dt.date(2025, 9, 1) + dt.timedelta(days=rng.randint(0, 240))
        participants.append(
            {
                "pseudonym": pseudonym,
                "registry_id": trial,
                "site_id": site,
                "arm": f"{trial}/{rng.choice('AB')}",
                "age_band": rng.choice(AGE_BANDS),
                "enrolled_on": enrolled,
            }
        )
        consent.append(
            {
                "pseudonym": pseudonym,
                "registry_id": trial,
                "consented_on": enrolled - dt.timedelta(days=rng.randint(1, 14)),
                "form_version": rng.choice(["1.0", "1.1", "2.0"]),
            }
        )
        for number in range(1, rng.randint(1, 3) + 1):
            scheduled = enrolled + dt.timedelta(days=28 * number)
            visits.append(
                {
                    "visit_id": f"V-{pseudonym[2:]}-{number}",
                    "pseudonym": pseudonym,
                    "number": number,
                    "scheduled": scheduled,
                    "window_days": 7 if number == 1 else 14,
                    "deviation": rng.choice(DEVIATIONS) if rng.random() < 0.12 else "",
                }
            )
        if rng.random() < 0.45:
            severity = rng.choice(["mild", "mild", "moderate", "moderate", "severe"])
            events.append(
                {
                    "ae_id": f"AE-{len(events) + 1:04d}",
                    "pseudonym": pseudonym,
                    "registry_id": trial,
                    "severity": severity,
                    "serious": severity == "severe" or rng.random() < 0.1,
                    "onset": enrolled + dt.timedelta(days=rng.randint(3, 90)),
                }
            )
    tables["participants"] = participants
    tables["consent"] = consent
    tables["adverse_events"] = events
    tables["visits"] = visits
    return tables


def write_exports(data_dir: Path = DATA_DIR, seed: int = SEED) -> None:
    tables = generate(seed)
    rng = random.Random(seed + 1)
    late = set(rng.sample([c["pseudonym"] for c in tables["consent"]], LATE_CONSENT))

    may = {name: [dict(r) for r in rows] for name, rows in tables.items()}
    may["consent"] = [r for r in may["consent"] if r["pseudonym"] not in late]
    for row in may["sites"]:
        del row["country"]
    for row in may["visits"]:
        del row["window_days"]
    for row in may["trials"]:
        del row["status"]
    _write(data_dir / "export-2026-05", may)
    _write(data_dir / "export-2026-06", tables)


def _write(folder: Path, tables: dict[str, list[dict[str, Any]]]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        with (folder / f"{name}.csv").open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            for row in rows:
                writer.writerow({k: _cell(v) for k, v in row.items()})


def _cell(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)


if __name__ == "__main__":
    write_exports()
    print(f"wrote data/export-2026-05 and data/export-2026-06 under {DATA_DIR}")
