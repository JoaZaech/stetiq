/**
 * Sets the URL search param `name` to `value`, or deletes it when `value` is absent or
 * empty, so a default leaves the URL clean. Returns `params`, to end a `setSearchParams`
 * updater: `setParams((p) => setOrDeleteParam(p, 'q', query), { replace: true })`.
 */
export function setOrDeleteParam(
  params: URLSearchParams,
  name: string,
  value: string | null | undefined,
): URLSearchParams {
  if (value) params.set(name, value)
  else params.delete(name)
  return params
}
