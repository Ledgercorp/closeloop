// Drive the public demo in a real browser and report what the page did.
//
//   node tests/browser_demo_interaction.mjs --probe [chromium|webkit]
//   node tests/browser_demo_interaction.mjs <baseUrl> [chromium|webkit] [--no-decompression-stream]
//
// The last stdout line is a JSON report. Exit status 0 means every check passed.
// --no-decompression-stream removes window.DecompressionStream before any page script
// runs, which reproduces Safari 16.3 and earlier (iOS 16.3 and earlier) on the bundle loader.
import { createRequire } from 'node:module';
import { execSync } from 'node:child_process';

const require = createRequire(import.meta.url);
function loadPlaywright() {
  const candidates = [process.env.PLAYWRIGHT_MODULE, 'playwright'].filter(Boolean);
  for (const candidate of candidates) {
    try { return require(candidate); } catch { /* try the next location */ }
  }
  const globalRoot = execSync('npm root -g', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
  return require(`${globalRoot}/playwright`);
}

const args = process.argv.slice(2);
const probe = args.includes('--probe');
const noDecompressionStream = args.includes('--no-decompression-stream');
const positional = args.filter((a) => !a.startsWith('--'));
const engineName = positional.find((a) => a === 'chromium' || a === 'webkit') || 'chromium';
const baseUrl = positional.find((a) => /^https?:\/\//.test(a));

const playwright = loadPlaywright();
const engine = playwright[engineName];
if (probe) {
  const browser = await engine.launch();
  await browser.close();
  console.log(JSON.stringify({ engine: engineName, version: browser.version() }));
  process.exit(0);
}
if (!baseUrl) { console.error('base URL required'); process.exit(2); }

const failures = [];
const check = (condition, message) => { if (!condition) failures.push(message); };
const device = playwright.devices['iPhone 14'];
const browser = await engine.launch();
const context = await browser.newContext({ ...device, locale: 'en-US' });
const page = await context.newPage();
const consoleErrors = [];
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); });
page.on('pageerror', (e) => consoleErrors.push(`pageerror: ${String(e).slice(0, 200)}`));
const posts = [];
page.on('request', (r) => { if (r.url().endsWith('/demo/run')) posts.push({ method: r.method(), body: r.postData() }); });
await page.addInitScript((strip) => {
  window.__unhandledRejections = [];
  window.addEventListener('unhandledrejection', (e) => window.__unhandledRejections.push(String(e.reason).slice(0, 200)));
  if (strip) { try { delete window.DecompressionStream; } catch { /* non-configurable */ } window.DecompressionStream = undefined; }
}, noDecompressionStream);

const statusHeading = () => page.locator('section[aria-labelledby="lifecycle-heading"] h3', {
  hasText: /^(Verified|Not completed|Awaiting proof|Proof unavailable)$/,
});
const confirmButton = () => page.getByRole('button', { name: 'Confirm demo cancellation' });
const scenarioButton = (label) => page.getByRole('button', { name: label, exact: true });
const outcomes = [];

async function runScenario(label, scenario) {
  const before = posts.length;
  const selector = scenarioButton(label);
  await selector.scrollIntoViewIfNeeded();
  await selector.tap();
  check((await selector.getAttribute('aria-pressed')) === 'true', `${label}: scenario selection did not register`);
  await confirmButton().scrollIntoViewIfNeeded();
  await confirmButton().tap();
  await page.waitForTimeout(250);
  check((await confirmButton().count()) === 0, `${label}: confirm handler did not fire`);
  await statusHeading().first().waitFor({ timeout: 30000 });
  const status = (await statusHeading().first().textContent()).trim();
  const chip = (await page.locator('section[aria-labelledby="lifecycle-heading"] h3 + span').first().textContent()).trim();
  const readBack = (await page.locator('article', { has: page.locator('h3', { hasText: 'Independent read-back' }) }).first().textContent()).replace(/\s+/g, ' ');
  const claim = (await page.locator('article', { has: page.locator('h3', { hasText: 'Execution claim' }) }).first().textContent()).replace(/\s+/g, ' ');
  const newPosts = posts.slice(before);
  check(newPosts.length === 1, `${label}: expected exactly one POST /demo/run, saw ${newPosts.length}`);
  check(newPosts[0]?.method === 'POST' && newPosts[0]?.body === JSON.stringify({ scenario }), `${label}: unexpected request body ${newPosts[0]?.body}`);
  outcomes.push({ scenario, status, chip, claim: claim.slice(0, 160), readBack: readBack.slice(0, 160) });
  return { status, chip, claim, readBack };
}

try {
  const response = await page.goto(`${baseUrl}/demo/`, { waitUntil: 'load' });
  check(response.status() === 200, `GET /demo/ returned ${response.status()}`);
  await confirmButton().waitFor({ timeout: 30000 });
  check(!/\{\{\s*\w+/.test(await page.evaluate(() => document.body.innerText)), 'raw template placeholders are visible');
  check((await page.evaluate(() => document.getElementById('__bundler_err')?.textContent ?? '')) === '', 'bundle loader reported an error');
  check((await page.evaluate(() => typeof window.DecompressionStream)) === (noDecompressionStream ? 'undefined' : 'function'), 'DecompressionStream stripping did not apply');
  check((await page.evaluate(() => typeof verifyCancellation === 'undefined' && typeof runProvider === 'undefined')), 'browser-side verdict logic is present');
  check((await statusHeading().count()) === 0, 'a terminal outcome is shown before confirmation');

  const healthy = await runScenario('Verified path', 'healthy');
  check(healthy.status === 'Verified' && healthy.chip === 'PASS', `healthy rendered ${healthy.status}/${healthy.chip}`);
  const falseSuccess = await runScenario('False success', 'false_success');
  check(falseSuccess.status === 'Not completed' && falseSuccess.chip === 'FAIL', `false_success rendered ${falseSuccess.status}/${falseSuccess.chip}`);
  check(/Success claimed/.test(falseSuccess.claim) && /Auto-renew Enabled/.test(falseSuccess.readBack), 'false_success contradiction is not visible');
  const outage = await runScenario('Evidence outage', 'evidence_outage');
  check(outage.status === 'Awaiting proof' && outage.chip === 'INCONCLUSIVE', `evidence_outage rendered ${outage.status}/${outage.chip}`);

  // Backend unreachable: the page must fail closed.
  await page.route('**/demo/run', (route) => route.abort());
  const aborted = await runScenario('Verified path', 'healthy');
  check(aborted.status === 'Proof unavailable', `backend failure rendered ${aborted.status}`);
  await page.unroute('**/demo/run');

  // Tampered server result: a verdict that contradicts the rest of the server tuple
  // violates the contract, so the page must fail closed rather than pick a side.
  const genuine = await (await fetch(`${baseUrl}/demo/run`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scenario: 'false_success' }) })).json();
  genuine.verification.verdict = 'PASS';
  await page.route('**/demo/run', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(genuine) }));
  const tampered = await runScenario('False success', 'false_success');
  check(tampered.status === 'Proof unavailable', `tampered result rendered ${tampered.status}`);
  await page.unroute('**/demo/run');

  await page.getByRole('button', { name: 'Restart', exact: true }).tap();
  check(await page.getByText('Confirmation required before anything runs').isVisible(), 'Restart did not return to the confirmation state');
  await page.locator('summary').first().scrollIntoViewIfNeeded();
  await page.locator('summary').first().tap();
  check(await page.locator('details').evaluate((d) => d.open), 'provenance disclosure did not open');

  const rejections = await page.evaluate(() => window.__unhandledRejections);
  const expectedNetworkErrors = consoleErrors.filter((e) => /Failed to load resource|net::ERR_FAILED|demo\/run/.test(e));
  const otherErrors = consoleErrors.filter((e) => !expectedNetworkErrors.includes(e));
  check(otherErrors.length === 0, `console errors: ${otherErrors.join(' | ')}`);
  check(rejections.length === 0, `unhandled rejections: ${rejections.join(' | ')}`);
} catch (error) {
  failures.push(`exception: ${String(error).slice(0, 300)}`);
} finally {
  await browser.close();
}

console.log(JSON.stringify({ engine: engineName, noDecompressionStream, posts, outcomes, failures }));
process.exit(failures.length === 0 ? 0 : 1);
