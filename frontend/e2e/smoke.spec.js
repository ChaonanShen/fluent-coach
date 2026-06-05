import { expect, test } from '@playwright/test';

test('starts a session, sends a fixture text turn, and ends with a summary', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByRole('combobox', { name: 'Scenario' })).toHaveValue('interview');
  await page.getByRole('button', { name: 'Start', exact: true }).click();
  await expect(page.getByText('Could you start by briefly introducing yourself?')).toBeVisible();

  await page.getByLabel('Your reply').fill(
    'Sure. I have three years of experience in backend development, mainly building APIs and data services.',
  );
  const aiMessages = page.locator('.message.ai');
  await expect(aiMessages).toHaveCount(1);
  await page.getByRole('button', { name: 'Send' }).click();
  await expect(aiMessages).toHaveCount(2, { timeout: 30_000 });
  await expect(aiMessages.nth(1).locator('p')).toContainText(/\S/);

  await page.getByRole('button', { name: 'End', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Summary' })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('button', { name: 'Start', exact: true })).toBeVisible();
});
