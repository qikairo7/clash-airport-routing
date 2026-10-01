import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from policy import byte_amount, new_ledger, observe_health, policy_reload_allowed, select_candidates, update_ledger


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.rows = [self.node("P-US", "primary", "us", "in-1", "out-1"),
                     self.node("P-JP", "primary", "jp", "in-2", "out-2"),
                     self.node("B-US", "bulk", "us", "in-3", "out-3")]
        self.policy = {"services": {"chatgpt": {"preferred_country": "us"}}}

    def node(self, alias, source, country, ingress, exit_id):
        return {"alias": alias, "source": source, "exit_country": country,
                "ingress_id": ingress, "exit_id": exit_id,
                "evidence": {"chatgpt": {"checked_at": self.now.isoformat(),
                                         "transport": "passed", "business": "pending"}}}

    def test_same_country_backup_precedes_foreign_primary(self):
        selected, _ = select_candidates(self.rows, "chatgpt", ["primary", "bulk"], self.policy, self.now)
        self.assertEqual([row["alias"] for row in selected], ["P-US", "B-US", "P-JP"])

    def test_reload_waits_for_connections_but_budget_lock_is_immediate(self):
        active = {"connections": [{"id": "existing-stream"}]}
        self.assertFalse(policy_reload_allowed(active))
        self.assertTrue(policy_reload_allowed(active, budget_changed=True))
        self.assertTrue(policy_reload_allowed({"connections": []}))

    def test_stable_exit_precedes_a_faster_named_node(self):
        self.policy["services"]["chatgpt"]["preferred_exit_id"] = "out-3"
        selected, _ = select_candidates(self.rows, "chatgpt", ["primary", "bulk"], self.policy, self.now)
        self.assertEqual(selected[0]["alias"], "B-US")

    def test_expired_and_failed_business_do_not_enter_auto_pool(self):
        self.rows[0]["evidence"]["chatgpt"]["checked_at"] = (self.now - timedelta(hours=73)).isoformat()
        self.rows[1]["evidence"]["chatgpt"]["business"] = "failed"
        selected, excluded = select_candidates(self.rows, "chatgpt", ["primary", "bulk"], self.policy, self.now)
        self.assertEqual([row["alias"] for row in selected], ["B-US"])
        self.assertEqual(set(excluded.values()), {"qualification_expired", "business_not_passed"})

    def test_anonymous_success_is_not_business_qualification(self):
        self.policy["require_business"] = True
        selected, _ = select_candidates(self.rows, "chatgpt", ["primary", "bulk"], self.policy, self.now)
        self.assertEqual(selected, [])

    def test_deduplicate_route_and_keep_distinct_exit(self):
        duplicate = copy.deepcopy(self.rows[0])
        duplicate["alias"] = "P-US-duplicate"
        selected, excluded = select_candidates(self.rows + [duplicate], "chatgpt", ["primary", "bulk"], self.policy, self.now)
        self.assertEqual(len(selected), 3)
        self.assertEqual(excluded[duplicate["alias"]], "duplicate_ingress_and_exit")

    def test_blocked_source_removed_across_countries(self):
        self.policy["blocked_sources"] = ["primary"]
        selected, _ = select_candidates(self.rows, "chatgpt", ["primary", "bulk"], self.policy, self.now)
        self.assertEqual([row["alias"] for row in selected], ["B-US"])

    def test_quarantine_requires_distinct_samples_and_spaced_recovery(self):
        state = {}
        for second in [0, 60, 120]:
            state = observe_health(state, False, (self.now + timedelta(seconds=second)).isoformat())
        self.assertTrue(state["quarantined"])
        unchanged = observe_health(state, False, state["last_sample_at"])
        self.assertEqual(unchanged, state)
        for second in [180, 190, 240]:
            state = observe_health(state, True, (self.now + timedelta(seconds=second)).isoformat())
        self.assertTrue(state["quarantined"])
        state = observe_health(state, True, (self.now + timedelta(seconds=300)).isoformat())
        self.assertFalse(state["quarantined"])

    def test_byte_units_and_invalid_numbers(self):
        self.assertEqual(byte_amount("250", "GB"), 250_000_000_000)
        self.assertEqual(byte_amount("250", "GiB"), 268_435_456_000)
        for value, unit in [("nan", "GB"), ("bad", "GB"), (-1, "GB"), (1, "unknown")]:
            with self.assertRaises(ValueError):
                byte_amount(value, unit)

    def test_budget_is_locked_at_initial_baseline(self):
        ledger = new_ledger(950, 1000, 900, {"downloadTotal": 0, "uploadTotal": 0})
        self.assertTrue(ledger["blocked"])

    def test_mihomo_null_connections_are_an_empty_snapshot(self):
        snapshot = {"downloadTotal": 0, "uploadTotal": 0, "connections": None}
        ledger = new_ledger(0, 1000, 900, snapshot)
        updated = update_ledger(ledger, snapshot, {"P": 1})
        self.assertEqual(updated["seen"], {})
        self.assertFalse(updated["blocked"])

    def test_failed_observation_breaks_recovery_streak(self):
        state = {"quarantined": True, "quarantine_since": (self.now - timedelta(minutes=10)).isoformat(),
                 "successes": 2, "last_sample_at": (self.now - timedelta(seconds=10)).isoformat(),
                 "last_counted_failure_at": (self.now - timedelta(seconds=20)).isoformat()}
        failed = observe_health(state, False, self.now.isoformat())
        self.assertEqual(failed["successes"], 0)
        recovered_once = observe_health(failed, True, (self.now + timedelta(seconds=60)).isoformat())
        self.assertTrue(recovered_once["quarantined"])

    def test_counter_reset_keeps_protection_locked(self):
        state = new_ledger(0, 1000, 900, {"downloadTotal": 100, "uploadTotal": 0})
        result = update_ledger(state, {"downloadTotal": 0, "uploadTotal": 0}, {"P": 5})
        self.assertTrue(result["blocked"])

    def test_unknown_closed_connection_uses_highest_multiplier(self):
        state = new_ledger(0, 1000, 900, {"downloadTotal": 0, "uploadTotal": 0})
        result = update_ledger(state, {"downloadTotal": 200, "uploadTotal": 0}, {"P": 5})
        self.assertEqual(result["upper_bound_bytes"], 1000)
        self.assertTrue(result["blocked"])


if __name__ == "__main__":
    unittest.main()
