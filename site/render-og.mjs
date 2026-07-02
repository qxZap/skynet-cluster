// Render og.html to og.png (1200x630) with headless Chromium via Playwright.
// Run in CI before deploying the site; the PNG is what link-preview crawlers fetch.
import { chromium } from 'playwright';
import { fileURLToPath } from 'url';
import path from 'path';

const dir = path.dirname(fileURLToPath(import.meta.url));
const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1200, height: 630 },
  deviceScaleFactor: 2, // crisp on retina; OG crawlers accept the larger pixel size
});
await page.goto('file://' + path.join(dir, 'og.html'));
await page.waitForTimeout(500); // let webfonts settle
await page.screenshot({ path: path.join(dir, 'og.png') });
await browser.close();
console.log('wrote og.png');
