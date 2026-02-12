Original prompt: golf 스윙을 시뮬레이션 하는 web 게임

- Initialized project with empty workspace.
- Using develop-web-game skill workflow.
- TODO: implement canvas golf swing simulation with deterministic stepping hooks.

- Added `index.html` canvas golf swing simulator with start screen, swing charge/release mechanics, physics, wind, scoring, restart, and fullscreen toggle.
- Added `window.render_game_to_text` and deterministic `window.advanceTime(ms)` hook.
- Attempted Playwright loop with `web_game_playwright_client.js`; blocked because `playwright` package is missing and npm registry access failed (`ENOTFOUND registry.npmjs.org`).
- TODO next agent: when network is available, run `npm install playwright` in workspace and execute the skill Playwright command against `http://127.0.0.1:4173` with `test-actions.json`, then inspect screenshots and state json.
