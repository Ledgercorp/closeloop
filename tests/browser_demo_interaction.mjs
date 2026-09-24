// Exercise the persistent-resolution page in a real browser. The legacy browser test
// covered a dashboard that no longer serves as /demo/ after the product evolution.
import { createRequire } from 'node:module';
import { execSync } from 'node:child_process';

const require = createRequire(import.meta.url);
function loadPlaywright() {
  for (const candidate of [process.env.PLAYWRIGHT_MODULE, 'playwright'].filter(Boolean)) {
    try {
      return require(candidate);
    } catch {
      // Try the next installed location.
    }
  }
  const globalRoot = execSync('npm root -g', { stdio: ['ignore', 'pipe', 'ignore'] })
    .toString().trim();
  return require(globalRoot + '/playwright');
}

const args = process.argv.slice(2);
const probe = args.includes('--probe');
const noDecompressionStream = args.includes('--no-decompression-stream');
const positional = args.filter((arg) => !arg.startsWith('--'));
const engineName = positional.find((arg) => arg === 'chromium' || arg === 'webkit') || 'chromium';
const baseUrl = positional.find((arg) => /^https?:\/\//.test(arg));
const playwright = loadPlaywright();
const engine = playwright[engineName];

if (probe) {
  const browser = await engine.launch();
  const version = browser.version();
  await browser.close();
  console.log(JSON.stringify({ engine: engineName, version }));
  process.exit(0);
}
if (!baseUrl) {
  console.error('base URL required');
  process.exit(2);
}

const failures = [];
const check = (condition, message) => {
  if (!condition) failures.push(message);
};
const posts = [];
const outcomes = [];
const consoleErrors = [];
const browser = await engine.launch();
const context = await browser.newContext({
  viewport: { width: 390, height: 844 },
  locale: 'en-US',
  hasTouch: true,
  isMobile: true,
});
const page = await context.newPage();
page.on('request', (request) => {
  if (request.url().endsWith('/demo/run')) {
    posts.push({ method: request.method(), body: request.postData() });
  }
});
page.on('pageerror', (error) => consoleErrors.push(String(error).slice(0, 240)));
await page.addInitScript((strip) => {
  if (strip) {
    try {
      Object.defineProperty(window, 'DecompressionStream', {
        configurable: true,
        value: undefined,
      });
    } catch {
      // The current page does not depend on this browser API.
    }
  }
}, noDecompressionStream);

async function runScenario(buttonSelector, scenario, expectedState, expectedVerdict) {
  const before = posts.length;
  const responsePromise = page.waitForResponse((response) =>
    response.url().endsWith('/demo/run') && response.request().method() === 'POST'
  );
  await page.locator(buttonSelector).click();
  const response = await responsePromise;
  const payload = await response.json();
  await page.locator('#outcome:not([hidden])').waitFor();

  check(response.status() === 200, scenario + ': API returned ' + response.status());
  check(payload.server_generated === true, scenario + ': result was not server-generated');
  check(payload.scenario === scenario, scenario + ': response scenario did not match');
  check(payload.resolution.lifecycle_state === expectedState, scenario + ': wrong lifecycle state');
  check(payload.verification.verdict === expectedVerdict, scenario + ': wrong verifier outcome');
  check(posts.length === before + 1, scenario + ': expected exactly one API request');
  const body = JSON.parse(posts[before]?.body || '{}');
  check(
    JSON.stringify(Object.keys(body).sort()) === JSON.stringify(['scenario']),
    scenario + ': browser submitted fields beyond the scenario selector'
  );
  outcomes.push({
    scenario,
    state: payload.resolution.lifecycle_state,
    verdict: payload.verification.verdict,
    consumerState: payload.verification.consumer_state,
  });
  return payload;
}

try {
  const url = baseUrl.replace(/\/$/, '') + '/demo/';
  const response = await page.goto(url, { waitUntil: 'load' });
  check(response?.status() === 200, 'GET /demo/ did not return 200');
  check(
    await page.getByText('Waiting confirmation', { exact: false }).isVisible(),
    'initial confirmation gate is not visible'
  );
  check(posts.length === 0, 'a cancellation request ran before confirmation');
  check(
    await page.evaluate(() => typeof window.DecompressionStream === 'undefined') ===
      noDecompressionStream,
    'browser capability setup did not take effect'
  );

  for (const width of [390, 820, 1280]) {
    await page.setViewportSize({ width, height: 844 });
    await page.waitForTimeout(40);
    const metrics = await page.evaluate(() => ({
      viewport: window.innerWidth,
      document: document.documentElement.scrollWidth,
    }));
    check(
      metrics.document <= metrics.viewport + 1,
      'horizontal overflow at ' + width + 'px: ' + JSON.stringify(metrics)
    );
  }

  const verified = await runScenario('#run', 'persistent_resolution', 'VERIFIED', 'PASS');
  check(verified.lifecycle_story.length >= 6, 'persistent story is missing lifecycle scenes');
  check(
    verified.lifecycle_story.some((scene) => scene.session === 'Later session'),
    'same resolution was not retrieved in a later session'
  );
  check(
    verified.lifecycle_story
      .filter((scene) => scene.resolution_id)
      .every((scene) => scene.resolution_id === verified.resolution.resolution_id),
    'later-session evidence refers to another resolution'
  );
  check(verified.execution_claim.request_reference.length > 0, 'execution claim is missing');
  check(verified.verification_history.length > 0, 'verification history is missing');
  await page.locator('#proof summary').click();
  check(await page.locator('#proof').evaluate((element) => element.open), 'proof disclosure did not open');
  check(
    (await page.locator('#proof-data').innerText()).includes('verification_history'),
    'proof disclosure omitted verification history'
  );

  const failed = await runScenario('#failure', 'terminal_failure', 'NOT_COMPLETED', 'FAIL');
  check(
    failed.independent_read_back.account_readable === true &&
      failed.independent_read_back.auto_renew === true,
    'Not completed did not have fresh readable contradictory evidence'
  );

  const unknown = await runScenario('#outage', 'evidence_outage', 'AWAITING_PROOF', 'INCONCLUSIVE');
  check(unknown.resolution.is_terminal === false, 'evidence outage became terminal');
  check(unknown.resolution.next_check_at !== null, 'evidence outage lost its next-check metadata');
  check(
    unknown.independent_read_back.account_readable === false,
    'evidence outage was not represented as unavailable'
  );
  check(posts.every((post) => post.method === 'POST'), 'browser used an unexpected HTTP method');
  check(consoleErrors.length === 0, 'browser runtime errors: ' + consoleErrors.join(' | '));
} catch (error) {
  failures.push('exception: ' + String(error).slice(0, 300));
} finally {
  await browser.close();
}

console.log(JSON.stringify({ engine: engineName, noDecompressionStream, posts, outcomes, failures }));
process.exit(failures.length === 0 ? 0 : 1);
