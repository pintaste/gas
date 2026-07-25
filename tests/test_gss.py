#!/usr/bin/env python3
"""Isolated unit tests for gas 1.2 (ccs-hardened, no real network)."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAS = ROOT / "gas"


def sample_auth(email: str = "alice@example.com", first: str = "Alice", last: str = "A") -> dict:
    return {
        "https://auth.x.ai::client-id": {
            "key": "fake-access-token",
            "auth_mode": "oauth",
            "create_time": "2026-01-01T00:00:00Z",
            "user_id": f"user-{email}",
            "email": email,
            "first_name": first,
            "last_name": last,
            "principal_type": "User",
            "principal_id": f"user-{email}",
            "refresh_token": f"refresh-{email}",
            "expires_at": "2026-12-31T00:00:00Z",
            "oidc_issuer": "https://auth.x.ai",
            "oidc_client_id": "client-id",
        }
    }


class GasTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.grok = self.base / "grok"
        self.switch = self.base / "switch"
        self.grok.mkdir()
        self.env = os.environ.copy()
        self.env["GROK_DIR"] = str(self.grok)
        self.env["GSS_HOME"] = str(self.switch)
        self.env["NO_COLOR"] = "1"
        # Keep unit tests offline by default; usage tests re-enable + mock HTTP.
        self.env["GAS_USAGE"] = "0"
        self.env.pop("GAS_SILENT", None)
        self.env.pop("CCS_SILENT", None)
        self.env["PATH"] = str(ROOT) + os.pathsep + self.env.get("PATH", "")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_gas(self, *args: str, check: bool = True, input_text: str | None = None, env=None):
        return subprocess.run(
            [sys.executable, str(GAS), *args],
            env=env or self.env,
            capture_output=True,
            text=True,
            input=input_text,
            check=check,
        )

    def write_active(self, auth: dict) -> None:
        path = self.grok / "auth.json"
        path.write_text(json.dumps(auth), encoding="utf-8")
        os.chmod(path, 0o600)

    def seq(self) -> dict:
        return json.loads((self.switch / "sequence.json").read_text())

    def add_two(self) -> None:
        self.write_active(sample_auth("a@x.com", "A", "A"))
        self.run_gas("add")
        self.write_active(sample_auth("b@x.com", "B", "B"))
        self.run_gas("add")

    def test_version(self):
        r = self.run_gas("version")
        self.assertIn("gas 0.1", r.stdout)

    def test_add_ls_whoami(self):
        self.write_active(sample_auth())
        r = self.run_gas("add")
        self.assertIn("added Account-1", r.stdout)
        self.assertTrue((self.switch / "accounts" / "1" / "auth.json").exists())
        mode = (self.switch / "accounts" / "1" / "auth.json").stat().st_mode
        self.assertEqual(stat.S_IMODE(mode), 0o600)
        self.assertIn("(active)", self.run_gas("ls").stdout)
        self.assertEqual(self.run_gas("whoami").stdout.strip(), "alice@example.com")

    def test_add_updates_existing_email(self):
        self.write_active(sample_auth())
        self.run_gas("add")
        a = sample_auth()
        a["https://auth.x.ai::client-id"]["refresh_token"] = "refreshed"
        self.write_active(a)
        r = self.run_gas("add")
        self.assertIn("updated Account-1", r.stdout)
        stored = json.loads((self.switch / "accounts" / "1" / "auth.json").read_text())
        self.assertEqual(next(iter(stored.values()))["refresh_token"], "refreshed")
        self.assertEqual(len(self.seq()["accounts"]), 1)

    def test_sw_and_to(self):
        self.add_two()
        self.run_gas("to", "1")
        self.assertEqual(self.run_gas("whoami").stdout.strip(), "a@x.com")
        self.run_gas("sw")
        self.assertEqual(self.run_gas("whoami").stdout.strip(), "b@x.com")
        self.run_gas("sw")
        self.assertEqual(self.run_gas("whoami").stdout.strip(), "a@x.com")

    def test_to_by_email_and_profile(self):
        self.add_two()
        self.run_gas("profile", "1", "personal")
        self.run_gas("profile", "2", "work")
        self.run_gas("to", "personal")
        self.assertEqual(self.run_gas("whoami").stdout.strip(), "a@x.com")
        self.run_gas("to", "b@x.com")
        self.assertEqual(self.run_gas("whoami").stdout.strip(), "b@x.com")

    def test_dry_run_does_not_switch(self):
        self.add_two()
        before = (self.grok / "auth.json").read_text()
        r = self.run_gas("-n", "to", "1")
        self.assertIn("[DRY RUN]", r.stdout)
        self.assertEqual((self.grok / "auth.json").read_text(), before)

    def test_switch_backs_up_refreshed_token(self):
        self.add_two()
        refreshed = sample_auth("b@x.com", "B", "B")
        refreshed["https://auth.x.ai::client-id"]["refresh_token"] = "live-refreshed-b"
        self.write_active(refreshed)
        self.run_gas("to", "1")
        stored_b = json.loads((self.switch / "accounts" / "2" / "auth.json").read_text())
        self.assertEqual(next(iter(stored_b.values()))["refresh_token"], "live-refreshed-b")

    def test_unmanaged_live_rejects_switch(self):
        """ccs 0.4: switching while live is unmanaged must refuse (don't lose creds)."""
        self.write_active(sample_auth("a@x.com"))
        self.run_gas("add")
        # live becomes unmanaged account
        self.write_active(sample_auth("orphan@x.com", "O", "O"))
        r = self.run_gas("to", "1", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not managed", r.stderr)
        # orphan live must remain (not overwritten)
        self.assertEqual(self.run_gas("whoami").stdout.strip(), "orphan@x.com")

    def test_sw_auto_adds_unmanaged_then_requires_rerun(self):
        self.write_active(sample_auth("a@x.com"))
        self.run_gas("add")
        self.write_active(sample_auth("c@x.com", "C", "C"))
        r = self.run_gas("sw")
        self.assertIn("was not managed", r.stdout)
        self.assertIn("Account-2", r.stdout)
        # still on c until second sw
        self.assertEqual(self.run_gas("whoami").stdout.strip(), "c@x.com")
        self.run_gas("sw")
        self.assertEqual(self.run_gas("whoami").stdout.strip(), "a@x.com")

    def test_lock_serializes_switch(self):
        """Second switch waits/fails if lock held; after release works."""
        self.add_two()
        lock = self.switch / ".switch.lock"
        lock.mkdir()
        (lock / "pid").write_text("1")  # PID 1 usually exists... use fake dead pid
        # Use a high dead pid that won't be alive
        (lock / "pid").write_text("99999999")
        # Should steal stale lock and succeed
        r = self.run_gas("to", "1")
        self.assertIn("switched", r.stdout)
        self.assertFalse(lock.exists())  # released

    def test_lock_busy_with_live_pid(self):
        self.add_two()
        lock = self.switch / ".switch.lock"
        lock.mkdir()
        (lock / "pid").write_text(str(os.getpid()))  # this process is alive
        env = self.env.copy()
        env["GAS_LOCK_TIMEOUT_SECS"] = "0.4"
        r = self.run_gas("to", "1", check=False, env=env)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("lock", r.stderr.lower())
        import shutil

        shutil.rmtree(lock, ignore_errors=True)

    def test_silent_mode(self):
        self.add_two()
        env = self.env.copy()
        env["GAS_SILENT"] = "1"
        r = self.run_gas("to", "1", env=env)
        self.assertEqual(r.stdout.strip(), "")
        self.assertEqual(self.run_gas("whoami").stdout.strip(), "a@x.com")

    def test_config_dir_and_exec(self):
        self.add_two()
        r = self.run_gas("config-dir", "1")
        self.assertIn("export GROK_HOME=", r.stdout)
        # last line is export
        export_line = [ln for ln in r.stdout.strip().splitlines() if ln.startswith("export ")][-1]
        home = export_line.split("=", 1)[1].strip().strip('"')
        self.assertTrue(Path(home).joinpath("auth.json").exists())
        auth = json.loads(Path(home).joinpath("auth.json").read_text())
        self.assertEqual(next(iter(auth.values()))["email"], "a@x.com")

        # exec: run python that prints GROK_HOME and auth email
        script = (
            "import os,json; "
            "print(os.environ['GROK_HOME']); "
            "print(json.load(open(os.path.join(os.environ['GROK_HOME'],'auth.json')))"
            "[list(json.load(open(os.path.join(os.environ['GROK_HOME'],'auth.json'))).keys())[0]]['email'])"
        )
        # simpler script
        script = (
            "import os,json,pathlib;"
            "h=os.environ['GROK_HOME'];"
            "a=json.loads(pathlib.Path(h,'auth.json').read_text());"
            "print(next(iter(a.values()))['email'])"
        )
        r = self.run_gas("exec", "1", "--", sys.executable, "-c", script)
        self.assertEqual(r.returncode, 0, msg=r.stderr + r.stdout)
        self.assertIn("a@x.com", r.stdout)

    def test_exec_dry_run(self):
        self.add_two()
        r = self.run_gas("-n", "exec", "1", "--", "echo", "hi")
        self.assertIn("[DRY RUN]", r.stdout)

    def test_rm_and_check_status(self):
        self.write_active(sample_auth())
        self.run_gas("add")
        self.run_gas("profile", "1", "main")
        self.assertEqual(self.seq()["accounts"]["1"]["profile"], "main")
        self.assertIn("All checks passed", self.run_gas("check").stdout)
        self.assertIn("alice@example.com", self.run_gas("status").stdout)
        self.run_gas("rm", "1", "-y")
        self.assertEqual(self.seq()["accounts"], {})

    def test_dir_auto(self):
        self.add_two()
        work = self.base / "workproj"
        work.mkdir()
        self.run_gas("dir", str(work), "1")
        r = subprocess.run(
            [sys.executable, str(GAS), "auto"],
            env=self.env,
            cwd=str(work),
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("switched", r.stdout)
        self.assertEqual(self.run_gas("whoami").stdout.strip(), "a@x.com")

    def test_legacy_save_use(self):
        self.write_active(sample_auth())
        self.run_gas("save", "personal")
        self.assertEqual(self.seq()["accounts"]["1"]["profile"], "personal")
        self.write_active(sample_auth("b@x.com", "B", "B"))
        self.run_gas("add")
        self.run_gas("use", "personal")
        self.assertEqual(self.run_gas("whoami").stdout.strip(), "alice@example.com")

    def test_migrate_v1_profiles(self):
        pdir = self.switch / "profiles" / "personal"
        pdir.mkdir(parents=True)
        auth = sample_auth("old@x.com")
        (pdir / "auth.json").write_text(json.dumps(auth))
        (pdir / "meta.json").write_text(json.dumps({"email": "old@x.com"}))
        (self.switch / "state.json").write_text(json.dumps({"current": "personal"}))
        self.write_active(auth)
        r = self.run_gas("ls")
        self.assertIn("old@x.com", r.stdout)
        self.assertTrue((self.switch / "sequence.json").exists())

    def test_add_without_auth_fails(self):
        r = self.run_gas("add", check=False)
        self.assertNotEqual(r.returncode, 0)

    def test_stats(self):
        self.add_two()
        self.run_gas("to", "1")
        r = self.run_gas("stats")
        self.assertIn("Switches", r.stdout)

    def test_ls_no_usage_flag(self):
        self.write_active(sample_auth())
        self.run_gas("add")
        r = self.run_gas("ls", "--no-usage")
        self.assertIn("alice@example.com", r.stdout)
        self.assertIn("(active)", r.stdout)
        # Fresh sample token: no re-login banner
        self.assertNotIn("need re-login", r.stdout)

    def test_usage_disabled_shows_hint(self):
        self.write_active(sample_auth())
        self.run_gas("add")
        r = self.run_gas("usage")
        self.assertIn("Credit Usage", r.stdout)
        self.assertIn("disabled", r.stdout.lower())

    def test_ls_flags_expired_auth_offline(self):
        """Local-only: expired access without refresh_token → needs re-login."""
        auth = sample_auth("dead@x.com")
        entry = next(iter(auth.values()))
        entry["expires_at"] = "2020-01-01T00:00:00Z"
        entry.pop("refresh_token", None)
        self.write_active(auth)
        self.run_gas("add")
        r = self.run_gas("ls", "--no-usage")
        self.assertIn("re-login", r.stdout)
        self.assertIn("grok login", r.stdout)

    def test_sync_live_to_managed_on_command(self):
        """Any gas command should mirror refreshed live tokens into the active slot."""
        self.write_active(sample_auth("a@x.com"))
        self.run_gas("add")
        # Simulate Grok refreshing live tokens
        live = sample_auth("a@x.com")
        next(iter(live.values()))["key"] = "brand-new-access"
        next(iter(live.values()))["refresh_token"] = "brand-new-refresh"
        self.write_active(live)
        self.run_gas("whoami")
        stored = json.loads((self.switch / "accounts" / "1" / "auth.json").read_text())
        entry = next(iter(stored.values()))
        self.assertEqual(entry["key"], "brand-new-access")
        self.assertEqual(entry["refresh_token"], "brand-new-refresh")


class UsageUnitTest(unittest.TestCase):
    """Pure unit tests for usage parsers / formatters (no subprocess)."""

    def setUp(self) -> None:
        # Import extensionless `gas` script as a module for helper tests.
        import importlib.util
        from importlib.machinery import SourceFileLoader

        loader = SourceFileLoader("gas_mod", str(GAS))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        assert spec and spec.loader
        self.gas = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.gas)

    def test_parse_usage_payloads_weekly_and_monthly(self):
        credits = {
            "config": {
                "currentPeriod": {
                    "type": "USAGE_PERIOD_TYPE_WEEKLY",
                    "start": "2026-07-20T00:00:00+00:00",
                    "end": "2026-07-27T00:00:00+00:00",
                },
                "creditUsagePercent": 85.0,
                "productUsage": [
                    {"product": "GrokBuild", "usagePercent": 78.0},
                    {"product": "GrokChat", "usagePercent": 4.0},
                ],
                "onDemandCap": {"val": 0},
                "onDemandUsed": {"val": 0},
                "prepaidBalance": {"val": 0},
            }
        }
        monthly = {
            "config": {
                "monthlyLimit": {"val": 15000},
                "used": {"val": 12650},
                "billingPeriodStart": "2026-07-01T00:00:00+00:00",
                "billingPeriodEnd": "2026-08-01T00:00:00+00:00",
            }
        }
        u = self.gas.parse_usage_payloads(credits, monthly, email="a@x.com", account=1)
        self.assertEqual(u["weekly_percent"], 85.0)
        self.assertEqual(u["monthly_used"], 12650.0)
        self.assertEqual(u["monthly_limit"], 15000.0)
        self.assertEqual(u["products"]["GrokBuild"], 78.0)
        self.assertIsNone(u["error"])

        compact = self.gas.format_usage_compact(u)
        self.assertIn("85% used", compact)
        self.assertIn("$126.50/$150", compact)
        self.assertNotIn("monthly", compact)
        self.assertRegex(compact, r"Resets in \d+d \d+h \d+m|Resets in \d+h \d+m|Resets in \d+m|Reset due")

    def test_parse_usage_monthly_only_over(self):
        monthly = {
            "config": {
                "monthlyLimit": {"val": 4000},
                "used": {"val": 6048},
            }
        }
        u = self.gas.parse_usage_payloads(None, monthly, email="b@x.com", account=2)
        self.assertIsNone(u["weekly_percent"])
        compact = self.gas.format_usage_compact(u)
        self.assertIn("$60.48/$40!", compact)

    def test_parse_usage_omitted_weekly_percent_is_zero(self):
        """Web UI shows 0% when creditUsagePercent is missing but weekly period exists."""
        credits = {
            "config": {
                "currentPeriod": {
                    "type": "USAGE_PERIOD_TYPE_WEEKLY",
                    "start": "2026-07-23T18:56:17.204886+00:00",
                    "end": "2026-07-30T18:56:17.204886+00:00",
                },
                "onDemandCap": {"val": 0},
                "onDemandUsed": {"val": 0},
                "isUnifiedBillingUser": True,
                "prepaidBalance": {"val": 0},
                "billingPeriodStart": "2026-07-23T18:56:17.204886+00:00",
                "billingPeriodEnd": "2026-07-30T18:56:17.204886+00:00",
            }
        }
        monthly = {
            "config": {
                "monthlyLimit": {"val": 15000},
                "used": {"val": 4615},
            }
        }
        u = self.gas.parse_usage_payloads(credits, monthly, email="c@x.com", account=3)
        self.assertEqual(u["weekly_percent"], 0.0)
        compact = self.gas.format_usage_compact(u)
        self.assertIn("0% used", compact)
        self.assertIn("$46.15/$150", compact)
        self.assertRegex(compact, r"Resets in |Reset due")

    def test_money_and_val(self):
        self.assertEqual(self.gas._money(15000), "150")
        self.assertEqual(self.gas._money(12650), "126.50")
        self.assertEqual(self.gas._val_num({"val": 12}), 12.0)
        self.assertEqual(self.gas._val_num(3), 3.0)
        self.assertIsNone(self.gas._val_num(None))

    def test_format_reset_absolute_and_hint(self):
        ts = "2026-07-27T19:45:12.968910+00:00"
        abs_s = self.gas.format_reset_absolute(ts, local=False)
        self.assertEqual(abs_s, "2026-07-27 19:45 UTC")
        hint = self.gas.format_reset_hint(ts)
        self.assertIsNotNone(hint)
        assert hint is not None
        self.assertIn("(", hint)  # absolute + relative
        detail = "\n".join(
            self.gas.format_usage_detail(
                {
                    "weekly_percent": 50.0,
                    "weekly_end": ts,
                    "monthly_used": 1000.0,
                    "monthly_limit": 15000.0,
                    "monthly_end": "2026-08-01T00:00:00+00:00",
                    "products": {},
                },
                indent="",
            )
        )
        self.assertIn("Weekly usage:", detail)
        self.assertIn("reset ", detail)
        self.assertIn("Monthly reset:", detail)

    def test_format_reset_countdown(self):
        from datetime import datetime, timedelta, timezone

        future = datetime.now(timezone.utc) + timedelta(days=5, hours=21, minutes=18)
        s = self.gas.format_reset_countdown(future.isoformat())
        self.assertIsNotNone(s)
        assert s is not None
        self.assertTrue(s.startswith("Resets in "))
        self.assertIn("d", s)
        self.assertIn("h", s)
        self.assertIn("m", s)
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        self.assertEqual(self.gas.format_reset_countdown(past), "Reset due")

    def test_apply_token_refresh(self):
        auth = sample_auth("a@x.com")
        refreshed = self.gas.apply_token_refresh(
            auth,
            {
                "access_token": "new-at",
                "refresh_token": "new-rt",
                "expires_in": 3600,
            },
        )
        entry = next(iter(refreshed.values()))
        self.assertEqual(entry["key"], "new-at")
        self.assertEqual(entry["refresh_token"], "new-rt")
        self.assertIn("expires_at", entry)

    def test_format_usage_detail_error(self):
        lines = self.gas.format_usage_detail({"error": "refresh_failed"}, indent="  ")
        self.assertTrue(any("needs re-login" in ln for ln in lines))
        self.assertTrue(any("grok login" in ln for ln in lines))

    def test_format_usage_compact_relogin(self):
        self.assertIn(
            "re-login",
            self.gas.format_usage_compact({"error": "refresh_failed"}),
        )
        self.assertIn(
            "n/a",
            self.gas.format_usage_compact({"error": "fetch_failed"}),
        )

    def test_inspect_account_auth_and_footer(self):
        health_ok = {
            "status": "ok",
            "needs_relogin": False,
            "has_refresh": True,
            "expires_at": "2099-01-01T00:00:00Z",
            "email": "a@x.com",
        }
        self.assertFalse(self.gas.account_needs_relogin(None, health_ok))
        self.assertTrue(
            self.gas.account_needs_relogin({"error": "refresh_failed"}, health_ok)
        )
        seq = {
            "accounts": {
                "2": {"email": "b@x.com", "profile": "work"},
                "3": {"email": "c@x.com"},
            }
        }
        footer = "\n".join(self.gas.format_relogin_footer([2, 3], seq))
        self.assertIn("re-login 2, 3", footer)
        self.assertIn("gas to 2", footer)
        self.assertEqual(len(self.gas.format_relogin_footer([2, 3], seq)), 1)

    def test_fetch_account_usage_with_mock_http(self):
        """Mock _http_json so we never hit the network."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        grok = base / "grok"
        switch = base / "switch"
        grok.mkdir()
        switch.mkdir()

        # Point module paths at temp dirs
        self.gas.GROK_DIR = grok
        self.gas.AUTH_PATH = grok / "auth.json"
        self.gas.SWITCH_DIR = switch
        self.gas.ACCOUNTS_DIR = switch / "accounts"
        self.gas.SEQUENCE_PATH = switch / "sequence.json"
        self.gas.USAGE_CACHE_PATH = switch / "usage-cache.json"
        self.gas.ACCOUNTS_DIR.mkdir(parents=True)

        auth = sample_auth("a@x.com")
        # Not expired
        next(iter(auth.values()))["expires_at"] = "2099-01-01T00:00:00Z"
        self.gas.write_json(self.gas.AUTH_PATH, auth)
        self.gas.write_json(self.gas.account_auth_path(1), auth)
        self.gas.write_json(
            self.gas.SEQUENCE_PATH,
            {
                "version": 2,
                "activeAccountNumber": 1,
                "sequence": [1],
                "accounts": {
                    "1": {
                        "email": "a@x.com",
                        "profile": "main",
                        "switchCount": 0,
                        "totalSeconds": 0,
                    }
                },
            },
        )

        def fake_http(method, url, headers=None, data=None, timeout=None):
            if "format=credits" in url:
                return 200, {
                    "config": {
                        "creditUsagePercent": 42.0,
                        "currentPeriod": {
                            "type": "USAGE_PERIOD_TYPE_WEEKLY",
                            "end": "2099-01-08T00:00:00+00:00",
                        },
                        "productUsage": [{"product": "GrokBuild", "usagePercent": 40.0}],
                    }
                }
            if url.rstrip("/").endswith("/billing") or url.endswith("/billing"):
                return 200, {
                    "config": {
                        "monthlyLimit": {"val": 10000},
                        "used": {"val": 2500},
                    }
                }
            return 404, None

        orig = self.gas._http_json
        self.gas._http_json = fake_http
        # Force network path even if env says off
        old = os.environ.get("GAS_USAGE")
        os.environ["GAS_USAGE"] = "1"
        try:
            u = self.gas.fetch_account_usage(1, force=True)
            self.assertEqual(u["weekly_percent"], 42.0)
            self.assertEqual(u["monthly_used"], 2500.0)
            self.assertEqual(u["monthly_limit"], 10000.0)
            self.assertIsNone(u.get("error"))
            # Cache written
            self.assertTrue(self.gas.USAGE_CACHE_PATH.exists())
            # Second call hits cache (still valid)
            u2 = self.gas.fetch_account_usage(1, force=False)
            self.assertEqual(u2["weekly_percent"], 42.0)
        finally:
            self.gas._http_json = orig
            if old is None:
                os.environ.pop("GAS_USAGE", None)
            else:
                os.environ["GAS_USAGE"] = old


if __name__ == "__main__":
    unittest.main()
