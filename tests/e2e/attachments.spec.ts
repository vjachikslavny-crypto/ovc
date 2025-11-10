// Placeholder Playwright spec for future automation.
// Describes the two target scenarios from the roadmap:
// 1) drag-and-drop PNG inserts image block with preview and focal hint.
// 2) uploading PDF shows doc card with page count info and working link.

import { test, expect } from '@playwright/test';

test.describe.skip('Attachments flow (skeleton)', () => {
  test('dragging an image creates an image block', async ({ page }) => {
    await page.goto('/notes');
    // TODO: Implement once Playwright harness is wired into the project.
    expect(true).toBeTruthy();
  });

  test('uploading a PDF renders doc preview', async ({ page }) => {
    await page.goto('/notes');
    // TODO: Implement PDF viewer assertions.
    expect(true).toBeTruthy();
  });
});
