import { expect, test } from '@playwright/test';

test('starts a session, sends a fixture text turn, and ends with a summary', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByRole('combobox', { name: 'Scenario' })).toHaveValue('interview');
  const briefingToggle = page.getByRole('button', { name: 'Scenario Briefing' });
  await expect(briefingToggle).toHaveAttribute('aria-expanded', 'true');
  await page.getByLabel('Known background').fill('Backend engineer with API platform experience.');
  await briefingToggle.click();
  await expect(briefingToggle).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByLabel('Known background')).toBeHidden();
  await page.getByRole('button', { name: 'Start', exact: true }).click();
  await expect(page.getByText(/I reviewed the background you shared/)).toBeVisible();

  await page.getByLabel('Your reply').fill(
    'Sure. I have three years of experience in backend development, mainly building APIs and data services.',
  );
  const aiMessages = page.locator('.message.ai');
  await expect(aiMessages).toHaveCount(1);
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(aiMessages).toHaveCount(2, { timeout: 30_000 });
  await expect(aiMessages.nth(1).locator('p')).toContainText(
    'Great. Which project from that experience is most relevant to this role?',
    { timeout: 30_000 },
  );
  const hasHorizontalScroll = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(hasHorizontalScroll).toBe(false);

  await page.getByRole('button', { name: 'End', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Summary' })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('button', { name: 'New conversation', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'New conversation', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Start', exact: true })).toBeVisible();
  await expect(page.getByLabel('Your reply')).toBeDisabled();
  await expect(briefingToggle).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByLabel('Known background')).toHaveValue('');
});
