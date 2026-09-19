/**
 * 브라우저 효과 승인 UI witness (task 18)
 * ======================================
 * 이 파일이 재는 것
 * ---------------
 *   A1 정상: 에이전트의 브라우저 효과가 **승인 대기**로 뜨고, 화면이 서버 판정(효과·위험도·주소·
 *          세대·지문·남은 초)을 그대로 보여 준다. 사람이 승인하면 **클라이언트가 한 번만** 실행하고,
 *          실행은 fixture 사이트에 **정확히 1회** 닿는다.
 *   A2 거절: 화면에서 거절하면 실행되지 않고(0회) 대기 목록에서도 사라진다. 그 뒤 발급 경로는
 *          409 로 거절한다 — 거절이 "조용한 미실행" 으로 끝나지 않는다.
 *   A3 토큰 위조: 서버가 발급하지 않은 토큰으로 실행을 시도하면 403 이고 실행은 0회다.
 *          화면에는 그 요청이 **여전히 대기 중**으로 남는다(사람이 승인할 기회가 사라지지 않는다).
 *   A4 만료: 남은 초가 화면에 보이고 줄어든다(승인이 무기한이 아니라는 사실이 화면에 있다).
 *   A5 사람 차례: MFA 페이지에서는 승인 요청이 **만들어지지 않는다**(자동 재시도·자동 승인 없음).
 *
 * 무엇으로 재는가
 * --------------
 * - **실 hermetic 백엔드**(`startBackendServer`): 실제 uvicorn + 실제 라우트 + 실제 승인 원장.
 *   playwright 는 그 프로세스 안에서 돌므로, 여기서는 **관찰자가 아니라 클라이언트**다.
 * - **실 fixture 사이트**(이 파일의 node server): 버튼이 눌리면 서버가 **호출 횟수**를 센다 —
 *   "효과가 일어났다"를 백엔드 브라우저의 DOM 이 아니라 **밖에서** 확인한다.
 * - 화면은 실제 빌드된 SPA(백엔드가 서빙)이므로, 이 witness 는 `npm run build` 뒤에만 뜻이 있다.
 */

import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { startBackendServer, type HermeticServer } from "./helpers/hermeticBackend";

process.env.AGK_SEC_DEV_NO_PIN_ALLOW = "1";

const SESSION_HEADER = "X-AGK-Browser-Session";
const SESSION = "e2e-approval";
const ACTION_URL = "/api/agent/tools/browser/action";
const PENDING_URL = "/api/agent/tools/browser/approval/pending";

const INDEX_HTML = `<!doctype html>
<html><head><meta charset="utf-8"><title>Approval Fixture</title></head>
<body>
  <h1>approval fixture</h1>
  <button id="send" onclick="fetch('/hit?effect=send')">Send message</button>
  <button id="search" onclick="fetch('/hit?effect=search')">Search</button>
  <a id="go" href="/page2.html">Next page</a>
</body></html>`;

const MFA_HTML = `<!doctype html>
<html><head><meta charset="utf-8"><title>Two-factor</title></head><body>
  <h1>Two-factor authentication</h1>
  <p>Enter the code we sent to your device.</p>
  <input id="otp" autocomplete="one-time-code" aria-label="Verification code" inputmode="numeric" maxlength="6">
  <button id="verify" onclick="fetch('/hit?effect=verify')">Continue</button>
</body></html>`;

const PAGE2_HTML = `<!doctype html>
<html><head><meta charset="utf-8"><title>Second</title></head><body><h1>second</h1></body></html>`;

type FixtureSite = Readonly<{
    baseUrl: string;
    hits: () => number;
    close: () => Promise<void>;
}>;

async function startFixtureSite(): Promise<FixtureSite> {
    const counts = new Map<string, number>();
    const server: Server = createServer((incoming, response) => {
        const url = new URL(incoming.url ?? "/", "http://127.0.0.1");
        if (url.pathname === "/hit") {
            const effect = url.searchParams.get("effect") ?? "unknown";
            counts.set(effect, (counts.get(effect) ?? 0) + 1);
            response.writeHead(204).end();
            return;
        }
        const body =
            url.pathname === "/mfa.html"
                ? MFA_HTML
                : url.pathname === "/page2.html"
                  ? PAGE2_HTML
                  : INDEX_HTML;
        response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" }).end(body);
    });
    await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
    const { port } = server.address() as AddressInfo;
    return {
        baseUrl: `http://127.0.0.1:${port}`,
        hits: () => [...counts.values()].reduce((total, value) => total + value, 0),
        close: () =>
            new Promise<void>(resolve => {
                server.close(() => resolve());
            }),
    };
}

function headers(): Record<string, string> {
    return { [SESSION_HEADER]: SESSION };
}

/**
 * 이 시나리오만의 백엔드.
 *
 * **세션 원장을 격리하는 것이 필수다**: 상한(호스트 2개)은 파일 하나로 호스트 전체가 공유하므로,
 * 시나리오가 병렬로 돌면 서로의 자리를 세어 `429 (2/2)` 로 죽는다(실측: 첫 실행 5건 전부 429).
 * 격리하지 않으면 개발자의 실제 앱/CLI 세션까지 세게 된다.
 */
async function startApprovalServer(): Promise<HermeticServer> {
    const stateDirectory = await mkdtemp(path.join(tmpdir(), "ssak18-approval-"));
    return await startBackendServer({}, {
        stateDirectory,
        overrides: {
            AGK_BROWSER_API_ALLOW_LOCAL: "1",
            AGK_BROWSER_SESSION_STATE: path.join(stateDirectory, "browser_sessions.json"),
        },
    });
}

type Caller = Readonly<{
    launch: () => Promise<void>;
    goto: (url: string) => Promise<void>;
    observe: () => Promise<Record<string, unknown>>;
    click: (ref: string, token?: string) => Promise<{ status: number; json: () => Promise<Record<string, unknown>> }>;
    pending: () => Promise<readonly Record<string, unknown>[]>;
    grant: (requestId: string) => Promise<{ status: number; json: () => Promise<Record<string, unknown>> }>;
    resolve: (requestId: string, decision: string) => Promise<number>;
}>;

function caller(request: APIRequestContext, baseUrl: string): Caller {
    const post = async (path: string, data: Record<string, unknown>) =>
        request.post(`${baseUrl}${path}`, { data, headers: headers() });
    return {
        launch: async () => {
            const response = await post(ACTION_URL, { action: "launch" });
            expect(response.status(), await response.text()).toBe(200);
        },
        goto: async (url: string) => {
            const response = await post(ACTION_URL, { action: "goto", url });
            expect(response.status(), await response.text()).toBe(200);
        },
        observe: async () => {
            const response = await post(ACTION_URL, { action: "observe" });
            expect(response.status(), await response.text()).toBe(200);
            return (await response.json()) as Record<string, unknown>;
        },
        click: async (ref: string, token?: string) => {
            const body: Record<string, unknown> = { action: "click", ref };
            if (token !== undefined) body.approval_token = token;
            const response = await post(ACTION_URL, body);
            return {
                status: response.status(),
                json: async () => (await response.json()) as Record<string, unknown>,
            };
        },
        pending: async () => {
            const response = await request.get(`${baseUrl}${PENDING_URL}`, { headers: headers() });
            const body = (await response.json()) as { pending: readonly Record<string, unknown>[] };
            return body.pending;
        },
        grant: async (requestId: string) => {
            const response = await request.post(
                `${baseUrl}/api/agent/tools/browser/approval/${requestId}/grant`,
                { data: {}, headers: headers() },
            );
            return {
                status: response.status(),
                json: async () => (await response.json()) as Record<string, unknown>,
            };
        },
        resolve: async (requestId: string, decision: string) => {
            const response = await request.post(`${baseUrl}/api/approval/${requestId}/resolve`, {
                data: { decision },
                headers: headers(),
            });
            return response.status();
        },
    };
}

function refByName(observation: Record<string, unknown>, name: string): string {
    const payload = observation.observation as { refs: readonly { name: string; ref: string }[] };
    const found = payload.refs.find(item => item.name === name);
    if (found === undefined) throw new Error(`no ref named ${name}`);
    return found.ref;
}

/** 승인 대기 한 건을 만들고 그 요청 ID·참조를 돌려준다(에이전트가 실제로 428 을 받은 상태). */
async function raiseApproval(
    api: Caller,
    site: FixtureSite,
): Promise<{ requestId: string; ref: string; requirement: Record<string, unknown> }> {
    await api.launch();
    await api.goto(`${site.baseUrl}/index.html`);
    const observation = await api.observe();
    const ref = refByName(observation, "Send message");
    const asked = await api.click(ref);
    expect(asked.status).toBe(428);
    const detail = (await asked.json()).detail as { requirement: Record<string, unknown> };
    return { requestId: String(detail.requirement.request_id), ref, requirement: detail.requirement };
}

async function openPanel(page: Page, baseUrl: string): Promise<void> {
    await page.goto(`${baseUrl}/agent`);
    await page.waitForLoadState("domcontentloaded");
    await expect(page.getByRole("heading", { name: "브라우저 효과 승인" })).toBeVisible({
        timeout: 20_000,
    });
}

test.describe("브라우저 효과 승인 UI", () => {
    test("A1 승인하면 클라이언트가 정확히 한 번 실행한다", async ({ browser, request }) => {
        test.setTimeout(120_000);
        const site = await startFixtureSite();
        const server = await startApprovalServer();
        const context = await browser.newContext({ baseURL: server.baseUrl });
        const page = await context.newPage();
        try {
            const api = caller(request, server.baseUrl);
            const { requestId, ref } = await raiseApproval(api, site);

            await openPanel(page, server.baseUrl);
            const item = page.getByTestId("browser-approval-item");
            await expect(item).toHaveCount(1, { timeout: 20_000 });
            // 화면은 **서버가 판정한 의미**를 그린다(클라이언트가 위험도를 계산하지 않는다).
            await expect(item).toContainText("전송·게시 · 높음");
            await expect(item).toContainText(site.baseUrl);
            await expect(page.getByTestId("browser-approval-ttl")).toContainText("만료까지");
            await expect(item).toContainText(ref);
            // 브라우저 효과에는 '항상 허용' 이 없다는 사실이 화면에 있다(패널이 정책을 말한다).
            await expect(page.locator(".browser-approval-note")).toContainText("항상 허용");
            // 그리고 일반 승인 대기열도 이 도구에 '항상 허용' 버튼을 주지 않는다(서버 판정을 따른다).
            await expect(page.getByTestId("approval-always-allow-unavailable")).toBeVisible({
                timeout: 20_000,
            });
            await expect(page.getByRole("button", { name: /browser_effect 도구를 항상 허용/ })).toHaveCount(0);

            await page.getByTestId("browser-approval-approve").click();
            await expect(page.getByTestId("browser-approval-granted")).toContainText("요청한 클라이언트가 이어서 실행");
            // 화면은 발급하지 않는다 — 토큰이 DOM 에 실리면 페이지 안의 무엇이든 읽을 수 있다.
            expect(await page.content()).not.toContain("ssak1.");

            // 클라이언트(에이전트)가 발급받아 실행한다.
            const granted = await api.grant(requestId);
            expect(granted.status, await JSON.stringify(await granted.json())).toBe(200);
            const ticket = (await granted.json()).ticket as { approval_token: string; ttl_seconds: number };
            expect(ticket.approval_token.startsWith("ssak1.")).toBe(true);
            expect(ticket.ttl_seconds).toBeGreaterThan(0);

            const executed = await api.click(ref, ticket.approval_token);
            expect(executed.status, await executed.json()).toBe(200);

            // 효과가 **밖에서** 관측된다: fixture 사이트 호출 1회.
            await expect.poll(() => site.hits(), { timeout: 10_000 }).toBe(1);
            // 같은 승인은 두 번 쓰이지 않는다.
            const again = await api.click(ref, ticket.approval_token);
            expect(again.status).toBe(409);
            await expect.poll(() => site.hits()).toBe(1);
        } finally {
            await context.close();
            await server.cleanup();
            await site.close();
        }
    });

    test("A2 거절하면 실행되지 않고 대기에서도 사라진다", async ({ browser, request }) => {
        test.setTimeout(120_000);
        const site = await startFixtureSite();
        const server = await startApprovalServer();
        const context = await browser.newContext({ baseURL: server.baseUrl });
        const page = await context.newPage();
        try {
            const api = caller(request, server.baseUrl);
            const { requestId } = await raiseApproval(api, site);

            await openPanel(page, server.baseUrl);
            await expect(page.getByTestId("browser-approval-item")).toHaveCount(1, { timeout: 20_000 });
            await page.getByTestId("browser-approval-deny").click();
            await expect(page.getByTestId("browser-approval-empty")).toBeVisible({ timeout: 20_000 });

            // 거절은 **기록으로 남는다**(F-33) — 거절이 "조용한 미실행" 으로 끝나지 않는다.
            const recorded = await request.get(`${server.baseUrl}/api/approval/${requestId}`, {
                headers: headers(),
            });
            expect(recorded.status()).toBe(200);
            expect((await recorded.json()).status).toBe("denied");
            // 그리고 발급 경로는 아무것도 주지 않는다.
            const granted = await api.grant(requestId);
            expect([404, 409]).toContain(granted.status);
            expect(site.hits()).toBe(0);
        } finally {
            await context.close();
            await server.cleanup();
            await site.close();
        }
    });

    test("A3 서버가 발급하지 않은 토큰은 실행되지 않는다", async ({ browser, request }) => {
        test.setTimeout(120_000);
        const site = await startFixtureSite();
        const server = await startApprovalServer();
        const context = await browser.newContext({ baseURL: server.baseUrl });
        const page = await context.newPage();
        try {
            const api = caller(request, server.baseUrl);
            const { ref } = await raiseApproval(api, site);

            const forged = await api.click(ref, "ssak1.i-made-this-up");
            expect(forged.status).toBe(403);
            expect(await forged.json()).toMatchObject({
                detail: { error_code: "MODEL_TOKEN_REFUSED" },
            });
            expect(site.hits()).toBe(0);

            // 실패한 시도는 사람의 기회를 없애지 않는다 — 요청은 여전히 대기 중으로 보인다.
            await openPanel(page, server.baseUrl);
            await expect(page.getByTestId("browser-approval-item")).toHaveCount(1, { timeout: 20_000 });
            await expect(page.getByTestId("browser-approval-approve")).toBeEnabled();
        } finally {
            await context.close();
            await server.cleanup();
            await site.close();
        }
    });

    test("A4 남은 초가 화면에서 줄어든다(승인은 무기한이 아니다)", async ({ browser, request }) => {
        test.setTimeout(120_000);
        const site = await startFixtureSite();
        const server = await startApprovalServer();
        const context = await browser.newContext({ baseURL: server.baseUrl });
        const page = await context.newPage();
        try {
            const api = caller(request, server.baseUrl);
            await raiseApproval(api, site);
            await openPanel(page, server.baseUrl);
            const ttl = page.getByTestId("browser-approval-ttl");
            await expect(ttl).toBeVisible({ timeout: 20_000 });
            const first = Number(/(\d+)초/.exec((await ttl.textContent()) ?? "")?.[1] ?? "0");
            expect(first).toBeGreaterThan(0);
            expect(first).toBeLessThanOrEqual(60);
            await expect
                .poll(async () => Number(/(\d+)초/.exec((await ttl.textContent()) ?? "")?.[1] ?? "0"), {
                    timeout: 10_000,
                })
                .toBeLessThan(first);
        } finally {
            await context.close();
            await server.cleanup();
            await site.close();
        }
    });

    test("A5 MFA 페이지는 승인이 아니라 사람 차례다", async ({ browser, request }) => {
        test.setTimeout(120_000);
        const site = await startFixtureSite();
        const server = await startApprovalServer();
        const context = await browser.newContext({ baseURL: server.baseUrl });
        const page = await context.newPage();
        try {
            const api = caller(request, server.baseUrl);
            await api.launch();
            await api.goto(`${site.baseUrl}/mfa.html`);
            const observation = await api.observe();
            const handoff = observation.handoff as { status: string; kind: string };
            expect(handoff.status).toBe("waiting_user");
            expect(handoff.kind).toBe("mfa");

            const clicked = await api.click(refByName(observation, "Continue"));
            expect(clicked.status).toBe(409);
            expect(await clicked.json()).toMatchObject({
                detail: { status: "waiting_user", error_code: "HANDOFF_REQUIRED" },
            });

            // 승인 창이 아니라 사람 차례다 — 승인 요청이 **하나도** 만들어지지 않는다.
            expect(await api.pending()).toHaveLength(0);
            await openPanel(page, server.baseUrl);
            await expect(page.getByTestId("browser-approval-empty")).toBeVisible({ timeout: 20_000 });
            expect(site.hits()).toBe(0);
        } finally {
            await context.close();
            await server.cleanup();
            await site.close();
        }
    });
});
