# gas — session handoff / project context

Read this at the start of any session working on **gas**.

## What it is

- **gas** = Grok Account Switch: multi-account switcher for Grok CLI
- Inspired by **ccs** (Claude Code multi-account switcher: `fairy-pitta/cc-account-switcher`, Homebrew `ccswitch`)
- **Not** CC Switch (desktop GUI by farion1231)

## Repo & install

| Item | Value |
|------|--------|
| GitHub | https://github.com/pintaste/gas |
| Local path | `~/Documents/SideProjects/gas` |
| CLI name | `gas` (not `gss` — shells alias `gss` → `git status -s`) |
| Version | **0.1.1** |
| Install | `curl -fsSL https://raw.githubusercontent.com/pintaste/gas/main/install.sh \| bash` → `~/.local/bin/gas` |
| License | MIT |
| Author credit | Written by **Grok 4.5 (high)** |

Repo was renamed from `pintaste/gss` → `pintaste/gas`. Prefer new URLs only.

## Storage

| Path | Role |
|------|------|
| `~/.grok/auth.json` | Live Grok session (hot-reloads) |
| `~/.grok-switch/` | gas store (`GSS_HOME` / `GAS_HOME`) |
| `sequence.json` | Account index, rotation, stats |
| `accounts/<n>/auth.json` | Per-account backup |
| `usage-cache.json` | SuperGrok credit usage cache |
| Official env | `GROK_HOME` (Grok CLI); gas also honors `GROK_DIR` for tests |

## Commands (ccs-style)

```text
gas add / ls / sw / to <n|email|profile>
gas profile / rm / dir / auto
gas exec / config-dir     # isolation via GROK_HOME
gas check / status / stats / usage / refresh / whoami
gas ls --no-usage / --refresh
gas -n …                  # dry-run
GAS_SILENT=1              # quiet
GAS_USAGE=0               # offline (no credit-usage fetch)
```

Token hygiene: every `gas` command **mirrors live auth → matching account slot** (Grok only refreshes live).  
`gas refresh` / usage path also OIDC-refresh inactive slots and write back (RT rotation).

`gas add` = **capture current login only** (never logout).  
Second account: `gas add` → `grok logout && grok login` → `gas add` → `gas sw`.

## Design decisions (do not regress)

1. **Transactional switch** + rollback (like ccs)
2. **Exclusive lock** `~/.grok-switch/.switch.lock` (mkdir, stale-PID recovery)
3. **Live email** is SSOT under lock; refuse switch if live login is unmanaged
4. Grok **hot-reloads** auth — no forced restart (unlike Claude/ccs `-r`)
5. **Usage display** (0.1.1+): SuperGrok credits via `cli-chat-proxy.grok.com/v1/billing` — show in `ls`/`status`/`usage` only; **no** auto-switch / rate-limit hooks yet
6. **No** Claude Keychain / `--resume` (N/A for Grok)
7. Demo GIF emails are **fake**: `you@personal.dev` / `you@work.dev` — never put real emails in assets
8. Version stays **0.x** (not 1.x); keep history clean when user asks
9. On OIDC refresh, **always write tokens back** to `accounts/<n>/auth.json` (and live if email matches) — refresh tokens rotate
10. **sync_live_to_managed** on every `ensure_layout()` so Grok's silent live refresh is not lost from backups

## Demo / social

- GIF: `assets/gas-demo.gif` (in README top)
- Do not commit real account emails into media or docs
- X/Twitter: no markdown code fences; put install URL on GitHub/README, not long curl mid-post

## Tests

```bash
cd ~/Documents/SideProjects/gas
python3 -m unittest discover -s tests -v
```

Uses temp dirs via `GSS_HOME` + `GROK_DIR`; never touches real `~/.grok` in CI-style tests.

## Related on this machine

- **ccs** (Claude): `/opt/homebrew/bin/ccs`, data `~/.claude-switch-backup/`
- User also has CC Switch app + `~/.cc-switch/` — different product

## User prefs (this project)

- Prefer Chinese replies unless asked otherwise
- When cleaning history: orphan rebuild + force-push is OK if user asks
- Keep commits few and well-written for release
