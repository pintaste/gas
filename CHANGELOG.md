# Changelog

## 0.1.1 — 2026-07-25

### Features

- **SuperGrok credit usage** in `gas ls`, `gas status`, and new `gas usage` / `gas cost`
  - Weekly pool `%` (`creditUsagePercent`) + monthly `$used/$limit`
  - Per-product breakdown (GrokBuild / GrokChat / Api) in detail views
  - OIDC token refresh with write-back to account backups (and live auth when matched)
  - Disk cache `~/.grok-switch/usage-cache.json` (TTL via `GAS_USAGE_TTL`, default 120s)
- `gas ls --no-usage` / `gas ls --refresh`; `gas usage --json`; `GAS_USAGE=0` offline mode
- Clear **auth health** on list/usage: `needs re-login` (not cryptic `token?`), plus footer with `gas to N && grok login && gas add`
- Usage lines show reset countdown (compact `ls`: `N% used · $a/$b · Resets in 5d 21h 18m`)
- **Token hygiene**: mirror live `auth.json` → matching slot on every command; `gas refresh` for proactive OIDC refresh + write-back; early refresh skew (default 30m)

### Notes

- Local switch counters remain under `gas stats` (not mixed with credit usage)
- No auto-switch on limit; display only
- Already-revoked refresh tokens cannot be recovered — still need `grok login && gas add`

## 0.1.0 — 2026-07-15

Initial public release.

### Features

- Capture and switch multiple Grok CLI OAuth accounts (`add`, `ls`, `sw`, `to`)
- Resolve accounts by number, email, or profile name
- Transactional switch with rollback and exclusive lock
- Refuse switch when the live login is unmanaged
- Directory mapping (`dir` / `auto`)
- Isolated runs via `GROK_HOME` (`exec` / `config-dir`)
- Diagnostics: `check`, `status`, `stats`, `whoami`
- Dry-run (`-n`) and quiet mode (`GAS_SILENT=1`)
- Automatic migration from the early named-profile layout

### Security

- Store directory mode `700`, token files mode `600`
- Atomic JSON writes
