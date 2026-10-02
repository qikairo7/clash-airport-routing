import json
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from monitor import ROOT, Monitor, save, state_digest
from policy import counter_segment, limited_candidates, new_ledger, resume_counter_segment, update_ledger
from verge import VergeWatcher, fingerprint, initial_transport, metadata_name
from availability import Availability


class MonitorTests(unittest.TestCase):
    def test_old_frozen_provider_health_is_not_inherited_by_changed_parameters(self):
        watcher = Availability()
        watcher.expected_endpoints = {"same-name": "new-version"}
        watcher.provider_paths = {"old": "policy-providers/old-version-alias.yaml", "new": "policy-providers/new-version-alias.yaml"}
        watcher.root_endpoints = {"same-name": "old-version"}
        url = "https://example.invalid/health"
        providers = {"old": {"proxies": [{"name": "same-name", "extra": {url: {"history": [{"time": "2026-10-01T09:00:00Z", "delay": 10}]}}}]}}
        self.assertIsNone(watcher.sample(providers, "same-name", url))
        self.assertFalse(watcher.provider_matches("default", "same-name"))
        self.assertTrue(watcher.provider_matches("new", "same-name"))

    def test_exit_recheck_does_not_restore_stale_service_whitelist(self):
        node = {"provider": "primary", "name": "same-name", "initial_proof_valid": False,
                "checked_at": "2026-10-01T09:00:00Z", "checks": {"openai": {"passed": True}}}
        services = {"AI ChatGPT Codex": {("primary", "same-name")}}
        self.assertFalse(initial_transport(node, "AI ChatGPT Codex", services))
        self.assertFalse(initial_transport(node, "OpenAI 自动（1倍优先）", services))
        node["initial_proof_valid"] = True
        self.assertTrue(initial_transport(node, "AI ChatGPT Codex", services))
        self.assertFalse(initial_transport(node, "AI Claude", services))

    def test_service_monitor_uses_runtime_health_url_instead_of_original_homepage(self):
        watcher = VergeWatcher.__new__(VergeWatcher)
        watcher.runtime = {}
        ordinary = ["开发", "GitHub API", "GitHub 文件", "容器", "社交", "Telegram 线路", "媒体大流量", "通用海外"]
        pools = {name: {"candidates": []} for name in ordinary}
        pools.update({name: {"active_candidates": [], "milk_backup": []} for name in ["OpenAI", "Claude", "Google"]})
        merge = {"x-verified-pools": {"pools": pools}, "x-service-pools": [
            {"name": "ChatGPT Codex", "url": "https://chatgpt.com/", "status": 200, "candidates": []}]}
        names = ordinary + [name + " 自动（1倍优先）" for name in ["OpenAI", "Claude", "Google"]]
        groups = [{"name": name, "url": "https://www.gstatic.com/generate_204", "expected-status": 204} for name in names]
        groups.append({"name": "AI ChatGPT Codex 候选", "url": "https://chatgpt.com/robots.txt", "expected-status": 200})
        definitions = watcher.definitions(merge, {"proxy-groups": groups})
        self.assertEqual(definitions["AI ChatGPT Codex"]["url"], "https://chatgpt.com/robots.txt")
        self.assertEqual(definitions["AI ChatGPT Codex"]["status"], 200)

    def calibration_inputs(self):
        observed = datetime.now(timezone.utc)
        monitor = Monitor.__new__(Monitor)
        monitor.settings = {"nodes": [{"alias": "known", "source": "primary", "multiplier": 3}]}
        identity = [1, (observed - timedelta(hours=1)).timestamp()]
        state = {"core_identity": identity, "created_at": (observed - timedelta(minutes=10)).isoformat(),
                 "budgets": {"primary": {"upper_bound_bytes": 100, "max_multiplier": 4}}}
        return monitor, observed, identity, state

    def test_subscription_configuration_without_managed_groups_is_explicit_error(self):
        watcher = VergeWatcher.__new__(VergeWatcher)
        watcher.runtime = {}
        ordinary = ["开发", "GitHub API", "GitHub 文件", "容器", "社交", "Telegram 线路", "媒体大流量", "通用海外"]
        pools = {name: {"candidates": []} for name in ordinary}
        pools.update({name: {"active_candidates": [], "milk_backup": []} for name in ["OpenAI", "Claude", "Google"]})
        merge = {"x-verified-pools": {"pools": pools}, "x-service-pools": []}
        with self.assertRaises(ValueError):
            watcher.definitions(merge, {"proxy-groups": []})

    def test_billing_bridge_uses_last_checkpoint_before_refresh_and_historical_multiplier(self):
        monitor, observed, identity, state = self.calibration_inputs()
        state["checkpoints"] = [{"at": (observed - timedelta(seconds=5)).isoformat(), "counter": 100, "core_identity": identity},
                                {"at": (observed + timedelta(seconds=1)).isoformat(), "counter": 200, "core_identity": identity}]
        amount, method = monitor.calibration_bridge(state, {"downloadTotal": 250, "uploadTotal": 0}, identity, "primary", observed)
        self.assertEqual(amount, 600)
        self.assertEqual(method, "counter_checkpoint_before_local_refresh")

    def test_initial_migration_without_checkpoint_preserves_whole_old_estimate(self):
        monitor, observed, identity, state = self.calibration_inputs()
        amount, method = monitor.calibration_bridge(state, {"downloadTotal": 250, "uploadTotal": 0}, identity, "primary", observed)
        self.assertEqual(amount, 100)
        self.assertEqual(method, "legacy_conservative_overlap")

    def test_fresh_bill_after_uncontrolled_restart_covers_entire_new_counter(self):
        monitor, observed, identity, state = self.calibration_inputs()
        fresh_identity = [2, (observed - timedelta(seconds=5)).timestamp()]
        amount, method = monitor.calibration_bridge(state, {"downloadTotal": 25, "uploadTotal": 5}, fresh_identity, "primary", observed)
        self.assertEqual(amount, 120)
        self.assertIn("full_new_segment_overlap", method)

    def test_reset_counter_cannot_be_bridged_from_old_checkpoint(self):
        monitor, observed, identity, state = self.calibration_inputs()
        state["checkpoints"] = [{"at": (observed - timedelta(seconds=5)).isoformat(), "counter": 100, "core_identity": identity}]
        with self.assertRaises(ValueError):
            monitor.calibration_bridge(state, {"downloadTotal": 25, "uploadTotal": 0}, identity, "primary", observed)

    def test_parameter_change_invalidates_fingerprint_but_alias_change_does_not(self):
        node = {"name": "original", "type": "trojan", "server": "ingress", "port": 443, "password": "test-fixture"}
        original = fingerprint(node, {"ingress": "192.0.2.1"})
        node["name"] = "renamed"
        self.assertEqual(original, fingerprint(node, {"ingress": "192.0.2.1"}))
        node["port"] = 444
        self.assertNotEqual(original, fingerprint(node, {"ingress": "192.0.2.1"}))

    def test_counter_segment_keeps_estimate_and_lock(self):
        ledger = new_ledger(100, 1000, 900, {"downloadTotal": 50, "uploadTotal": 0})
        ledger.update(upper_bound_bytes=200, blocked=True, blocked_reason="test_threshold")
        fresh = counter_segment(ledger, {"downloadTotal": 10, "uploadTotal": 0})
        self.assertEqual(fresh["upper_bound_bytes"], 200)
        self.assertTrue(fresh["blocked"])
        advanced = update_ledger(fresh, {"downloadTotal": 20, "uploadTotal": 0}, {"known": 3})
        self.assertEqual(advanced["upper_bound_bytes"], 230)

    def test_delayed_connection_observation_cannot_reduce_conservative_upper(self):
        ledger = new_ledger(0, 1000, 900, {"downloadTotal": 0, "uploadTotal": 0})
        first = update_ledger(ledger, {"downloadTotal": 100, "uploadTotal": 0}, {"known": 3})
        first.update(lag_actual=100, lag_weighted=100)
        next_ledger = update_ledger(first, {"downloadTotal": 100, "uploadTotal": 0}, {"known": 3})
        self.assertGreaterEqual(next_ledger["upper_bound_bytes"], first["upper_bound_bytes"])

    def test_restart_carries_previous_usage_and_entire_new_counter_once(self):
        ledger = new_ledger(100, 1000, 900, {"downloadTotal": 500, "uploadTotal": 0})
        ledger.update(upper_bound_bytes=200, blocked=True, blocked_reason="core_restart_requires_new_billing_baseline")
        snapshot = {"downloadTotal": 20, "uploadTotal": 10}
        fresh = resume_counter_segment(ledger, snapshot, {"known": 3, "other": 1})
        self.assertEqual(fresh["baseline_bytes"], 100)
        self.assertEqual(fresh["upper_bound_bytes"], 290)
        self.assertFalse(fresh["blocked"])
        self.assertNotIn("blocked_reason", fresh)
        self.assertEqual(update_ledger(fresh, snapshot, {"known": 3})["upper_bound_bytes"], 290)
        self.assertEqual(ledger["upper_bound_bytes"], 200)

    def test_repeated_restarts_preserve_all_previous_segments(self):
        ledger = new_ledger(100, 1000, 900, {"downloadTotal": 500, "uploadTotal": 0})
        ledger.update(upper_bound_bytes=200)
        fresh = resume_counter_segment(ledger, {"downloadTotal": 20, "uploadTotal": 10}, {"known": 3})
        fresh = update_ledger(fresh, {"downloadTotal": 30, "uploadTotal": 10}, {"known": 3})
        resumed = resume_counter_segment(fresh, {"downloadTotal": 5, "uploadTotal": 0}, {"known": 3})
        self.assertEqual(resumed["upper_bound_bytes"], 335)
        unchanged = update_ledger(resumed, {"downloadTotal": 5, "uploadTotal": 0}, {"known": 3})
        self.assertEqual(unchanged["upper_bound_bytes"], 335)

    def test_restart_new_increment_is_accounted_after_resumed_counter(self):
        ledger = new_ledger(100, 1000, 900, {"downloadTotal": 500, "uploadTotal": 0})
        ledger.update(upper_bound_bytes=200, blocked=True, blocked_reason="counter_reset_requires_new_billing_baseline")
        fresh = resume_counter_segment(ledger, {"downloadTotal": 20, "uploadTotal": 10}, {"known": 3})
        advanced = update_ledger(fresh, {"downloadTotal": 30, "uploadTotal": 10}, {"known": 3})
        self.assertEqual(advanced["upper_bound_bytes"], 320)
        self.assertFalse(advanced["blocked"])

    def test_restart_preserves_real_budget_and_unrelated_locks(self):
        for reason in ["conservative_budget_threshold", "controlled_restart_gate", "manual_protection"]:
            with self.subTest(reason=reason):
                ledger = new_ledger(100, 1000, 900, {"downloadTotal": 500, "uploadTotal": 0})
                ledger.update(upper_bound_bytes=200, blocked=True, blocked_reason=reason)
                fresh = resume_counter_segment(ledger, {"downloadTotal": 10, "uploadTotal": 0}, {"known": 3})
                self.assertTrue(fresh["blocked"])
                self.assertEqual(fresh["blocked_reason"], reason)
                self.assertEqual(fresh["upper_bound_bytes"], 230)

    def test_restart_does_not_unlock_usage_that_reaches_threshold(self):
        ledger = new_ledger(100, 1000, 900, {"downloadTotal": 500, "uploadTotal": 0})
        ledger.update(upper_bound_bytes=770, blocked=True, blocked_reason="core_restart_requires_new_billing_baseline")
        fresh = resume_counter_segment(ledger, {"downloadTotal": 10, "uploadTotal": 0}, {"known": 3})
        self.assertEqual(fresh["upper_bound_bytes"], 800)
        self.assertTrue(fresh["blocked"])
        self.assertEqual(fresh["blocked_reason"], "conservative_budget_threshold")

    def test_restart_preserves_already_exceeded_budget(self):
        ledger = new_ledger(100, 1000, 900, {"downloadTotal": 500, "uploadTotal": 0})
        ledger.update(upper_bound_bytes=850, blocked=True, blocked_reason="conservative_budget_threshold")
        fresh = resume_counter_segment(ledger, {"downloadTotal": 10, "uploadTotal": 0}, {"known": 3})
        self.assertEqual(fresh["upper_bound_bytes"], 880)
        self.assertTrue(fresh["blocked"])
        self.assertEqual(fresh["blocked_reason"], "conservative_budget_threshold")

    def test_restart_rejects_invalid_new_counter_and_multiplier(self):
        ledger = new_ledger(100, 1000, 900, {"downloadTotal": 500, "uploadTotal": 0})
        with self.assertRaises(ValueError):
            resume_counter_segment(ledger, {"downloadTotal": -1, "uploadTotal": 0}, {"known": 3})
        with self.assertRaises(ValueError):
            resume_counter_segment(ledger, {"downloadTotal": 1, "uploadTotal": 0}, {"known": float("nan")})

    def test_restart_uses_historical_highest_multiplier(self):
        ledger = new_ledger(100, 1000, 900, {"downloadTotal": 500, "uploadTotal": 0})
        ledger.update(upper_bound_bytes=200, max_multiplier=5)
        fresh = resume_counter_segment(ledger, {"downloadTotal": 10, "uploadTotal": 0}, {"known": 1})
        self.assertEqual(fresh["upper_bound_bytes"], 250)
        self.assertEqual(fresh["max_multiplier"], 5)

    def test_candidate_limit_keeps_ingress_source_and_country_backups(self):
        rows = [{"alias": str(i), "source": source, "exit_country": country, "ingress_id": ingress, "exit_id": exit_id}
                for i, (source, country, ingress, exit_id) in enumerate([
                    ("primary", "us", "i1", "e1"), ("primary", "us", "i1", "e2"),
                    ("primary", "us", "i2", "e1"), ("bulk", "us", "i3", "e3"), ("primary", "jp", "i4", "e4")])]
        selected = limited_candidates(rows, "us", "e1", 4)
        self.assertEqual([row["alias"] for row in selected], ["0", "2", "3", "4"])

    def test_atomic_state_has_checksum_and_previous_snapshot(self):
        (ROOT / "local").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "local") as directory:
            path = Path(directory) / "state.json"
            state = {"version": 2, "budgets": {"primary": {"blocked": True}}}
            save(path, state)
            previous = path.read_bytes()
            state["reason"] = "changed"
            save(path, state)
            self.assertEqual(path.with_suffix(".previous.json").read_bytes(), previous)
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored["checksum"], state_digest(stored))
            stored["budgets"]["primary"]["blocked"] = False
            self.assertNotEqual(stored["checksum"], state_digest(stored))

    def test_single_instance_uses_real_file_lock(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "local") as directory:
            # 只使用真实文件锁，无控制器或流量请求。
            first, second = Monitor.__new__(Monitor), Monitor.__new__(Monitor)
            first.state_path = second.state_path = Path(directory) / "state.json"
            with first.exclusive():
                with self.assertRaises(OSError):
                    with second.exclusive():
                        self.fail("第二个写入者不应该获取同一台账锁")
            with second.exclusive():
                pass

    def test_subscription_metadata_is_excluded_from_nodes(self):
        self.assertTrue(metadata_name("3.36 G | 500.00 G"))
        self.assertTrue(metadata_name("Expire Date: 2026/11/01"))
        self.assertFalse(metadata_name("USA Seattle 01"))


if __name__ == "__main__":
    unittest.main()
