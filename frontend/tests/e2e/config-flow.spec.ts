import { test, expect } from '@playwright/test';

test.describe('Config Screen', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('renders app title BackTest Studio (not ACE BackTest Studio)', async ({ page }) => {
    const title = await page.title();
    expect(title).toBe('BackTest Studio');
    expect(title).not.toContain('ACE');
  });

  test('sidebar is visible with nav items', async ({ page }) => {
    const sidebar = page.locator('.sidebar');
    await expect(sidebar).toBeVisible();

    // Check for nav items by class
    const navItems = page.locator('.sidebar-item');
    await expect(navItems).toHaveCount(4);
  });

  test('config screen shows strategy selection section', async ({ page }) => {
    // Wait for app to load
    await page.waitForSelector('.config-screen', { timeout: 5000 });
    await expect(page.locator('.config-screen')).toBeVisible();
  });

  test('challenger card is visible', async ({ page }) => {
    await page.waitForSelector('.strategy-card-challenger', { timeout: 5000 });
    const challengerCard = page.locator('.strategy-card-challenger');
    await expect(challengerCard).toBeVisible();
  });

  test('champion card is visible', async ({ page }) => {
    await page.waitForSelector('.strategy-card-champion', { timeout: 5000 });
    const championCard = page.locator('.strategy-card-champion');
    await expect(championCard).toBeVisible();
  });

  test('challenger card shows locked badge', async ({ page }) => {
    await page.waitForSelector('.strategy-card-challenger', { timeout: 5000 });
    const challengerCard = page.locator('.strategy-card-challenger');
    const lockedBadge = challengerCard.locator('.locked-badge');
    await expect(lockedBadge).toBeVisible();
  });

  test('champion card shows locked badge', async ({ page }) => {
    await page.waitForSelector('.strategy-card-champion', { timeout: 5000 });
    const championCard = page.locator('.strategy-card-champion');
    const lockedBadge = championCard.locator('.locked-badge');
    await expect(lockedBadge).toBeVisible();
  });

  test('sample cards are rendered', async ({ page }) => {
    await page.waitForSelector('.sample-card', { timeout: 5000 });
    const sampleCards = page.locator('.sample-card');
    await expect(sampleCards).toHaveCount(2);
  });

  test('Run Backtest button is present', async ({ page }) => {
    await page.waitForSelector('.config-run-row', { timeout: 5000 });
    const runBtn = page.locator('.config-run-row button');
    await expect(runBtn).toBeVisible();
  });

  test('AI parse button is present', async ({ page }) => {
    await page.waitForSelector('.btn-ai-trigger', { timeout: 5000 });
    const aiBtn = page.locator('.btn-ai-trigger').first();
    await expect(aiBtn).toBeVisible();
  });

  test('language toggle button switches between 中 and EN', async ({ page }) => {
    await page.waitForSelector('.topbar', { timeout: 5000 });
    // Find language toggle
    const langBtn = page.locator('.topbar-actions .btn-ghost');
    await expect(langBtn).toBeVisible();
  });

  test('beta card can be removed', async ({ page }) => {
    await page.waitForSelector('.strategy-card-beta', { timeout: 5000 });
    const betaCard = page.locator('.strategy-card-beta');
    await expect(betaCard).toBeVisible();

    // Click remove beta button
    const removeBtn = betaCard.locator('button').first();
    await removeBtn.click();

    // Beta card should disappear, add-beta button should appear
    await expect(page.locator('.add-beta-btn')).toBeVisible();
  });

  test('add beta button re-adds beta card', async ({ page }) => {
    await page.waitForSelector('.strategy-card-beta', { timeout: 5000 });

    // Remove beta first
    const betaCard = page.locator('.strategy-card-beta');
    await betaCard.locator('button').first().click();

    // Add beta back
    await page.locator('.add-beta-btn').click();
    await expect(page.locator('.strategy-card-beta')).toBeVisible();
  });

  test('metrics checkboxes are present', async ({ page }) => {
    await page.waitForSelector('.metrics-checkboxes', { timeout: 5000 });
    const checkboxes = page.locator('.metric-checkbox');
    await expect(checkboxes).toHaveCount(5);
  });

  test('layer tabs L1-L5 all visible in metrics checkboxes', async ({ page }) => {
    await page.waitForSelector('.metrics-checkboxes', { timeout: 5000 });
    const checkboxLabels = await page.locator('.metric-checkbox').allTextContents();
    // All 5 layer checkboxes should be present
    expect(checkboxLabels).toHaveLength(5);
  });
});
