import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { login } from './login.js';

async function expectNoA11yViolations(page, view) {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  const summary = results.violations.map((violation) => ({
    id: violation.id,
    impact: violation.impact,
    nodes: violation.nodes.map((node) => ({ target: node.target, message: node.any?.[0]?.message || node.failureSummary })),
  }));
  expect(summary, `${view} accessibility violations`).toEqual([]);
}

async function expectNoHorizontalOverflow(page) {
  const overflows = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflows, 'the current view should fit the viewport width').toBe(false);
}

async function expectNoDeveloperUiText(page) {
  const visibleText = await page.locator('body').innerText();
  expect(visibleText).not.toMatch(/API documentation|\badapter\b|receipt id|case id|gemini-\d[\w.-]*/i);
}

test('farmer question reaches officer review and the matching regional farmer feed', async ({ page }) => {
  const farmerQuestion = `Several lower rice leaves changed color this week. What should I observe next? Ref ${Date.now().toString(36)}.`;
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'మీ పొలానికి తదుపరి అడుగు స్పష్టంగా.' })).toBeVisible();
  console.log('E2E checkpoint: welcome rendered');
  await page.locator('#language-select').selectOption('en');
  await expect(page.getByRole('heading', { name: 'A clearer next step for your field.' })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expectNoA11yViolations(page, 'welcome');
  console.log('E2E checkpoint: welcome accessibility scan passed');

  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expectNoDeveloperUiText(page);
  await login(page, 'ramesh');
  await expect(page.getByRole('heading', { name: 'What is happening in your crop?' })).toBeVisible();
  await expectNoDeveloperUiText(page);
  await page.getByRole('radio', { name: 'Select field: Nalgonda · Rice · Kharif' }).check();
  console.log('E2E checkpoint: farmer workspace rendered');
  await expect(page.locator('.weather-primary')).toHaveCount(0);
  await expect(page.getByText('No live weather reading is connected. Historical values were not substituted.')).toHaveCount(0);
  await expect(page.getByText('A practice to discuss')).toHaveCount(0);
  await expectNoHorizontalOverflow(page);
  await expectNoA11yViolations(page, 'farmer workspace');
  console.log('E2E checkpoint: farmer accessibility scan passed');

  await page.getByRole('textbox', { name: 'Your question', exact: true }).fill(farmerQuestion);
  await page.getByRole('button', { name: 'Get careful guidance' }).click();
  await expect(page.getByRole('status')).toContainText('Your answer is saved.', { timeout: 55_000 });
  await expect(page.locator('.case-panel .case-summary')).toBeVisible();
  const recentQuestion = page.locator('.case-list-item').filter({ hasText: farmerQuestion });
  await expect(recentQuestion).toContainText('Rice');
  await expect(recentQuestion).toContainText('Nalgonda');
  await expect(recentQuestion).toContainText('Kharif');
  await expect(recentQuestion).toContainText('AI guidance unavailable');
  console.log('E2E checkpoint: farmer case saved');
  await expect(page.getByRole('button', { name: 'Want professional help? Contact an officer' })).toBeVisible();
  await expect(page.locator('.case-panel .status-chip')).not.toContainText('Waiting for officer');
  await page.getByRole('button', { name: 'Want professional help? Contact an officer' }).click();
  await page.getByLabel('Your name').fill('Demo Farmer');
  await page.getByLabel('Phone number').fill('9876543210');
  await page.getByLabel(/I agree to share my contact details/).check();
  await page.getByRole('button', { name: 'Send request to officer' }).click();
  await expect(page.getByRole('status')).toContainText('Your request was sent to the officer queue.');
  await expect(page.locator('.case-panel')).toContainText('Waiting for officer');
  console.log('E2E checkpoint: explicit contact request submitted');

  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await login(page, 'rajesh');
  await expect(page.getByRole('heading', { name: 'Cases that need a human check.' })).toBeVisible();
  await expectNoDeveloperUiText(page);
  console.log('E2E checkpoint: officer workspace rendered');
  await expect(page.getByRole('heading', { name: 'Publish a scoped advisory' })).toBeVisible();
  await expect(page.getByLabel('Advisory title')).toHaveCount(0);
  await page.getByRole('button', { name: 'Go to Card 03: Publish a scoped advisory' }).click();
  await expect(page.locator('.publish-panel')).toBeFocused();
  await expect(page.locator('.officer-case-panel').getByText(farmerQuestion)).toBeVisible();
  await expect(page.locator('.officer-case-panel').getByText('Demo Farmer')).toBeVisible();
  await expect(page.locator('.officer-case-panel').getByText('9876543210')).toBeVisible();
  await expect(page.locator('.officer-case-panel').getByRole('heading', { name: 'A possible explanation, not a diagnosis' })).toHaveCount(0);
  await expect(page.locator('.officer-case-panel').getByRole('heading', { name: 'Evidence and source limits' })).toHaveCount(0);
  await expect(page.locator('.officer-case-panel')).not.toContainText('AI guidance is unavailable');
  await expect(page.getByRole('heading', { name: 'AI response', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Accept AI response', exact: true })).toHaveCount(0);
  await expectNoHorizontalOverflow(page);
  await expectNoA11yViolations(page, 'officer workspace');
  console.log('E2E checkpoint: officer accessibility scan passed');

  await page.getByRole('button', { name: 'Write officer response', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Send officer response', exact: true })).toBeDisabled();
  await page.getByLabel('Officer response', { exact: true }).fill('Ask the farmer for a dated field photo.');
  await page.getByRole('button', { name: 'Send officer response', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Publish a scoped advisory' })).toBeVisible();
  console.log('E2E checkpoint: officer approval recorded');
  await expect(page.getByLabel('Advisory title')).toBeVisible();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await login(page, 'ramesh');
  await expect(page.locator('.case-panel')).toContainText('Ask the farmer for a dated field photo.');
  await expect(page.locator('.case-list-item').filter({ hasText: farmerQuestion })).toContainText('Approved for follow-up');
  console.log('E2E checkpoint: officer response reached farmer');
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await login(page, 'rajesh');
  await expect(page.getByRole('heading', { name: 'Publish a scoped advisory' })).toBeVisible();
  await page.getByRole('button', { name: 'Insert a cautious draft' }).click();
  // Base 36 avoids a long digit run that the public-text privacy guard treats as a phone number.
  const advisoryTitle = `Rice field observations in Nalgonda ${Date.now().toString(36)}`;
  await page.getByLabel('Advisory title').fill(advisoryTitle);
  await page.getByRole('button', { name: 'Publish to matching farmers' }).click();
  await expect(page.getByRole('status')).toContainText('Advisory published for matching farmers in Telangana and Andhra Pradesh.');
  console.log('E2E checkpoint: advisory published');
  await expect(page.getByRole('button', { name: /adapter/i })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'API documentation' })).toHaveCount(0);
  await expect(page.locator('.receipts-panel')).toContainText(advisoryTitle);
  await expectNoDeveloperUiText(page);
  console.log('E2E checkpoint: advisory shared automatically');

  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await login(page, 'lakshmi');
  await expect(page.getByRole('heading', { name: 'What is happening in your crop?' })).toBeVisible();
  await expectNoDeveloperUiText(page);
  console.log('E2E checkpoint: receiving farmer workspace rendered');
  const receivedAdvisory = page.locator('.feed-list li').filter({ hasText: advisoryTitle });
  await expect(receivedAdvisory.getByText(advisoryTitle)).toBeVisible();
  await expect(receivedAdvisory.getByText('Regional share')).toBeVisible();
  await page.getByRole('radio', { name: 'Select field: Krishna · Maize · Kharif' }).check();
  await expect(page.locator('.feed-list li').filter({ hasText: advisoryTitle })).toHaveCount(0);
  await page.getByRole('radio', { name: 'Select field: Krishna · Rice · Kharif' }).check();
  await page.getByRole('button', { name: 'Refresh advisories', exact: true }).click();
  await expect(page.locator('.feed-list li').filter({ hasText: advisoryTitle })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await login(page, 'priya');
  await expect(page.locator('.receipts-panel')).toContainText(advisoryTitle);
  await expectNoDeveloperUiText(page);
  await expect(page.locator('.officer-case-panel').getByText(farmerQuestion)).toHaveCount(0);
  await expectNoA11yViolations(page, 'Andhra Pradesh officer');
  console.log('E2E checkpoint: end-to-end journey completed at mobile width');
});
