// `npm run check`: typecheck, lint and unit tests, quiet when green. Each step's
// output is held back and printed in full only when that step fails, so a green
// run costs one line of a coding agent's context.
import { spawnSync } from 'node:child_process'

const steps: [name: string, command: string][] = [
  ['typecheck', 'tsc -b --pretty false'],
  ['lint', 'eslint .'],
  ['unit tests', 'vitest run --reporter=dot'],
]

const failed: string[] = []
for (const [name, command] of steps) {
  // Output is captured, not a terminal, so ask the tools for plain text.
  const env = { ...process.env, NO_COLOR: '1', FORCE_COLOR: undefined }
  const run = spawnSync(command, { shell: true, encoding: 'utf8', env })
  if (run.status !== 0) {
    failed.push(name)
    process.stdout.write(`--- ${name} failed: ${command}\n${run.stdout}${run.stderr}\n`)
  }
}

if (failed.length) {
  console.log(`check failed: ${failed.join(', ')}`)
  process.exit(1)
}
console.log(`check passed: ${steps.map(([name]) => name).join(', ')}`)
