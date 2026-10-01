from urllib.error import HTTPError
from urllib.parse import quote

from monitor import now
from policy import utc


class Availability:
    def provider_matches(self, provider, alias):
        expected = getattr(self, "expected_endpoints", {}).get(alias)
        if not expected:
            return True
        path = getattr(self, "provider_paths", {}).get(provider)
        if path and path.replace("\\", "/").startswith("policy-providers/"):
            return path.replace("\\", "/").rsplit("/", 1)[-1].startswith(expected + "-")
        if path:
            return True
        return getattr(self, "root_endpoints", {}).get(alias) == expected

    def sample(self, providers, alias, url):
        records = [record for name, provider in providers.items() if self.provider_matches(name, alias) for node in provider.get("proxies", [])
                   if node["name"] == alias for record in (node.get("extra", {}).get(url, {}).get("history") or [])]
        return max(records, key=lambda row: utc(row["time"])) if records else None

    def probe(self, providers, alias, spec):
        provider = next((name for name, row in providers.items() if self.provider_matches(name, alias) and any(node["name"] == alias for node in row.get("proxies", []))), None)
        if not provider:
            return False
        path = "/providers/proxies/" + quote(provider, safe="") + "/" + quote(alias, safe="")
        path += "/healthcheck?url=" + quote(spec["url"], safe="") + "&timeout=5000&expected=" + str(spec["status"])
        try:
            return self.api.request("GET", path).get("delay", 0) > 0
        except (HTTPError, RuntimeError):
            return False

    def pin(self, state, definitions, providers):
        proxies = self.api.request("GET", "/proxies")["proxies"]
        active_checks = getattr(self, "active_checks", 0)
        statuses = {}
        for name, spec in definitions.items():
            if not spec["ai"]:
                continue
            automatic = name + " 候选"
            if automatic not in proxies:
                continue
            outer = self.api.request("GET", "/proxies/" + quote(name, safe=""))
            group = self.api.request("GET", "/proxies/" + quote(automatic, safe=""))
            choice = group.get("now")
            rows = {row["alias"]: row for row in state["selection"].get(name, [])}
            candidates = [alias for alias in group.get("all", []) if alias in rows]
            rejects = state.setdefault("automatic_reject", [])
            manual = outer.get("now") not in {automatic, "REJECT"} or (outer.get("now") == "REJECT" and name not in rejects)
            statuses[name] = {"manual": manual, "current": choice, "candidates": len(candidates),
                              "backup_count": max(0, len(candidates) - 1), "business": "pending"}
            if not candidates:
                statuses[name]["available"] = False
            if manual:
                statuses[name].update(current=outer.get("now"), available=None)
                continue
            good, failed = [], []
            for alias in candidates:
                record = self.sample(providers, alias, spec["url"])
                if record and 0 <= (utc(now()) - utc(record["time"])).total_seconds() <= 180:
                    (good if record["delay"] > 0 else failed).append(alias)
            target = choice if choice in good else None
            if not target and choice in candidates and active_checks < 2:
                active_checks += 1
                if self.probe(providers, choice, spec):
                    target = choice
                elif choice not in failed:
                    failed.append(choice)
            if not target:
                target = next(iter(good), None)
            if not target:
                for alias in candidates:
                    if alias in failed or active_checks >= 2:
                        continue
                    active_checks += 1
                    if self.probe(providers, alias, spec):
                        target = alias
                        break
                    failed.append(alias)
            if target:
                if group.get("fixed") != target:
                    self.api.request("PUT", "/proxies/" + quote(automatic, safe=""), {"name": target})
                if name in rejects:
                    self.api.request("PUT", "/proxies/" + quote(name, safe=""), {"name": automatic})
                    rejects.remove(name)
                statuses[name].update(current=target, available=True, source=rows[target].get("source"),
                                      exit_country=rows[target].get("exit_country"), checked_at=rows[target].get("checked_at"))
            elif not candidates or len(set(failed)) == len(candidates):
                if outer.get("now") != "REJECT":
                    self.api.request("PUT", "/proxies/" + quote(name, safe=""), {"name": "REJECT"})
                if name not in rejects:
                    rejects.append(name)
                statuses[name]["available"] = False
            else:
                statuses[name]["available"] = None
        state["service_status"] = statuses
        self.active_checks = active_checks
