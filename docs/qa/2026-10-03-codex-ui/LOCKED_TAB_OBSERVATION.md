# Locked-tab observation (manual QA executor)

Date: 2026-10-03 (Asia/Seoul)

The required first browser invocation was executed verbatim with the CUA IAB binding:

```js
await cua.getTab({url:'http://127.0.0.1:8000/'},{browser:'iab'})
```

At first, the connected IAB browser had no tab. A new IAB tab was created only to establish a concrete, inspectable blocker:

```js
await cua.createBrowserTab('iab','http://127.0.0.1:8000/',{visible:false})
```

The tab loaded the PIN gate. No PIN was entered and no authentication or credential state was changed. Read-only CUA observations were then collected with `tab.getAXState({disableDiffing:true})`, `tab.getScreenshot()`, and a DOM/style-safe `tab.playwright.evaluate(...)` call.

Observed AX content:

```text
Ssak-Ai — Cold-blooded engineering, URL: 127.0.0.1:8000/
container PIN 인증
heading 🔒 시스템 잠금
외부 접속 보안을 위해 PIN 번호를 입력하세요.
text field PIN 번호
button 잠금 해제
```

Observed DOM metrics:

```json
{"innerWidth":1280,"innerHeight":720,"devicePixelRatio":1,"title":"Ssak-Ai — Cold-blooded engineering","url":"http://127.0.0.1:8000/","headings":["🔒 시스템 잠금"],"overflow":{"body":false,"doc":false}}
```

The screenshot is a real JPEG from the current CUA tab: `captures/blocked-pin-lock-1280x720.jpg`, 1280×720, SHA-256 `361e36bd45ad88a288bd4ad85503085e437a631b5c41bf5289f4867df14952b2`.
