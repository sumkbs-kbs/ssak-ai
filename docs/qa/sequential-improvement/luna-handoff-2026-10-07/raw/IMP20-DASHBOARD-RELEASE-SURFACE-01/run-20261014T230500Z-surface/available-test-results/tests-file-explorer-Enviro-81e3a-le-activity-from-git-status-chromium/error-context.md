# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: tests/file-explorer.spec.ts >> Environment Rail — file browsing >> should show file activity from git status
- Location: e2e/tests/file-explorer.spec.ts:44:3

# Error details

```
TimeoutError: locator.waitFor: Timeout 5000ms exceeded.
Call log:
  - waiting for locator('a, button').filter({ hasText: /AI 채팅|Chat/ }).first() to be visible

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - banner "시스템 상태" [ref=e4]:
    - generic [ref=e5]: 워크스페이스
    - group [ref=e6]:
      - generic "서버 연결 및 시스템 지표" [ref=e7] [cursor=pointer]:
        - generic [ref=e9]: 서버
        - generic [ref=e10]: LIVE · 3s ago
  - generic [ref=e13]:
    - complementary "SSAK-AI 탐색" [ref=e15]:
      - generic [ref=e16]: SSAK-AI
      - region "프로젝트와 대화 탐색" [ref=e18]:
        - navigation "주요 메뉴" [ref=e19]:
          - button "새 채팅" [ref=e20] [cursor=pointer]
          - button "검색 ⌘K" [ref=e24] [cursor=pointer]:
            - generic [ref=e27]: 검색
            - generic [ref=e28]: ⌘K
          - link "대화" [ref=e29] [cursor=pointer]:
            - /url: /chat
          - link "스튜디오" [ref=e33] [cursor=pointer]:
            - /url: /studio
          - link "모델" [ref=e37] [cursor=pointer]:
            - /url: /models
          - group [ref=e41]:
            - generic "더 보기" [ref=e42] [cursor=pointer]
        - region [ref=e48]:
          - generic [ref=e49]:
            - heading "프로젝트" [level=2] [ref=e50]
            - button "새 프로젝트 추가" [ref=e51] [cursor=pointer]
          - list [ref=e54]:
            - listitem [ref=e55]:
              - generic [ref=e56]:
                - button "agk-ambient-gate-85hvkudx 프로젝트 펼치기" [ref=e57] [cursor=pointer]
                - button "agk-ambient-gate-85hvkudx" [pressed] [ref=e60] [cursor=pointer]
        - region [ref=e64]:
          - heading "최근 대화" [level=2] [ref=e66]
          - button "첫 대화 시작하기" [ref=e67] [cursor=pointer]
      - generic [ref=e71]:
        - link "설정" [ref=e72] [cursor=pointer]:
          - /url: /settings
        - button "터미널 열기 또는 닫기" [ref=e76]
    - main [ref=e80]:
      - heading "Ssak-Ai Dashboard" [level=1] [ref=e81]
      - generic [ref=e82]:
        - generic [ref=e83]:
          - generic [ref=e84]:
            - generic [ref=e85]:
              - generic [ref=e86]: agk-ambient-gate-85hvkudx
              - generic [ref=e87]: /
              - 'button "대화 제목 수정: 새 대화" [ref=e88] [cursor=pointer]':
                - generic [ref=e89]: 새 대화
            - generic [ref=e92]:
              - 'button "대화 분기: 새 대화" [disabled] [ref=e93]'
              - 'button "대화 압축: 새 대화" [disabled] [ref=e96]'
              - button "명령 팔레트 열기 (Cmd+K)" [ref=e99] [cursor=pointer]
              - button "대화 기록 열기" [ref=e102] [cursor=pointer]
              - button "환경 패널 토글" [ref=e105] [cursor=pointer]
              - button "전체화면" [ref=e108] [cursor=pointer]
          - generic [ref=e112]:
            - heading "무엇을 만들어 볼까요?" [level=1] [ref=e113]
            - paragraph [ref=e114]: 코드를 살펴보거나, 해결할 문제를 알려 주세요.
            - generic [ref=e115]: agk-ambient-gate-85hvkudx
          - generic [ref=e119]:
            - generic [ref=e120]:
              - generic [ref=e121]:
                - textbox "메시지 입력" [ref=e122]:
                  - /placeholder: 질문이나 작업 내용을 입력하세요
                - generic [ref=e123]:
                  - generic [ref=e124]:
                    - button "옵션 및 파일 첨부" [ref=e126] [cursor=pointer]
                    - button "전체 액세스" [ref=e130] [cursor=pointer]
                    - button "검색" [ref=e136] [cursor=pointer]
                    - button "코드" [ref=e140] [cursor=pointer]
                    - button "MCP" [ref=e145] [cursor=pointer]
                  - generic [ref=e151]:
                    - button "모델 선택" [ref=e153] [cursor=pointer]:
                      - generic [ref=e154]: qwen3.8:latest (27.3B)
                    - button "음성 입력 미연결" [disabled] [ref=e157]
                    - button "메시지 전송" [disabled] [ref=e160]
              - generic [ref=e163]: Enter로 전송, Shift+Enter로 줄바꿈
            - generic "작업 시작 제안" [ref=e164]:
              - button "코드 살펴보기" [ref=e165] [cursor=pointer]
              - button "오류 해결하기" [ref=e168] [cursor=pointer]
              - button "테스트 추가하기" [ref=e171] [cursor=pointer]
        - status [ref=e175]
```

# Test source

```ts
  70  |   constructor(page: Page) {
  71  |     this.page = page;
  72  | 
  73  |     /* Sidebar */
  74  |     this.sidebar = page.locator('nav, .sidebar, [class*="sidebar"]');
  75  |     this.navChat = page.locator('a, button').filter({ hasText: /AI 채팅|Chat/ });
  76  |     this.navWiki = page.locator('a, button').filter({ hasText: /LLM Wiki|Wiki/ });
  77  |     this.navAgent = page.locator('a, button').filter({ hasText: /에이전트|Agent/ });
  78  |     this.navSettings = page.locator('a, button').filter({ hasText: /설정|Settings/ });
  79  |     this.navGit = page.locator('a, button').filter({ hasText: /Git/ });
  80  | 
  81  |     /* Command Palette */
  82  |     this.commandPaletteButton = page.locator(
  83  |       '[class*="palette"], button:has-text("명령"), [title*="Command"], [aria-label*="palette"]',
  84  |     );
  85  |     this.commandPaletteOverlay = page.locator('[class*="palette-overlay"], [class*="command-palette"]');
  86  |     this.commandPaletteInput = page.locator(
  87  |       '[class*="palette"] input, [class*="command-palette"] input, input[placeholder*="명령"], input[placeholder*="command"]',
  88  |     );
  89  | 
  90  |     /* Chat */
  91  |     this.chatInput = page.locator('textarea, [contenteditable="true"], input[type="text"]').first();
  92  |     this.chatSendButton = page.locator('button[type="submit"], button:has-text("전송"), button:has-text("Send")');
  93  |     this.chatMessages = page.locator('[class*="message"], [class*="bubble"], [class*="chat-message"]');
  94  | 
  95  |     /* File Explorer */
  96  |     this.fileExplorer = page.locator('.ide-explorer');
  97  |     this.explorerTitle = page.locator('.explorer-title');
  98  |     this.fileTree = page.locator('.file-tree');
  99  |     this.explorerRefreshBtn = page.locator('[aria-label="파일 트리 새로고침"]');
  100 | 
  101 |     /* Git */
  102 |     this.gitPanel = page.locator('.git-panel');
  103 |     this.gitTabs = page.locator('.git-tabs');
  104 |     this.gitTabStatus = page.locator('.git-tab').filter({ hasText: /Changes/ });
  105 |     this.gitTabHistory = page.locator('.git-tab').filter({ hasText: /History/ });
  106 |     this.gitTabBranches = page.locator('.git-tab').filter({ hasText: /Branches/ });
  107 |     this.gitTabGraph = page.locator('.git-tab').filter({ hasText: /Graph/ });
  108 | 
  109 |     /* PIN Modal */
  110 |     this.pinModal = page.locator('[role="dialog"][aria-label="PIN 인증"]');
  111 |     this.pinInput = page.locator('input[type="password"], input[placeholder*="PIN"], input[name="pin"]');
  112 |     this.pinSubmit = page.locator('button:has-text("잠금 해제"), button:has-text("확인"), button[type="submit"]');
  113 |   }
  114 | 
  115 |   /**
  116 |    * Start collecting console errors.
  117 |    * Call this in beforeEach() to capture all errors during the test.
  118 |    */
  119 |   startCollectingErrors(): void {
  120 |     this.consoleErrors = [];
  121 |     this.page.on('console', (msg) => {
  122 |       if (msg.type() === 'error' || msg.type() === 'warning') {
  123 |         this.consoleErrors.push(`[${msg.type()}] ${msg.text()}`);
  124 |       }
  125 |     });
  126 |   }
  127 | 
  128 |   /**
  129 |    * Assert that no console errors were collected during the test.
  130 |    * Call this in afterEach() after startCollectingErrors() was called in beforeEach().
  131 |    */
  132 |   expectNoConsoleErrors(): void {
  133 |     expect(this.consoleErrors).toEqual([]);
  134 |   }
  135 | 
  136 |   /* ═══════════════════════════════════════════════════════════════
  137 |      Navigation
  138 |      ═══════════════════════════════════════════════════════════════ */
  139 | 
  140 |   async goto(credential: DashboardCredential = { kind: 'none' }): Promise<void> {
  141 |     if (credential.kind === 'legacyPin') {
  142 |       await this.page.addInitScript(({ pin }) => {
  143 |         localStorage.setItem('ag_access_pin', pin);
  144 |       }, { pin: credential.value });
  145 |     } else if (credential.kind === 'token') {
  146 |       await this.page.addInitScript(({ token }) => {
  147 |         sessionStorage.setItem('ag_access_token', token);
  148 |       }, { token: credential.value });
  149 |     }
  150 |     await this.page.goto('/');
  151 |     await this.page.waitForLoadState('domcontentloaded');
  152 |   }
  153 | 
  154 |   async submitPin(pin: string): Promise<void> {
  155 |     await this.pinModal.waitFor({ state: 'visible', timeout: 3_000 });
  156 |     await this.pinInput.fill(pin);
  157 |     await this.pinSubmit.click();
  158 |   }
  159 | 
  160 |   /** Navigate directly to a page via real BrowserRouter pathname (UI-01: hash URL 제거). */
  161 |   async gotoPage(path: string): Promise<void> {
  162 |     await this.page.goto(`/${path.replace(/^\/+/, '')}`.replace(/\/$/, '') || '/');
  163 |     await this.page.waitForLoadState('domcontentloaded');
  164 |     await this.page.waitForTimeout(500);
  165 |   }
  166 | 
  167 |   /** Click the AI Chat nav link. Uses force click to handle overlay interception. */
  168 |   async goToChat(): Promise<void> {
  169 |     const target = this.navChat.first();
> 170 |     await target.waitFor({ state: 'visible', timeout: 5000 });
      |                  ^ TimeoutError: locator.waitFor: Timeout 5000ms exceeded.
  171 |     await target.click({ force: true });
  172 |     await this.page.waitForTimeout(800);
  173 |   }
  174 | 
  175 |   /** Click the Wiki nav link. Uses force click to handle overlay interception. */
  176 |   async goToWiki(): Promise<void> {
  177 |     const target = this.navWiki.first();
  178 |     await target.waitFor({ state: 'visible', timeout: 5000 });
  179 |     await target.click({ force: true });
  180 |     await this.page.waitForTimeout(800);
  181 |   }
  182 | 
  183 |   /** Click the Git nav link. Uses force click to handle overlay interception. */
  184 |   async goToGit(): Promise<void> {
  185 |     const target = this.navGit.first();
  186 |     await target.waitFor({ state: 'visible', timeout: 5000 });
  187 |     await target.click({ force: true });
  188 |     await this.page.waitForTimeout(800);
  189 |   }
  190 | 
  191 |   /* ═══════════════════════════════════════════════════════════════
  192 |      Command Palette
  193 |      ═══════════════════════════════════════════════════════════════ */
  194 | 
  195 |   async openCommandPalette(): Promise<void> {
  196 |     await this.page
  197 |       .getByRole('button', { name: '명령 팔레트 열기 (Cmd+K)' })
  198 |       .waitFor({ state: 'visible', timeout: 5_000 });
  199 |     await this.page.keyboard.press('ControlOrMeta+k');
  200 |     await this.page.waitForTimeout(300);
  201 |   }
  202 | 
  203 |   /** Type a query into the command palette search input. */
  204 |   async searchCommand(query: string): Promise<void> {
  205 |     await this.commandPaletteInput.waitFor({ state: 'visible', timeout: 3000 });
  206 |     await this.commandPaletteInput.fill(query);
  207 |   }
  208 | 
  209 |   /** Expect a command palette item with the given text to be visible. */
  210 |   async expectCommandItem(text: string): Promise<void> {
  211 |     const item = this.page
  212 |       .locator('[class*="palette"] a, [class*="palette"] li, [class*="command"]')
  213 |       .filter({ hasText: text });
  214 |     await expect(item.first()).toBeVisible({ timeout: 3000 });
  215 |   }
  216 | 
  217 |   /** Close the command palette by pressing Escape. */
  218 |   async closeCommandPalette(): Promise<void> {
  219 |     await this.page.keyboard.press('Escape');
  220 |     await this.page.waitForTimeout(200);
  221 |   }
  222 | 
  223 |   /* ═══════════════════════════════════════════════════════════════
  224 |      Chat
  225 |      ═══════════════════════════════════════════════════════════════ */
  226 | 
  227 |   /** Type a message into the chat input and send it. */
  228 |   async sendChatMessage(message: string): Promise<void> {
  229 |     await this.chatInput.waitFor({ state: 'visible', timeout: 5000 });
  230 |     await this.chatInput.fill(message);
  231 |     if (await this.chatSendButton.isVisible()) {
  232 |       await this.chatSendButton.click();
  233 |     } else {
  234 |       await this.page.keyboard.press('Enter');
  235 |     }
  236 |     await this.page.waitForTimeout(500);
  237 |   }
  238 | 
  239 |   /** Get the text content of all visible chat messages. */
  240 |   async getChatMessagesText(): Promise<string[]> {
  241 |     return this.chatMessages.allTextContents();
  242 |   }
  243 | 
  244 |   /** Expect a chat message bubble containing the given text to exist. */
  245 |   async expectChatMessage(text: string): Promise<void> {
  246 |     await expect(
  247 |       this.page.locator('[class*="message"], [class*="bubble"]').filter({ hasText: text }).first(),
  248 |     ).toBeVisible({ timeout: 10_000 });
  249 |   }
  250 | 
  251 |   /** Wait for a user message bubble with the given text. */
  252 |   async expectUserMessage(text: string): Promise<void> {
  253 |     const userMsg = this.page.locator('.message.user .bubble').filter({ hasText: text });
  254 |     await expect(userMsg.first()).toBeVisible({ timeout: 5000 });
  255 |   }
  256 | 
  257 |   /** Wait for an assistant response (any non-empty bubble) to appear. */
  258 |   async expectAssistantResponse(timeout = 15_000): Promise<void> {
  259 |     const assistantBubble = this.page.locator('.message.assistant .bubble');
  260 |     await expect(assistantBubble.first()).toBeVisible({ timeout });
  261 |   }
  262 | 
  263 |   /** Get the count of assistant messages in the chat. */
  264 |   async getAssistantMessageCount(): Promise<number> {
  265 |     return this.page.locator('.message.assistant').count();
  266 |   }
  267 | 
  268 |   /** Get the text of the last assistant message. */
  269 |   async getLastAssistantText(): Promise<string> {
  270 |     const bubbles = this.page.locator('.message.assistant .bubble');
```