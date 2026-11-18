import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { expect, Page } from '@playwright/test';

export const ANA = 'ana@leavedesk.test';
export const MO = 'mo@leavedesk.test';

/**
 * The demo users' password: from the DEMO_PASSWORD environment variable, or else from the
 * repository's .env file (one folder up). It is never written in the test code.
 */
export function demoPassword(): string {
  const fromEnv = process.env['DEMO_PASSWORD'];
  if (fromEnv) {
    return fromEnv;
  }
  const envFile = resolve(__dirname, '..', '..', '.env');
  if (existsSync(envFile)) {
    const line = readFileSync(envFile, 'utf8')
      .split('\n')
      .find((l) => l.startsWith('DEMO_PASSWORD='));
    if (line) {
      return line
        .slice('DEMO_PASSWORD='.length)
        .trim()
        .replace(/^["']|["']$/g, '');
    }
  }
  throw new Error('Set DEMO_PASSWORD, or run from the repository so ../.env can be read.');
}

/** Signs in through the login form and waits for My leave. */
export async function signIn(page: Page, email: string): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(demoPassword());
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(/\/leave$/);
}

/**
 * A Monday in a random week of 2030–2034, as MM/DD/YYYY for the date fields. A Monday is
 * always one working day, and a random week keeps repeated runs from overlapping.
 */
export function randomFutureMonday(): string {
  const firstMonday2030 = new Date(2030, 0, 7);
  const date = new Date(firstMonday2030);
  date.setDate(date.getDate() + 7 * Math.floor(Math.random() * 250));
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  return `${mm}/${dd}/${date.getFullYear()}`;
}

/** Reads one number from the balance card, e.g. balanceValue(page, 'ANNUAL', 'used'). */
export async function balanceValue(
  page: Page,
  leaveType: 'ANNUAL' | 'SICK' | 'CASUAL',
  column: 'used' | 'available',
): Promise<number> {
  const cell = page.getByTestId(`balance-${leaveType}`).getByTestId(column);
  await expect(cell).toBeVisible();
  return Number((await cell.textContent())?.trim());
}
