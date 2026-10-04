# QA capture readiness

Status: **BLOCKED — capture set is not ready for route approval**

The build is ready (`BUILD_CURRENT.log`, exit 0) and the current bundle binding is recorded as `index-C1osb2i9.js` plus `index-Gvc9kB2l.css`. The required IAB tab was absent on the first exact lookup. The fallback fresh IAB tab is PIN-locked and displays only the system lock dialog. The executor did not enter a PIN, change authentication, or inspect storage/tokens.

One fresh blocker screenshot is ready and verified as a JPEG: [blocked-pin-lock-1280x720.jpg](captures/blocked-pin-lock-1280x720.jpg), 1280×720, SHA-256 `361e36bd45ad88a288bd4ad85503085e437a631b5c41bf5289f4867df14952b2`. The requested 375×812, 768×900, and 1280×900 route/state captures could not be produced because the app surface is unavailable behind the gate.

The previous `BROWSER_OBSERVATIONS.json` and its `after-*` captures were checked and rejected for final approval: they bind to stale `index-CJUpMcF4.js`, and one previous model-popover observation reports horizontal overflow. They are retained as historical evidence only.

Root action needed before this QA can be completed: make an already-unlocked localhost:8000 IAB tab visible to this executor/session. Once that prerequisite exists, rerun the matrix in `QA_REVIEW.md`, capture every listed route at all three widths, and update `CAPTURE_MANIFEST.json`; do not reuse the stale captures.
