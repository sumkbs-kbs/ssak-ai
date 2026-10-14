# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: tests/cr10-telemetry.spec.ts >> C10-04 · 화면 지표가 API 응답을 그대로 옮긴다(고정 payload 대조)
- Location: e2e/tests/cr10-telemetry.spec.ts:163:1

# Error details

```
Error: expect(received).toMatch(expected)

Expected pattern: /^15M 0\dS$/
Received string:  "14M 59S"
```

# Test source

```ts
  103 |     expect(await text(page, 'telemetrics-mem')).not.toContain('MB');
  104 | 
  105 |     // C10-02: 방금 뜬 hermetic 서버다 — 업타임은 초 단위여야 한다.
  106 |     //         (14일 고정값이나 탭이 열린 시간과 구분된다.)
  107 |     const uptimeLabel = await text(page, 'telemetrics-uptime');
  108 |     const uptimeSeconds = parseUptime(uptimeLabel);
  109 |     // 화면 값은 관측 시점의 서버 업타임 + 경과분이므로 API 값과 30초 이내로 일치해야 한다.
  110 |     expect(Math.abs(uptimeSeconds - api.uptime_seconds)).toBeLessThan(30);
  111 |     expect(api.uptime_seconds).toBeLessThan(600);
  112 |     expect(Date.parse(api.uptime_started_at)).toBeGreaterThan(0);
  113 | 
  114 |     // C10-05: 고정 문구가 없다.
  115 |     const text2 = await bodyText(page);
  116 |     for (const fragment of HARDCODED_FRAGMENTS) {
  117 |       expect(text2, `고정 문구가 남아 있다: ${fragment}`).not.toContain(fragment);
  118 |     }
  119 | 
  120 |     console.log(
  121 |       `[C10-EVIDENCE] ${JSON.stringify({
  122 |         build,
  123 |         uptimeLabel,
  124 |         apiUptime: api.uptime_seconds,
  125 |         processId: api.process_id,
  126 |         cpu: api.cpu_percent,
  127 |         memoryPercent: api.memory_percent,
  128 |       })}`,
  129 |     );
  130 |   } finally {
  131 |     await context.close();
  132 |     await server.cleanup();
  133 |   }
  134 | });
  135 | 
  136 | /**
  137 |  * C10-04: 화면이 API 값을 그대로 옮기는지 결정적으로 확인한다.
  138 |  * 실 서버의 CPU/MEM은 호출마다 새로 표본되므로 고정 payload를 주입해 정확히 대조한다.
  139 |  */
  140 | const STUB_STATUS = {
  141 |   ok: true,
  142 |   status: 'online',
  143 |   memory_mb: 41.5,
  144 |   memory_percent: 41.5,
  145 |   cpu_percent: 12.3,
  146 |   total_tokens: 2048,
  147 |   uptime_seconds: 900,
  148 |   uptime_started_at: '2026-09-12T00:00:00+00:00',
  149 |   process_id: 4242,
  150 |   version: '9.9.9',
  151 |   build: { version: '9.9.9', build_id: 'stubbeef', built_at: null, channel: 'test' },
  152 | } as const;
  153 | 
  154 | const STUB_HEALTH = {
  155 |   status: 'ok',
  156 |   version: '9.9.9',
  157 |   build: { version: '9.9.9', build_id: 'stubbeef', built_at: null, channel: 'test' },
  158 |   backends: {},
  159 |   rag_index_files: 7,
  160 |   cov_active: true,
  161 | } as const;
  162 | 
  163 | test('C10-04 · 화면 지표가 API 응답을 그대로 옮긴다(고정 payload 대조)', async ({ browser }) => {
  164 |   test.setTimeout(120_000);
  165 |   const server: HermeticServer = await startNoAuthServer();
  166 |   const context = await browser.newContext({ baseURL: server.baseUrl });
  167 |   const page = await context.newPage();
  168 |   try {
  169 |     await page.route(/\/api\/system\/status(?:\?.*)?$/, route =>
  170 |       route.fulfill({
  171 |         status: 200,
  172 |         contentType: 'application/json',
  173 |         body: JSON.stringify(STUB_STATUS),
  174 |       }),
  175 |     );
  176 |     // 앱은 `/v1/health`를 호출한다(API_BASE='/v1'). 정확한 경로만 잡아
  177 |     // `/api/mcp/health` 같은 다른 health 엔드포인트를 덮지 않는다.
  178 |     await page.route(
  179 |       url => url.pathname === '/health' || url.pathname === '/v1/health',
  180 |       route =>
  181 |         route.fulfill({
  182 |           status: 200,
  183 |           contentType: 'application/json',
  184 |           body: JSON.stringify(STUB_HEALTH),
  185 |         }),
  186 |     );
  187 | 
  188 |     const dashboard = new DashboardPage(page);
  189 |     await dashboard.goto();
  190 |     await expect(page.getByTestId('telemetrics-link')).toHaveAttribute(
  191 |       'data-connection',
  192 |       'live',
  193 |       { timeout: 30_000 },
  194 |     );
  195 | 
  196 |     // 서버 버전과 번들 버전(0.1.0)이 다르므로 둘 다 구분되어 보여야 한다(C10-05).
  197 |     expect(await text(page, 'telemetrics-build')).toBe('v9.9.9 · stubbeef (ui v0.1.0)');
  198 |     expect(await text(page, 'telemetrics-node')).toBe('PID-4242 · NOMINAL');
  199 |     expect(await text(page, 'telemetrics-cpu')).toBe('12.3%');
  200 |     expect(await text(page, 'telemetrics-mem')).toBe('41.5%');
  201 |     expect(await text(page, 'telemetrics-vault')).toBe('7 INDEXED');
  202 |     // 900초 = 15분. 방금 관측했으므로 초는 00~05 사이에서만 흘렀다.
> 203 |     expect(await text(page, 'telemetrics-uptime')).toMatch(/^15M 0\dS$/);
      |                                                    ^ Error: expect(received).toMatch(expected)
  204 | 
  205 |     console.log(`[C10-EVIDENCE-stub] ${JSON.stringify({
  206 |       build: await text(page, 'telemetrics-build'),
  207 |       uptime: await text(page, 'telemetrics-uptime'),
  208 |     })}`);
  209 |   } finally {
  210 |     await context.close();
  211 |     await server.cleanup();
  212 |   }
  213 | });
  214 | 
  215 | test('C10-02 · 서버 재시작 후 UPTIME이 0에서 다시 시작한다', async ({ browser }) => {
  216 |   test.setTimeout(180_000);
  217 |   const first: HermeticServer = await startNoAuthServer();
  218 |   const context = await browser.newContext({ baseURL: first.baseUrl });
  219 |   const page = await context.newPage();
  220 |   try {
  221 |     const dashboard = new DashboardPage(page);
  222 |     await dashboard.goto();
  223 |     await expect(page.getByTestId('telemetrics-link')).toHaveAttribute(
  224 |       'data-connection',
  225 |       'live',
  226 |       { timeout: 30_000 },
  227 |     );
  228 |     const before = await text(page, 'telemetrics-uptime');
  229 | 
  230 |     // 같은 번들, 새 프로세스 — 업타임은 프로세스 기준이므로 처음부터 다시 센다.
  231 |     await first.cleanup();
  232 |     const second: HermeticServer = await startNoAuthServer();
  233 |     try {
  234 |       await page.goto(second.baseUrl);
  235 |       await expect(page.getByTestId('telemetrics-link')).toHaveAttribute(
  236 |         'data-connection',
  237 |         'live',
  238 |         { timeout: 30_000 },
  239 |       );
  240 |       const after = parseUptime(await text(page, 'telemetrics-uptime'));
  241 | 
  242 |       expect(after).toBeLessThan(600);
  243 |       // 이전 프로세스의 값이 이어지지 않는다(누적/고정이면 여기서 실패한다).
  244 |       expect(after).toBeLessThan(parseUptime(before) + 600);
  245 |     } finally {
  246 |       await second.cleanup();
  247 |     }
  248 |   } finally {
  249 |     await context.close();
  250 |     await first.cleanup().catch(() => undefined);
  251 |   }
  252 | });
  253 | 
  254 | test('C10-03 · API가 끊기면 UNKNOWN/OFFLINE이고 healthy를 주장하지 않는다', async ({ browser }) => {
  255 |   test.setTimeout(120_000);
  256 |   // 백엔드가 죽은 상태를 흉내낸다: 지표 API를 모두 끊는다.
  257 |   const server: HermeticServer = await startNoAuthServer();
  258 |   const context = await browser.newContext({ baseURL: server.baseUrl });
  259 |   const page = await context.newPage();
  260 |   try {
  261 |     await page.route(/\/(?:api\/system\/status|health)$/, route => route.abort('failed'));
  262 | 
  263 |     const dashboard = new DashboardPage(page);
  264 |     await dashboard.goto();
  265 |     await expect(page.getByTestId('telemetrics-link')).toBeVisible({ timeout: 20_000 });
  266 | 
  267 |     // 명시적 실패는 disconnected(=OFFLINE)로 나타난다.
  268 |     await expect(page.getByTestId('telemetrics-link')).toHaveAttribute(
  269 |       'data-connection',
  270 |       'disconnected',
  271 |       { timeout: 30_000 },
  272 |     );
  273 |     expect(await text(page, 'telemetrics-link')).toContain('OFFLINE');
  274 | 
  275 |     // 값이 없으면 0이 아니라 UNKNOWN이고, healthy를 주장하지 않는다.
  276 |     expect(await text(page, 'telemetrics-uptime')).toBe('UNKNOWN');
  277 |     expect(await text(page, 'telemetrics-build')).toBe('UNKNOWN');
  278 |     expect(await text(page, 'telemetrics-cpu')).toBe('UNKNOWN');
  279 |     expect(await text(page, 'telemetrics-mem')).toBe('UNKNOWN');
  280 |     expect(await text(page, 'telemetrics-node')).toBe('UNKNOWN');
  281 | 
  282 |     const body = await bodyText(page);
  283 |     expect(body).not.toContain('NOMINAL');
  284 |     expect(body).not.toContain('0.0%');
  285 |     console.log(`[C10-EVIDENCE-offline] ${JSON.stringify({ link: await text(page, 'telemetrics-link') })}`);
  286 |   } finally {
  287 |     await context.close();
  288 |     await server.cleanup();
  289 |   }
  290 | });
  291 | 
```