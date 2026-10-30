/**
 * A version number (Ontology Version or Use Case Version) from a route or search param;
 * undefined for anything but plain digits, so `v3`, `3.0` or `-1` are not found.
 */
export function parseVersionNumber(raw: string | null | undefined): number | undefined {
  return raw != null && /^\d+$/.test(raw) ? Number(raw) : undefined
}
