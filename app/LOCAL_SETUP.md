# Local deployment

Source: https://github.com/zhinianboke/xianyu-auto-reply
Commit: 990f701fe03d7f62c3cf1fe571fc5bb6de57c778
License: AGPL-3.0 (see LICENSE).

## Open

http://127.0.0.1:9000

Initial application login: admin / admin123. Complete the application CAPTCHA, then change this default password in Settings. No Xianyu account has been added; scan to connect your account after login. No messages have been sent or listings published during deployment.

## Start / stop

```powershell
cd E:\workplace\projects\xianyu-auto-reply
.\start-local.ps1
.\stop-local.ps1
```

No Windows service or automatic boot task was installed. All listeners bind to 127.0.0.1. MySQL:3307, Redis:6389; backend:8089, websocket:8090, scheduler:8091, built frontend preview:9000. The frontend build passed TypeScript + Vite production build. API and static-file proxy use the upstream Vite config. This is a local single-user deployment, not an internet-facing server setup.

## Isolation

- .venv: dedicated Python 3.12 environment, 99 dependency packages.
- .local/mysql: Oracle MySQL 8.0.46 portable ZIP; .local/data/mysql: new database.
- .local/redis: community Redis Windows 8.4.7 MSYS2 build; .local/data/redis: persistent data.
- .local/browser-runtime: Chromium 156, revision 1248, used by Playwright and Patchright.
- .local/private-settings.json: generated private runtime configuration. Do not share it.
- .local/logs: service logs and UI verification screenshot.
- .local/downloads/sources.json: binary download provenance and SHA256; Redis hash matched GitHub release digest.
- .local/verification.json: health/browser verification results.

MySQL app and root passwords were randomly generated and are not the upstream defaults. Browser data is isolated, not imported from an existing personal browser profile. Upstream CAPTCHA functionality remains unchanged. Remote ad/announcement fetch options and auto-crawl startup were disabled in local environment settings.

The upstream browser installer repeatedly failed with a stale filesystem lock. Chromium was instead downloaded from the same Playwright CDN, ZIP integrity checked, and extracted to a new independent directory without changing upstream source. Browser launch tests cover Playwright/Patchright runtime, not a real Xianyu account login, messaging or delivery transaction.

Stop script checks PID ownership against this project before stopping application processes, then requests MySQL/Redis shutdown. Unrelated workplace project/registry discrepancies were left unchanged.
