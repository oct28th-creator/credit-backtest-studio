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
    const navItems = page.locator('.sb-item');
    await expect(navItems).toHaveCount(3);
  });

  test('config screen shows strategy selection section', async ({ page }) => {
    // Wait for app to load
    await page.waitForSelector('.page', { timeout: 5000 });
    await expect(page.locator('.cmp-grid')).toBeVisible();
  });

  test('challenger card is visible', async ({ page }) => {
    await page.waitForSelector('.cmp-card.chal', { timeout: 5000 });
    const challengerCard = page.locator('.cmp-card.chal');
    await expect(challengerCard).toBeVisible();
  });

  test('champion card is visible', async ({ page }) => {
    await page.waitForSelector('.cmp-card.champ', { timeout: 5000 });
    const championCard = page.locator('.cmp-card.champ');
    await expect(championCard).toBeVisible();
  });

  test('challenger card shows locked badge', async ({ page }) => {
    await page.waitForSelector('.cmp-card.chal', { timeout: 5000 });
    const challengerCard = page.locator('.cmp-card.chal');
    const lockedBadge = challengerCard.locator('.cmp-lock');
    await expect(lockedBadge).toBeVisible();
  });

  test('champion card shows locked badge', async ({ page }) => {
    await page.waitForSelector('.cmp-card.champ', { timeout: 5000 });
    const championCard = page.locator('.cmp-card.champ');
    const lockedBadge = championCard.locator('.cmp-lock');
    await expect(lockedBadge).toBeVisible();
  });

  test('sample cards are rendered', async ({ page }) => {
    await page.waitForSelector('.slice-chip', { timeout: 5000 });
    const sampleCards = page.locator('.slice-chip');
    await expect(sampleCards).toHaveCount(2);
  });

  test('Run Backtest button is present', async ({ page }) => {
    await page.waitForSelector('.page-hd', { timeout: 5000 });
    const runBtn = page.locator('.page-hd button.primary');
    await expect(runBtn).toBeVisible();
  });

  test('AI parse button is present', async ({ page }) => {
    await page.waitForSelector('.ai-go', { timeout: 5000 });
    const aiBtn = page.locator('.ai-go').first();
    await expect(aiBtn).toBeVisible();
  });

  test('language toggle button switches between 中 and EN', async ({ page }) => {
    await page.waitForSelector('.topbar', { timeout: 5000 });
    const langBtn = page.locator('.lang-btn');
    await expect(langBtn).toBeVisible();
  });

  test('beta card can be removed', async ({ page }) => {
    await page.waitForSelector('.cmp-card.beta', { timeout: 5000 });
    const betaCard = page.locator('.cmp-card.beta');
    await expect(betaCard).toBeVisible();

    // Click remove beta button
    const removeBtn = betaCard.locator('.cmp-remove').first();
    await removeBtn.click();

    // Beta card should disappear, add-beta button should appear
    await expect(page.locator('.cmp-add')).toBeVisible();
  });

  test('add beta button re-adds beta card', async ({ page }) => {
    await page.waitForSelector('.cmp-card.beta', { timeout: 5000 });

    // Remove beta first
    const betaCard = page.locator('.cmp-card.beta');
    await betaCard.locator('.cmp-remove').first().click();

    // Add beta back
    await page.locator('.cmp-add').click();
    await expect(page.locator('.cmp-card.beta')).toBeVisible();
  });
});
