/** A run of words in a word diff: in both texts, only the old one (removed) or only the new one (added). */
export interface WordDiffPart {
  kind: 'unchanged' | 'removed' | 'added'
  /** Its words, one space apart. */
  text: string
}

/**
 * How `after` differs from `before`, word by word: the fewest words removed and added (a
 * longest common subsequence of their words), in reading order, a removed run before the
 * added one replacing it. Words are split at whitespace, which the parts do not keep.
 */
export function wordDiff(before: string, after: string): WordDiffPart[] {
  const [a, b] = [words(before), words(after)]
  // common[i][j]: how many words a[i..] and b[j..] have in common, in order.
  const common = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0))
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      common[i][j] = a[i] === b[j] ? common[i + 1][j + 1] + 1 : Math.max(common[i + 1][j], common[i][j + 1])
    }
  }
  const parts: WordDiffPart[] = []
  const push = (kind: WordDiffPart['kind'], word: string) => {
    const last = parts.at(-1)
    if (last?.kind === kind) last.text += ` ${word}`
    else parts.push({ kind, text: word })
  }
  let [i, j] = [0, 0]
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      push('unchanged', a[i])
      i++
      j++
    } else if (i < a.length && (j === b.length || common[i + 1][j] >= common[i][j + 1])) {
      push('removed', a[i++])
    } else {
      push('added', b[j++])
    }
  }
  return parts
}

const words = (text: string) => text.split(/\s+/).filter((w) => w !== '')
