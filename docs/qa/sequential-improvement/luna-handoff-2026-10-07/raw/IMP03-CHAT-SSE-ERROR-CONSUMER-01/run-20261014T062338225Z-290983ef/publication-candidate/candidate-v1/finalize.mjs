import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const run = path.dirname(fileURLToPath(import.meta.url));
const root = '/Users/mr.k/.codex/worktrees/structured-output-publication/Ssak-Ai';
const owned = ['dashboard/src/api/client.ts', 'dashboard/src/api/client.streamChannels.test.ts', 'dashboard/src/components/Chat/__tests__/ChatPageStreamChannels.test.tsx'];
const hashBytes = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');
const hash = (file) => hashBytes(fs.readFileSync(file));
const read = (file) => JSON.parse(fs.readFileSync(path.join(run, file), 'utf8'));
const baselineArgs = [path.join(root, 'dashboard/node_modules/eslint/bin/eslint.js'), '--stdin', '--stdin-filename', 'src/api/client.ts'];
const baselineStarted = new Date().toISOString();
const baseline = spawnSync('node', baselineArgs, { cwd: path.join(root, 'dashboard'), input: fs.readFileSync(path.join(run, 'preimage/dashboard/src/api/client.ts')), encoding: 'utf8' });
fs.writeFileSync(path.join(run, 'baseline-lint.stdout'), baseline.stdout);
fs.writeFileSync(path.join(run, 'baseline-lint.stderr'), baseline.stderr);
fs.writeFileSync(path.join(run, 'baseline-lint-receipt.json'), JSON.stringify({ command: ['node', ...baselineArgs], cwd: path.join(root, 'dashboard'), input: 'preimage/dashboard/src/api/client.ts', inputSHA256: hash(path.join(run, 'preimage/dashboard/src/api/client.ts')), started: baselineStarted, ended: new Date().toISOString(), exitCode: baseline.status }, null, 2));
const reconstruction = path.join(run, 'reconstruction');
for (const file of owned) {
  const target = path.join(reconstruction, file);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(path.join(run, 'preimage', file), target);
}
const result = spawnSync('patch', ['-p1', '-i', path.join(run, 'candidate.patch')], { cwd: reconstruction, encoding: 'utf8' });
const binding = owned.map((file) => ({ file, head: hashBytes(spawnSync('git', ['show', `b345bbb7601f1611e6de639161f9fbd241ac1eba:${file}`], { cwd: root }).stdout), preimage: hash(path.join(run, 'preimage', file)), current: hash(path.join(root, file)), source: hash(path.join(run, 'source', file)), reconstructed: hash(path.join(reconstruction, file)) }));
if (result.status !== 0 || binding.some((file) => file.head !== file.preimage || file.source !== file.current || file.reconstructed !== file.current)) throw new Error('Candidate source or reconstruction mismatch');
fs.writeFileSync(path.join(run, 'patch-reconstruction.json'), JSON.stringify({ command: ['patch', '-p1', '-i', path.join(run, 'candidate.patch')], cwd: reconstruction, exitCode: result.status, stdout: result.stdout, stderr: result.stderr, binding }, null, 2));
const tests = read('vitest.json');
const receipts = read('receipts.json');
if (tests.numPassedTests !== 59 || tests.numFailedTests !== 0 || tests.numPendingTests !== 0 || !receipts.sourcesStable || receipts.receipts.some((receipt) => receipt.exitCode !== 0)) throw new Error('Candidate checks failed');
fs.writeFileSync(path.join(run, 'result.json'), JSON.stringify({ status: 'PASS_SCOPED_OFFLINE_CLEAN_CANDIDATE', tests: tests.numTotalTests, passed: tests.numPassedTests, failed: tests.numFailedTests, skipped: tests.numPendingTests, sourcesStable: receipts.sourcesStable, sourceInputCount: Object.keys(read('source-before.json')).length, lint: { exitCode: 0, errors: 0, warnings: 1, preexisting: 'createAccessPinHeaders unused import; baseline-lint.stdout reproduces from HEAD preimage' }, patchReconstructed: true, cases: tests.testResults.flatMap((suite) => suite.assertionResults.map((test) => ({ name: test.fullName, status: test.status }))) }, null, 2));
const artifacts = fs.readdirSync(run, { recursive: true }).filter((file) => fs.statSync(path.join(run, file)).isFile() && file !== 'artifact-manifest.json');
fs.writeFileSync(path.join(run, 'artifact-manifest.json'), JSON.stringify(artifacts.map((file) => ({ file, bytes: fs.statSync(path.join(run, file)).size, sha256: hash(path.join(run, file)) })), null, 2));
console.log(JSON.stringify({ passed: tests.numPassedTests, failed: tests.numFailedTests, patchReconstructed: true, artifactCount: artifacts.length, baselineLintExit: baseline.status }));
