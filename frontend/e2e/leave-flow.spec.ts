import { expect, test } from '@playwright/test';

import { ANA, balanceValue, MO, randomFutureMonday, signIn } from './support';

/**
 * Capstone 4 "Done when" (UI_SPEC.md §11): an employee applies, the manager approves, the
 * employee sees the approval notification arrive live and their balance change.
 * Runs against `docker compose up` (database, migrate, API, worker and web).
 */

test('the app and the API answer through nginx (UI-28)', async ({ page, request }) => {
  const health = await request.get('/api/health');
  expect(health.ok()).toBe(true);
  expect(await health.json()).toEqual({ status: 'ok' });

  await page.goto('/approvals');
  await expect(page).toHaveURL(/\/login\?returnUrl=%2Fapprovals$/);
});

test('employee applies, manager approves, employee sees the notification and the balance change', async ({
  browser,
}) => {
  const reason = `E2E annual leave ${Date.now()}`;
  const day = randomFutureMonday();

  // Two separate browser contexts = two people with their own sign-in.
  const anaContext = await browser.newContext();
  const moContext = await browser.newContext();
  const ana = await anaContext.newPage();
  const mo = await moContext.newPage();

  // 1. Ana signs in and notes her annual balance.
  await signIn(ana, ANA);
  const usedBefore = await balanceValue(ana, 'ANNUAL', 'used');
  const availableBefore = await balanceValue(ana, 'ANNUAL', 'available');
  expect(
    availableBefore,
    'Ana has no annual leave left. Reset the demo data: docker compose down -v && docker compose up -d --build --wait',
  ).toBeGreaterThanOrEqual(1);

  // 2. Ana applies for one day; it shows as pending and "available" drops by 1 (UI-14).
  await ana.getByRole('link', { name: 'Apply for leave' }).click();
  await ana.getByLabel('Leave type').click();
  await ana.getByRole('option', { name: 'Annual' }).click();
  await ana.getByLabel('Start date').fill(day);
  await ana.getByLabel('End date').fill(day);
  await ana.getByLabel('Reason').fill(reason);
  await ana.getByRole('button', { name: 'Submit' }).click();
  await expect(ana).toHaveURL(/\/leave$/);
  const anaRow = ana.getByRole('row').filter({ hasText: reason });
  await expect(anaRow.getByText('pending')).toBeVisible();
  await expect.poll(() => balanceValue(ana, 'ANNUAL', 'available')).toBe(availableBefore - 1);

  // 3. Mo signs in, opens Approvals (lazy-loaded, managers only) and approves it (UI-17, UI-18).
  await signIn(mo, MO);
  await mo.getByRole('link', { name: 'Approvals' }).first().click();
  const moRow = mo.getByRole('row').filter({ hasText: reason });
  await expect(moRow).toBeVisible();
  await moRow.getByRole('button', { name: /^Approve/ }).click();
  const dialog = mo.getByRole('dialog');
  await expect(dialog).toContainText('Approve 1 day(s) of annual leave for E-ANA');
  await dialog.getByRole('button', { name: 'Approve' }).click();
  await expect(moRow).toHaveCount(0);

  // 4. Without reloading, Ana gets the live notification (SSE), the bell counts it, and her
  //    annual "used" goes up by 1 (UI-22).
  await expect(
    ana.locator('mat-snack-bar-container').filter({ hasText: /was approved/ }),
  ).toBeVisible();
  await expect(ana.getByRole('button', { name: /^Notifications [1-9]\d* unread$/ })).toBeVisible();
  await expect.poll(() => balanceValue(ana, 'ANNUAL', 'used')).toBe(usedBefore + 1);
  await expect(anaRow.getByText('approved')).toBeVisible();

  // 5. Opening the bell lists the approval and marks everything read (UI-23).
  await ana.getByRole('button', { name: /^Notifications/ }).click();
  const panel = ana.getByRole('dialog', { name: 'Notifications' });
  await expect(panel.getByText(/was approved/).first()).toBeVisible();
  await expect(ana.getByRole('button', { name: 'Notifications 0 unread' })).toBeVisible();

  await anaContext.close();
  await moContext.close();
});
