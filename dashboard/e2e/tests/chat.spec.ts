/**
 * Chat E2E Test
 * =============
 * Verifies the chat interface: sending a message, seeing the user bubble,
 * waiting for an assistant response, and verifying the stream starts.
 *
 * Scenario:
 *   1. Navigate to chat page
 *   2. Type a message and send it
 *   3. Verify user message bubble appears
 *   4. Verify assistant starts responding (typing indicator or response bubble)
 */

import { test, expect } from '@playwright/test';
import { DashboardPage } from '../pages/DashboardPage';

test.describe('Chat Interface', () => {
  let dashboard: DashboardPage;

  test.beforeEach(async ({ page }) => {
    await page.route(/\/v1\/chat\/completions$/, async route => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: [
          'data: {"choices":[{"delta":{"content":"deterministic E2E response"}}]}',
          'data: [DONE]',
          '',
        ].join('\n\n'),
      });
    });
    dashboard = new DashboardPage(page);
    await dashboard.goto();
    await dashboard.goToChat();
  });

  test('should display the chat input and send button', async () => {
    const textarea = dashboard.page.locator('textarea#chat-input');
    await expect(textarea).toBeVisible({ timeout: 5000 });
    await expect(textarea).toBeEnabled({ timeout: 5000 });
  });

  test('should send a message and show user bubble', async () => {
    const testMessage = 'Hello from E2E test!';
    await dashboard.sendChatMessageViaTextarea(testMessage);
    await dashboard.expectUserMessage(testMessage);
  });

  test('should show assistant response after sending a message', async () => {
    const testMessage = '간단한 인사 부탁해';
    await dashboard.sendChatMessageViaTextarea(testMessage);
    await dashboard.expectUserMessage(testMessage);

    const assistantRow = dashboard.page.locator('.message.assistant');
    await expect(assistantRow.first()).toBeVisible({ timeout: 15_000 });
    const text = await assistantRow.first().textContent();
    expect(text?.length).toBeGreaterThan(0);
  });

  test('should render the chat history panel button', async () => {
    const historyBtn = dashboard.page.locator('[aria-label="대화 기록 열기"]');
    await expect(historyBtn).toBeVisible({ timeout: 5000 });
    await expect(historyBtn).toBeEnabled();
  });

  test('should render the model selector', async () => {
    const modelSelector = dashboard.page.locator('.model-selector-wrap select, .model-selector-wrap [class*="select"]');
    await expect(modelSelector.first()).toBeVisible({ timeout: 5000 });
  });

  test('should send multiple lines via textarea', async () => {
    const message1 = '첫 번째 메시지';
    const message2 = '두 번째 메시지';

    await dashboard.sendChatMessageViaTextarea(message1);
    await dashboard.expectUserMessage(message1);
    await expect(dashboard.page.locator('.send-btn.sending')).toHaveCount(0);

    await dashboard.sendChatMessageViaTextarea(message2);
    await dashboard.expectUserMessage(message2);

    // Both user messages should be visible
    const userMessages = dashboard.page.locator('.message.user .bubble');
    const count = await userMessages.count();
    expect(count).toBeGreaterThanOrEqual(2);
  });

  test('should have the empty state before any messages', async () => {
    const hasBubbles = await dashboard.page.locator('.bubble').count();
    expect(hasBubbles).toBe(0);
  });
});
