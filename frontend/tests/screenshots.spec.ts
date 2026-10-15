import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const SCREENSHOT_DIR = path.join(__dirname, '..', 'artifacts', 'screenshots');

test.describe('BranchSleuth Screenshots', () => {
  test.beforeAll(() => {
    if (!fs.existsSync(SCREENSHOT_DIR)) {
      fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
    }
  });

  test('01-dashboard', async ({ page }) => {
    await page.goto('http://localhost:3000');
    await page.waitForLoadState('networkidle');
    // Wait for dashboard content to load (repositories and analyses lists)
    await page.waitForSelector('h1:has-text("Dashboard")', { timeout: 30000 });
    await page.waitForSelector('.panel', { timeout: 30000 });
    // Wait for any loading spinners to disappear
    await page.waitForFunction(() => !document.querySelector('.animate-spin'), { timeout: 30000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '01-dashboard.png'), fullPage: true });
  });

  test('02-repositories', async ({ page }) => {
    await page.goto('http://localhost:3000/repositories');
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('h1:has-text("Repositories")', { timeout: 30000 });
    await page.waitForSelector('.panel', { timeout: 30000 });
    await page.waitForFunction(() => !document.querySelector('.animate-spin'), { timeout: 30000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '02-repositories.png'), fullPage: true });
  });

  test('03-new-analysis', async ({ page }) => {
    await page.goto('http://localhost:3000/analyses/new');
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('h1:has-text("New analysis")', { timeout: 30000 });
    // Wait for repository dropdown to be populated (not showing "Loading...")
    await page.waitForFunction(() => {
      const select = document.querySelector('select[required]') as HTMLSelectElement | null;
      return select && select.options.length > 1;
    }, { timeout: 30000 });
    await page.waitForFunction(() => !document.querySelector('.animate-spin'), { timeout: 30000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '03-new-analysis.png'), fullPage: true });
  });

  test('04-analysis-results', async ({ page }) => {
    await page.goto('http://localhost:3000/analyses/b357d154-d42b-4978-b05c-4c60238d2b44');
    await page.waitForLoadState('networkidle');
    // The h1 shows the repository name "tinyshop" not "Analysis"
    await page.waitForSelector('h1', { timeout: 30000 });
    await page.waitForSelector('.panel', { timeout: 30000 });
    await page.waitForFunction(() => !document.querySelector('.animate-spin'), { timeout: 30000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '04-analysis-results.png'), fullPage: true });
  });

  test('05-evidence-graph', async ({ page }) => {
    await page.goto('http://localhost:3000/analyses/b357d154-d42b-4978-b05c-4c60238d2b44');
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('h1', { timeout: 30000 });
    await page.waitForFunction(() => !document.querySelector('.animate-spin'), { timeout: 30000 });
    await page.waitForSelector('text=Evidence graph', { timeout: 10000 });
    await page.locator('nav[role="tablist"] button:has-text("Evidence graph")').click();
    // Wait for React Flow to render
    await page.waitForSelector('.react-flow', { timeout: 15000 });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '05-evidence-graph.png'), fullPage: true });
  });

  test('06-verification-details', async ({ page }) => {
    await page.goto('http://localhost:3000/analyses/b357d154-d42b-4978-b05c-4c60238d2b44');
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('h1', { timeout: 30000 });
    await page.waitForFunction(() => !document.querySelector('.animate-spin'), { timeout: 30000 });
    await page.waitForSelector('text=Verifications', { timeout: 10000 });
    await page.locator('nav[role="tablist"] button:has-text("Verifications")').click();
    await page.waitForTimeout(1000);
    await page.getByRole('button', { name: 'Show details' }).click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '06-verification-details.png'), fullPage: true });
  });

  test('07-regression-evidence', async ({ page }) => {
    await page.goto('http://localhost:3000/analyses/b357d154-d42b-4978-b05c-4c60238d2b44');
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('h1', { timeout: 30000 });
    await page.waitForFunction(() => !document.querySelector('.animate-spin'), { timeout: 30000 });
    await page.waitForSelector('text=Changed code', { timeout: 10000 });
    await page.locator('nav[role="tablist"] button:has-text("Changed code")').click();
    await page.waitForTimeout(500);
    await page.selectOption('select', 'c275ec24-e9c6-4830-9ae1-5153c5055e47');
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '07-regression-evidence.png'), fullPage: true });
  });
});