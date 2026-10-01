import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation


def utc(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("测量时间需要包含时区")
    return parsed.astimezone(timezone.utc)


def byte_amount(value, unit):
    units = {"B": 1, "GB": 10**9, "GiB": 1024**3}
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("额度需要有效数字") from None
    if unit not in units or not amount.is_finite() or amount < 0:
        raise ValueError("额度需要非负数和明确的 B、GB 或 GiB 单位")
    return int(amount * units[unit])


def policy_reload_allowed(snapshot, budget_changed=False):
    # 完整重载会重建来源；普通候选调整等现有连接结束后再部署。
    # 额度锁定仍须立即执行，不能因长连接继续消耗已经受保护的订阅。
    return budget_changed or not snapshot.get("connections")


def select_candidates(rows, service, source_order, policy, now=None):
    now = now or datetime.now(timezone.utc)
    max_age = policy.get("qualification_max_age_hours", 72)
    if isinstance(max_age, bool) or not isinstance(max_age, (int, float)) or not math.isfinite(max_age) or max_age <= 0:
        raise ValueError("qualification_max_age_hours 必须为正数")
    preference = policy.get("services", {}).get(service, {})
    country = str(preference.get("preferred_country", "")).lower()
    exit_id = preference.get("preferred_exit_id")
    blocked = set(policy.get("blocked_sources", []))
    selected, excluded = [], {}
    for row in rows:
        alias = row["alias"]
        if row["source"] in blocked:
            excluded[alias] = "source_budget_blocked"
            continue
        evidence = row.get("evidence", {}).get(service, row.get("evidence", {}).get("transport", {}))
        if not evidence.get("checked_at"):
            excluded[alias] = "missing_measurement_time"
            continue
        checked = utc(evidence["checked_at"])
        if checked > now or now >= checked + timedelta(hours=max_age):
            excluded[alias] = "qualification_expired"
            continue
        if evidence.get("transport") != "passed":
            excluded[alias] = "transport_not_passed"
            continue
        business = evidence.get("business", "pending")
        if business not in {"passed", "failed", "pending"}:
            raise ValueError("业务证据必须为 passed、failed 或 pending")
        if business == "passed":
            observed = evidence.get("business_checked_at")
            if not observed or utc(observed) > now or now >= utc(observed) + timedelta(hours=max_age):
                business = "pending"
        if business == "failed" or (policy.get("require_business", False) and business != "passed"):
            excluded[alias] = "business_not_passed"
            continue
        if policy.get("health", {}).get(service, {}).get(alias, {}).get("quarantined", False):
            excluded[alias] = "temporarily_quarantined"
            continue
        selected.append(row)

    def order(row):
        actual_country = str(row.get("exit_country", "")).lower()
        same_exit = bool(exit_id and row.get("exit_id") == exit_id)
        same_country = bool(country and actual_country == country)
        priority = row.get("priority", 0)
        if isinstance(priority, bool) or not isinstance(priority, (int, float)) or not math.isfinite(priority):
            raise ValueError("候选 priority 必须为有限数值")
        return (0 if same_exit else 1 if same_country else 2,
                source_order.index(row["source"]), priority)

    selected.sort(key=order)
    routes, unique = set(), []
    for row in selected:
        # 缺少实测出口时保留候选，但不能把它计为已确认的独立线路。
        route = (row.get("ingress_id"), row.get("exit_id"))
        if all(route) and route in routes:
            excluded[row["alias"]] = "duplicate_ingress_and_exit"
            continue
        if all(route):
            routes.add(route)
        unique.append(row)
    return unique, excluded


def observe_health(state, passed, sampled_at, failure_limit=3, recovery_limit=3,
                   cooldown_seconds=180, recovery_spacing_seconds=60, failure_spacing_seconds=60):
    if not isinstance(passed, bool):
        raise ValueError("健康观测必须是明确的成功或失败")
    sampled = utc(sampled_at)
    previous = state.get("last_sample_at")
    if previous and sampled <= utc(previous):
        return state
    next_state = dict(state)
    next_state["last_sample_at"] = sampled.isoformat()
    if not passed:
        next_state["successes"] = 0
        last_failure = state.get("last_counted_failure_at")
        if last_failure and (sampled - utc(last_failure)).total_seconds() < failure_spacing_seconds:
            return next_state
        next_state.update(failures=state.get("failures", 0) + 1, successes=0)
        next_state["last_counted_failure_at"] = sampled.isoformat()
        if next_state["failures"] >= failure_limit:
            next_state.update(quarantined=True, quarantine_since=sampled.isoformat())
        return next_state
    next_state["failures"] = 0
    next_state.pop("last_counted_failure_at", None)
    if not state.get("quarantined"):
        next_state["successes"] = 0
        return next_state
    last_success = state.get("last_recovery_at")
    if last_success and (sampled - utc(last_success)).total_seconds() < recovery_spacing_seconds:
        return next_state
    next_state.update(successes=state.get("successes", 0) + 1, last_recovery_at=sampled.isoformat())
    elapsed = (sampled - utc(state["quarantine_since"])).total_seconds()
    if next_state["successes"] >= recovery_limit and elapsed >= cooldown_seconds:
        next_state.update(quarantined=False, successes=0)
    return next_state


def new_ledger(baseline_bytes, total_bytes, threshold_bytes, snapshot):
    if not 0 <= baseline_bytes <= total_bytes or not 0 < threshold_bytes <= total_bytes:
        raise ValueError("账单基线、总额度与保护阈值不符合范围")
    total = snapshot["downloadTotal"] + snapshot["uploadTotal"]
    return {"baseline_bytes": baseline_bytes, "total_bytes": total_bytes,
            "threshold_bytes": threshold_bytes, "base_counter": total, "last_counter": total,
            "observed_actual": 0, "observed_weighted": 0, "observed_other": 0,
            "lag_actual": 0, "lag_weighted": 0, "lag_other": 0, "upper_bound_bytes": 0,
            "blocked": baseline_bytes >= threshold_bytes, "seen": {row["id"]: row["download"] + row["upload"]
                                      for row in (snapshot.get("connections") or [])}}


def update_ledger(state, snapshot, multipliers):
    if not multipliers or any(not math.isfinite(value) or value <= 0 for value in multipliers.values()):
        raise ValueError("额度核算需要完整的正数倍率")
    total = snapshot["downloadTotal"] + snapshot["uploadTotal"]
    next_state = dict(state)
    next_state["seen"] = dict(state["seen"])
    if total < state["last_counter"]:
        next_state.update(blocked=True, blocked_reason="counter_reset_requires_new_billing_baseline")
        return next_state
    actual = total - state["base_counter"]
    unknown = max(0, actual - state["lag_actual"] - state["lag_other"])
    upper = unknown * max(multipliers.values()) + state["lag_weighted"] + state.get("carry_bytes", 0)
    upper = math.ceil(max(state.get("upper_bound_bytes", 0), upper))
    next_state.update(upper_bound_bytes=upper, last_counter=total,
                      lag_actual=state["observed_actual"], lag_other=state["observed_other"],
                      lag_weighted=state["observed_weighted"])
    for row in (snapshot.get("connections") or []):
        value = row["download"] + row["upload"]
        previous = state["seen"].get(row["id"])
        increment = max(0, value - previous) if previous is not None else 0
        multiplier = max((multipliers.get(name, 0) for name in row.get("chains", [])), default=0)
        if multiplier:
            next_state["observed_actual"] += increment
            next_state["observed_weighted"] += increment * multiplier
        else:
            next_state["observed_other"] += increment
        next_state["seen"][row["id"]] = value
    active = {row["id"] for row in (snapshot.get("connections") or [])}
    next_state["seen"] = {key: value for key, value in next_state["seen"].items() if key in active}
    if state["baseline_bytes"] + upper >= state["threshold_bytes"]:
        next_state.update(blocked=True, blocked_reason="conservative_budget_threshold")
    return next_state


def counter_segment(ledger, snapshot):
    next_ledger = new_ledger(ledger["baseline_bytes"], ledger["total_bytes"], ledger["threshold_bytes"], snapshot)
    next_ledger.update(carry_bytes=ledger["upper_bound_bytes"], upper_bound_bytes=ledger["upper_bound_bytes"],
                       blocked=ledger["blocked"])
    for key in ("blocked_reason", "billing_observed_at", "billing_version", "warning_bytes", "billing_bridge_method", "max_multiplier"):
        if key in ledger:
            next_ledger[key] = ledger[key]
    return next_ledger


def limited_candidates(rows, preferred_country="", preferred_exit_id=None, limit=4):
    # 保留当前出口、另一入口、另一来源和其他国家，不能用四个同入口别名充当备用。
    if len(rows) <= limit:
        return rows
    selected = [rows[0]]
    first = rows[0]
    predicates = [
        lambda row: row.get("ingress_id") != first.get("ingress_id") and
                    (row.get("exit_id") == preferred_exit_id or row.get("exit_country") == preferred_country),
        lambda row: row["source"] != first["source"] and row.get("exit_country") == preferred_country,
        lambda row: row.get("exit_country") != preferred_country,
    ]
    for predicate in predicates:
        candidate = next((row for row in rows if row not in selected and predicate(row)), None)
        if candidate and len(selected) < limit:
            selected.append(candidate)
    for row in rows:
        if len(selected) >= limit:
            break
        if row not in selected:
            selected.append(row)
    return selected
