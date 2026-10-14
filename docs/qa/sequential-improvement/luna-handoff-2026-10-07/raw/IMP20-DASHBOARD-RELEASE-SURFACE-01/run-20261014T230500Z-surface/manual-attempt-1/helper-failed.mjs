import { readFile, writeFile, mkdtemp, rm } from 'node:fs/promises';
import path from 'node:path';
import { loadOmowright } from '/Users/mr.k/.codex/plugins/cache/sisyphuslabs/omo/5.1.33/skills/browser/scripts/omowright.mjs';
import { startNoAuthServer } from '/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai/dashboard/e2e/helpers/hermeticBackend.ts';

const output = process.argv[2];
if (!output) throw new Error('Evidence output directory is required');
process.chdir('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai/dashboard');
const server = await startNoAuthServer();
const { omowright } = await loadOmowright();
const profile = await mkdtemp(path.join(output, 'runtime/browser-'));
const observations = [];
const requests = [];
const axeSource = await readFile('/Users/mr.k/.codex/worktrees/candidate-git-boundary/Ssak-Ai/dashboard/node_modules/axe-core/axe.min.js', 'utf8');
let routes;
let browser;
try {
  browser = await omowright.connectPipe({
    browserPath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    browserArgs: ['--headless', '--no-first-run', `--user-data-dir=${profile}`],
    storageRoot: profile,
  });
  const page = await browser.newTab('about:blank');
  routes = omowright.createRoutes(page);
  await routes.route('**/*', route => {
    const url = route.request.url;
    requests.push(url);
    return url.startsWith(server.baseUrl) ? route.continue() : route.abort();
  });
  for (const device of ['desktop-1440', 'iphone-14']) {
    await omowright.emulate(page, device);
    for (const scheme of ['dark', 'light']) {
      await page.cdp.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: scheme }] }, await page.resolveSessionId());
      await page.goto(`${server.baseUrl}/agent`);
      await page.locator('.agent-status-label').waitFor({ state: 'visible' });
      for (const surface of ['agent', 'palette']) {
        if (surface === 'palette') {
          await page.keyboard.press('Meta+k');
          await page.locator('[role="dialog"][aria-label="명령 팔레트"]').waitFor({ state: 'visible' });
        }
        const label = `${surface}-${device}-${scheme}`;
        await writeFile(path.join(output, `${label}.png`), await page.screenshot());
        await writeFile(path.join(output, `${label}.snapshot.json`), JSON.stringify(omowright.compactSnapshot(await page.snapshot()), null, 2));
        await page.evaluate(source => {
          const script = document.createElement('script');
          script.textContent = source;
          document.head.append(script);
        }, axeSource);
        const violations = await page.evaluate(async () => (await window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'] } })).violations);
        const layout = await page.evaluate(() => ({
          width: innerWidth,
          documentWidth: document.documentElement.scrollWidth,
          theme: document.documentElement.dataset.theme ?? null,
          textMuted: getComputedStyle(document.documentElement).getPropertyValue('--text-muted'),
          labels: [...document.querySelectorAll('.agent-status-label,.metric-label,.cmd-shortcut,.cmd-item-subtitle')].map(node => ({ text: node.textContent, color: getComputedStyle(node).color, background: getComputedStyle(node).backgroundColor })),
        }));
        await writeFile(path.join(output, `${label}.axe.json`), JSON.stringify({ violations, layout }, null, 2));
        observations.push({ label, serious: violations.filter(v => v.impact === 'serious' || v.impact === 'critical').map(v => ({ id: v.id, targets: v.nodes.map(n => n.target) })), layout });
        if (surface === 'palette') await page.keyboard.press('Escape');
      }
    }
  }
} finally {
  try {
    if (routes) await routes.dispose();
    if (browser) await browser.close();
  } finally {
    await server.cleanup();
  }
  await rm(profile, { recursive: true, force: true });
  await writeFile(path.join(output, 'browser-requests.json'), JSON.stringify(requests, null, 2));
  await writeFile(path.join(output, 'manual-observations.json'), JSON.stringify({ observations, browserClosed: true, backendCleanupCompleted: true }, null, 2));
}
console.log(JSON.stringify(observations.map(({ label, serious }) => ({ label, serious }))));
