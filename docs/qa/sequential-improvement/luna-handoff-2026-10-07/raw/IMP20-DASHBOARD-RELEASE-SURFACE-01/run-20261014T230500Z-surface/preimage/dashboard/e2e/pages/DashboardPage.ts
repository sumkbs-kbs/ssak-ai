/**
 * DashboardPage — Base Page Object Model for Ssak-Ai Dashboard E2E tests.
 *
 * Provides reusable selectors and actions for common dashboard interactions:
 * - Navigation via sidebar
 * - Command palette (Cmd+K)
 * - Chat input & message verification
 * - File explorer panel
 * - Git panel
 * - PIN modal handling
 * - Status / health checks
 *
 * Usage:
 *   const dashboard = new DashboardPage(page);
 *   await dashboard.goto();
 *   await dashboard.openCommandPalette();
 *   await dashboard.searchCommand('goal');
 */

import { type Locator, type Page, expect } from '@playwright/test';

type DashboardCredential =
  | { kind: 'none' }
  | { kind: 'legacyPin'; value: string }
  | { kind: 'token'; value: string };

export class DashboardPage {
  readonly page: Page;

  /* ─── Sidebar Navigation ─── */
  readonly sidebar: Locator;
  readonly navChat: Locator;
  readonly navWiki: Locator;
  readonly navAgent: Locator;
  readonly navSettings: Locator;
  readonly navGit: Locator;

  /* ─── Command Palette ─── */
  readonly commandPaletteButton: Locator;
  readonly commandPaletteOverlay: Locator;
  readonly commandPaletteInput: Locator;

  /* ─── Chat ─── */
  readonly chatInput: Locator;
  readonly chatSendButton: Locator;
  readonly chatMessages: Locator;

  /* ─── File Explorer ─── */
  readonly fileExplorer: Locator;
  readonly explorerTitle: Locator;
  readonly fileTree: Locator;
  readonly explorerRefreshBtn: Locator;

  /* ─── Git ─── */
  readonly gitPanel: Locator;
  readonly gitTabs: Locator;
  readonly gitTabStatus: Locator;
  readonly gitTabHistory: Locator;
  readonly gitTabBranches: Locator;
  readonly gitTabGraph: Locator;

  /* ─── PIN Modal ─── */
  readonly pinModal: Locator;
  readonly pinInput: Locator;
  readonly pinSubmit: Locator;

  /** Collected console errors for the current test. */
  consoleErrors: string[] = [];

  constructor(page: Page) {
    this.page = page;

    /* Sidebar */
    this.sidebar = page.locator('nav, .sidebar, [class*="sidebar"]');
    this.navChat = page.locator('a, button').filter({ hasText: /AI 채팅|Chat/ });
    this.navWiki = page.locator('a, button').filter({ hasText: /LLM Wiki|Wiki/ });
    this.navAgent = page.locator('a, button').filter({ hasText: /에이전트|Agent/ });
    this.navSettings = page.locator('a, button').filter({ hasText: /설정|Settings/ });
    this.navGit = page.locator('a, button').filter({ hasText: /Git/ });

    /* Command Palette */
    this.commandPaletteButton = page.locator(
      '[class*="palette"], button:has-text("명령"), [title*="Command"], [aria-label*="palette"]',
    );
    this.commandPaletteOverlay = page.locator('[class*="palette-overlay"], [class*="command-palette"]');
    this.commandPaletteInput = page.locator(
      '[class*="palette"] input, [class*="command-palette"] input, input[placeholder*="명령"], input[placeholder*="command"]',
    );

    /* Chat */
    this.chatInput = page.locator('textarea, [contenteditable="true"], input[type="text"]').first();
    this.chatSendButton = page.locator('button[type="submit"], button:has-text("전송"), button:has-text("Send")');
    this.chatMessages = page.locator('[class*="message"], [class*="bubble"], [class*="chat-message"]');

    /* File Explorer */
    this.fileExplorer = page.locator('.ide-explorer');
    this.explorerTitle = page.locator('.explorer-title');
    this.fileTree = page.locator('.file-tree');
    this.explorerRefreshBtn = page.locator('[aria-label="파일 트리 새로고침"]');

    /* Git */
    this.gitPanel = page.locator('.git-panel');
    this.gitTabs = page.locator('.git-tabs');
    this.gitTabStatus = page.locator('.git-tab').filter({ hasText: /Changes/ });
    this.gitTabHistory = page.locator('.git-tab').filter({ hasText: /History/ });
    this.gitTabBranches = page.locator('.git-tab').filter({ hasText: /Branches/ });
    this.gitTabGraph = page.locator('.git-tab').filter({ hasText: /Graph/ });

    /* PIN Modal */
    this.pinModal = page.locator('[role="dialog"][aria-label="PIN 인증"]');
    this.pinInput = page.locator('input[type="password"], input[placeholder*="PIN"], input[name="pin"]');
    this.pinSubmit = page.locator('button:has-text("잠금 해제"), button:has-text("확인"), button[type="submit"]');
  }

  /**
   * Start collecting console errors.
   * Call this in beforeEach() to capture all errors during the test.
   */
  startCollectingErrors(): void {
    this.consoleErrors = [];
    this.page.on('console', (msg) => {
      if (msg.type() === 'error' || msg.type() === 'warning') {
        this.consoleErrors.push(`[${msg.type()}] ${msg.text()}`);
      }
    });
  }

  /**
   * Assert that no console errors were collected during the test.
   * Call this in afterEach() after startCollectingErrors() was called in beforeEach().
   */
  expectNoConsoleErrors(): void {
    expect(this.consoleErrors).toEqual([]);
  }

  /* ═══════════════════════════════════════════════════════════════
     Navigation
     ═══════════════════════════════════════════════════════════════ */

  async goto(credential: DashboardCredential = { kind: 'none' }): Promise<void> {
    if (credential.kind === 'legacyPin') {
      await this.page.addInitScript(({ pin }) => {
        localStorage.setItem('ag_access_pin', pin);
      }, { pin: credential.value });
    } else if (credential.kind === 'token') {
      await this.page.addInitScript(({ token }) => {
        sessionStorage.setItem('ag_access_token', token);
      }, { token: credential.value });
    }
    await this.page.goto('/');
    await this.page.waitForLoadState('domcontentloaded');
  }

  async submitPin(pin: string): Promise<void> {
    await this.pinModal.waitFor({ state: 'visible', timeout: 3_000 });
    await this.pinInput.fill(pin);
    await this.pinSubmit.click();
  }

  /** Navigate directly to a page via real BrowserRouter pathname (UI-01: hash URL 제거). */
  async gotoPage(path: string): Promise<void> {
    await this.page.goto(`/${path.replace(/^\/+/, '')}`.replace(/\/$/, '') || '/');
    await this.page.waitForLoadState('domcontentloaded');
    await this.page.waitForTimeout(500);
  }

  /** Click the AI Chat nav link. Uses force click to handle overlay interception. */
  async goToChat(): Promise<void> {
    const target = this.navChat.first();
    await target.waitFor({ state: 'visible', timeout: 5000 });
    await target.click({ force: true });
    await this.page.waitForTimeout(800);
  }

  /** Click the Wiki nav link. Uses force click to handle overlay interception. */
  async goToWiki(): Promise<void> {
    const target = this.navWiki.first();
    await target.waitFor({ state: 'visible', timeout: 5000 });
    await target.click({ force: true });
    await this.page.waitForTimeout(800);
  }

  /** Click the Git nav link. Uses force click to handle overlay interception. */
  async goToGit(): Promise<void> {
    const target = this.navGit.first();
    await target.waitFor({ state: 'visible', timeout: 5000 });
    await target.click({ force: true });
    await this.page.waitForTimeout(800);
  }

  /* ═══════════════════════════════════════════════════════════════
     Command Palette
     ═══════════════════════════════════════════════════════════════ */

  async openCommandPalette(): Promise<void> {
    await this.page
      .getByRole('button', { name: '명령 팔레트 열기 (Cmd+K)' })
      .waitFor({ state: 'visible', timeout: 5_000 });
    await this.page.keyboard.press('ControlOrMeta+k');
    await this.page.waitForTimeout(300);
  }

  /** Type a query into the command palette search input. */
  async searchCommand(query: string): Promise<void> {
    await this.commandPaletteInput.waitFor({ state: 'visible', timeout: 3000 });
    await this.commandPaletteInput.fill(query);
  }

  /** Expect a command palette item with the given text to be visible. */
  async expectCommandItem(text: string): Promise<void> {
    const item = this.page
      .locator('[class*="palette"] a, [class*="palette"] li, [class*="command"]')
      .filter({ hasText: text });
    await expect(item.first()).toBeVisible({ timeout: 3000 });
  }

  /** Close the command palette by pressing Escape. */
  async closeCommandPalette(): Promise<void> {
    await this.page.keyboard.press('Escape');
    await this.page.waitForTimeout(200);
  }

  /* ═══════════════════════════════════════════════════════════════
     Chat
     ═══════════════════════════════════════════════════════════════ */

  /** Type a message into the chat input and send it. */
  async sendChatMessage(message: string): Promise<void> {
    await this.chatInput.waitFor({ state: 'visible', timeout: 5000 });
    await this.chatInput.fill(message);
    if (await this.chatSendButton.isVisible()) {
      await this.chatSendButton.click();
    } else {
      await this.page.keyboard.press('Enter');
    }
    await this.page.waitForTimeout(500);
  }

  /** Get the text content of all visible chat messages. */
  async getChatMessagesText(): Promise<string[]> {
    return this.chatMessages.allTextContents();
  }

  /** Expect a chat message bubble containing the given text to exist. */
  async expectChatMessage(text: string): Promise<void> {
    await expect(
      this.page.locator('[class*="message"], [class*="bubble"]').filter({ hasText: text }).first(),
    ).toBeVisible({ timeout: 10_000 });
  }

  /** Wait for a user message bubble with the given text. */
  async expectUserMessage(text: string): Promise<void> {
    const userMsg = this.page.locator('.message.user .bubble').filter({ hasText: text });
    await expect(userMsg.first()).toBeVisible({ timeout: 5000 });
  }

  /** Wait for an assistant response (any non-empty bubble) to appear. */
  async expectAssistantResponse(timeout = 15_000): Promise<void> {
    const assistantBubble = this.page.locator('.message.assistant .bubble');
    await expect(assistantBubble.first()).toBeVisible({ timeout });
  }

  /** Get the count of assistant messages in the chat. */
  async getAssistantMessageCount(): Promise<number> {
    return this.page.locator('.message.assistant').count();
  }

  /** Get the text of the last assistant message. */
  async getLastAssistantText(): Promise<string> {
    const bubbles = this.page.locator('.message.assistant .bubble');
    const count = await bubbles.count();
    if (count === 0) return '';
    return (await bubbles.nth(count - 1).textContent()) || '';
  }

  /** Send a chat message specifically using the #chat-input textarea and .send-btn. */
  async sendChatMessageViaTextarea(message: string): Promise<void> {
    const textarea = this.page.locator('textarea#chat-input');
    await textarea.waitFor({ state: 'visible', timeout: 5000 });
    await textarea.fill(message);
    const sendBtn = this.page.locator('.send-btn');
    if (await sendBtn.isVisible().catch(() => false)) {
      await sendBtn.click();
    } else {
      await this.page.keyboard.press('Enter');
    }
    await this.page.waitForTimeout(500);
  }

  /* ═══════════════════════════════════════════════════════════════
     File Explorer
     ═══════════════════════════════════════════════════════════════ */

  /** Expect the file explorer panel to be visible. */
  async expectFileExplorerVisible(): Promise<void> {
    await expect(this.fileExplorer.first()).toBeVisible({ timeout: 5000 });
    await expect(this.explorerTitle).toBeVisible({ timeout: 3000 });
  }

  /** Expect the file tree container to be rendered. */
  async expectFileTreeRendered(): Promise<void> {
    await expect(this.fileTree).toBeVisible({ timeout: 5000 });
  }

  /** Click the refresh button on the file explorer toolbar. */
  async clickExplorerRefresh(): Promise<void> {
    await this.explorerRefreshBtn.waitFor({ state: 'visible', timeout: 3000 });
    await this.explorerRefreshBtn.click();
    await this.page.waitForTimeout(500);
  }

  /* ═══════════════════════════════════════════════════════════════
     Git
     ═══════════════════════════════════════════════════════════════ */

  /** Expect the git page header to be visible. */
  async expectGitPageVisible(): Promise<void> {
    await expect(this.page.locator('.git-page-header')).toBeVisible({ timeout: 5000 });
  }

  /** Expect the git panel (with tabs) to be visible. */
  async expectGitPanelVisible(): Promise<void> {
    await expect(this.gitPanel.first()).toBeVisible({ timeout: 5000 });
  }

  /** Expect all four git tabs to be rendered. */
  async expectGitTabsVisible(): Promise<void> {
    await expect(this.gitTabs).toBeVisible({ timeout: 5000 });
    await expect(this.gitTabStatus).toBeVisible({ timeout: 3000 });
    await expect(this.gitTabHistory).toBeVisible({ timeout: 3000 });
    await expect(this.gitTabBranches).toBeVisible({ timeout: 3000 });
    await expect(this.gitTabGraph).toBeVisible({ timeout: 3000 });
  }

  /** Click a git tab by label. */
  async clickGitTab(label: 'Changes' | 'History' | 'Branches' | 'Graph'): Promise<void> {
    const tab = this.page.locator('.git-tab').filter({ hasText: label });
    await tab.waitFor({ state: 'visible', timeout: 3000 });
    await tab.click();
    await this.page.waitForTimeout(500);
  }

  /** Expect the given tab to be active. */
  async expectGitTabActive(label: string): Promise<void> {
    const activeTab = this.page.locator('.git-tab.active').filter({ hasText: label });
    await expect(activeTab).toBeVisible({ timeout: 3000 });
  }

  /** Expect git tab content area to be visible. */
  async expectGitContentVisible(): Promise<void> {
    const content = this.page.locator('.git-tab-content');
    await expect(content).toBeVisible({ timeout: 5000 });
  }

  /* ═══════════════════════════════════════════════════════════════
     PIN Modal
     ═══════════════════════════════════════════════════════════════ */

  /** Check if the PIN modal is currently visible. */
  async isPinModalVisible(): Promise<boolean> {
    return this.pinModal.isVisible().catch(() => false);
  }

  /* ═══════════════════════════════════════════════════════════════
     Health / Status
     ═══════════════════════════════════════════════════════════════ */

  /** Expect the page title to contain the app name. */
  async expectTitle(title = 'Ssak-Ai'): Promise<void> {
    await expect(this.page).toHaveTitle(new RegExp(title, 'i'));
  }

  /** Expect the main app container / root element to be present. */
  async expectAppRoot(): Promise<void> {
    await expect(this.page.locator('#app, #root, [class*="app"]').first()).toBeVisible({ timeout: 5000 });
  }
}
