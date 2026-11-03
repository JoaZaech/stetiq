# map-prototype/ — PROTOTYPE, throwaway (branch `prototype/ontology-map-d3`)

**Question:** what should the Ontology Map look like once it is drawn with d3 (ADR 0014),
so it is more concise, more accurate and easier to read, with **one layout shared by
every Ontology Version** of a Knowledge Graph?

**Run:** `cd frontend && npm run prototype:map`, then open
<http://localhost:5173/ui/kg/trial-registry/versions/4/ontology?variant=A>. This serves a
throwaway copy of `.stetiq/examples.db` on port 5057, plus the Vite dev UI. Cycle the
variants with the floating bar or the ← / → keys.

| `?variant=` | Variant | What it tries |
| --- | --- | --- |
| `current` (or absent) | Today's Map | the React Flow + ELK baseline |
| `A` | Anchored map | node-link with one line per class pair, relations as `NAME →` / `← NAME` read left to right, arrowheads per direction, UML subclass triangles, loops on top, labels placed clear of classes, only focused or changed labels when zoomed out |
| `B` | Schema cards | ERD cards: attributes (`*` required, type or Vocabulary), then outgoing relations; each line leaves from its relation's row |
| `C` | Matrix | source × target grid in subclass-tree order; nothing can cross or overlap at any size |

Prototype bar above the Map: **Version** steps through versions in place (the layout and the
view never move); **Changes since vN-1** shows added (green) and removed (red, dashed
ghosts) items; **Layout** `anchored` / `union` (`?layout=union`); **Stress test**
(`?scale=large`) swaps in a synthetic 5-version history that grows from 50 to 74 classes. The
readout on the right says whether any class of this version *would move when later versions
land*.

**Layout** (`stable-layout.prototype.ts`, d3-force only):

- `anchored`: versions are laid out oldest first. A class keeps the place it got in the first
  version that declared it. New classes start next to their placed neighbours, and the
  classes already placed (removed ones included) stay fixed as obstacles. Registering a new
  version never moves anything. Checked on the stress test: 0 moves across 5 versions,
  0 overlaps, deterministic, about 150 ms.
- `union`: one layout of every class in the history. Every version agrees, but a new
  version reshuffles everything once: 66 of 66 classes moved between "v1–v3 registered"
  and "v1–v5 registered".
- Forces: link distance sized for the boxes and their labels, rectangular collision, each
  subclass kept below its superclass, lines pushed off classes they don't belong to, and a
  final spiral search that moves any class still overlapping to the nearest clear spot.

Files: `OntologyMapPrototype.tsx` (data, prototype bar, details panel), `variants.prototype.ts`,
`Variant*.prototype.tsx`, `schema-view.prototype.ts` (per-version model, diff and synthetic
data), `sizes.prototype.ts`, `../../../../components/PrototypeSwitcher.tsx` (dev builds only).
