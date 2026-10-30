/**
 * Orders two strings by their characters' codes, not the locale: as the server's Python
 * sorts them (the same for every character outside the astral planes). A sort comparator.
 */
export const codePointOrder = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0)
