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

test('keyboard navigation and accessible controls', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');

  // Tab through header controls
  await page.keyboard.press('Tab');
  const focusedTag = await page.evaluate(() => document.activeElement?.tagName);
  expect(['SELECT', 'BUTTON', 'A', 'INPUT']).toContain(focusedTag);

  // Switch to English via welcome language selector
  await page.locator('#welcome-language').selectOption('en');
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');

  // Navigate to farmer mode
  await login(page, 'ramesh');
  await expect(page.getByRole('heading', { name: 'What is happening in your crop?' })).toBeVisible();

  // Delete speech recognition API on window to test unsupported browser fallback
  await page.evaluate(() => {
    delete window.SpeechRecognition;
    delete window.webkitSpeechRecognition;
  });
  await page.getByRole('button', { name: 'Record a short question' }).click();
  const voiceNotice = page.getByText('Browser speech input is unavailable here. You can type your question instead.');
  await expect(voiceNotice).toBeVisible();

  // Check 200% zoom text scaling resilience
  await page.evaluate(() => {
    document.documentElement.style.fontSize = '32px'; // Simulates 200% text zoom
  });
  await expectNoHorizontalOverflow(page);

  // Reset zoom
  await page.evaluate(() => {
    document.documentElement.style.fontSize = '';
  });

  // Verify image upload validation for invalid file type
  const buffer = Buffer.from('This is a text file, not an image.', 'utf-8');
  await page.locator('#photo-input').setInputFiles({
    name: 'document.txt',
    mimeType: 'text/plain',
    buffer,
  });
  await page.getByRole('textbox', { name: 'Your question', exact: true }).fill('Testing file rejection');
  await page.getByRole('button', { name: 'Get careful guidance' }).click();

  // Expect error notice to appear and inform user
  const errorNotice = page.locator('.notice-error');
  await expect(errorNotice).toBeVisible({ timeout: 10_000 });
  await expect(errorNotice).toContainText(/image/i);

  // Run accessibility check on the error state
  await expectNoA11yViolations(page, 'farmer workspace with error notice');
});
