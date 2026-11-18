import AxeBuilder from '@axe-core/playwright';
import { expect, Page, test } from '@playwright/test';

import { ANA, MO, signIn } from './support';

/**
 * Automated accessibility check (UI_SPEC.md §8, UI-26, UI-27): axe-core with the WCAG 2.1
 * A and AA rules on each screen, at desktop width and at 375 px phone width. A screen fails
 * on any violation; the page must also never scroll sideways.
 */

async function expectAccessible(page: Page): Promise<void> {
  // Icons are a web font that loads only once an icon is on screen; wait for it, otherwise
  // axe would see the icon names ("notifications") as plain text.
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  const summary = results.violations.map((v) => `${v.id} (${v.impact}): ${v.help}`);
  expect(summary).toEqual([]);
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  const viewportWidth = page.viewportSize()?.width ?? 0;
  expect(scrollWidth).toBeLessThanOrEqual(viewportWidth);
}

for (const width of [1280, 375]) {
  test.describe(`at ${width} px`, () => {
    test.use({ viewport: { width, height: 900 } });

    test('login, My leave and Apply are accessible', async ({ page }) => {
      await page.goto('/login');
      await expect(page.getByLabel('Email')).toBeVisible();
      await expectAccessible(page);

      await signIn(page, ANA);
      await expect(page.getByTestId('balance-ANNUAL')).toBeVisible();
      await expectAccessible(page);

      await page.goto('/leave/apply');
      await expect(page.getByLabel('Reason')).toBeVisible();
      await expectAccessible(page);
    });

    test('Approvals and the notification panel are accessible', async ({ page }) => {
      await signIn(page, MO);
      await page.goto('/approvals');
      await expect(page.getByRole('heading', { name: 'Approvals' })).toBeVisible();
      await expectAccessible(page);

      await page.getByRole('button', { name: /^Notifications/ }).click();
      await expect(page.getByRole('dialog', { name: 'Notifications' })).toBeVisible();
      await expectAccessible(page);
      await page.keyboard.press('Escape');
      await expect(page.getByRole('dialog')).toHaveCount(0);
    });
  });
}
