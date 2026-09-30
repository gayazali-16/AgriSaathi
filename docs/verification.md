# Submission verification

Verified 30 September 2026 on Windows with Python 3.13 and Node.js 22.
These results apply to the clean submission checkout, not a cloud deployment.

| Check | Result |
|---|---|
| New Python virtual environment and declared dependency install | Passed |
| Clean npm ci using the committed lockfile | Passed; npm reported zero vulnerabilities |
| Backend tests | 62 passed |
| Vitest | 19 passed across 7 files |
| Both Playwright journeys | 2 passed, including axe/keyboard/mobile checks |
| Production frontend build | Passed |
| Standalone staged-file export: backend tests | 62 passed |
| Standalone staged-file export: data hashes and documentation targets | Passed |
| Fresh standalone server: health, Ramesh/Rajesh/Lakshmi logins and empty history | Passed |
| Private .env, uploads, databases and dependency directories excluded from Git | Passed |
| Original private secret values absent from staged files | Passed; values were not printed |
| Git whitespace check | Passed |

The fresh standalone server was tested with no Gemini/OpenWeather keys. It
correctly reported demo abstention, rather than a generated AI answer. Historic
live evaluation results are preserved separately in [evaluation.md](evaluation.md);
this packaging check did not repeat provider calls or claim new AI accuracy.

Three upstream TestClient deprecation warnings accompanied the passing backend
tests. They did not fail the suite; no extra dependency was added to suppress them.
Direct backend dependencies are pinned to the versions installed for this check.

Public reference JSON and architecture artifacts retain exact bytes in Git where
hash receipts require them. Git line-ending conversion is disabled for those
artifacts; ordinary source text uses LF. The standalone export checked this boundary.

Docker Desktop's engine was unavailable in this session, so the new submission
image was not built or started here. Cloud credentials were not used, and no
Cloud Run deployment or hosted end-to-end success is asserted.
