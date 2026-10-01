import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build import SERVICES, generate, read_yaml
from measure import validate_bandwidth, validate_latency


def route(config, host):
    # 仅模拟本文模板使用的域名首匹配；真实语法由 Mihomo -t 另验。
    for rule in config["rules"]:
        fields = rule.split(",")
        if fields[0] == "DOMAIN" and fields[1] == host:
            return fields[2]
        if fields[0] == "DOMAIN-SUFFIX" and (host == fields[1] or host.endswith("." + fields[1])):
            return fields[2]
        if fields[0] == "MATCH":
            return fields[1]


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.settings = read_yaml(ROOT / "examples/settings.example.yaml")
        self.sources = {key: read_yaml(ROOT / "examples" / value) for key, value in self.settings["sources"].items()}
        self.config, self.payloads = generate(self.settings, self.sources, demo=True)

    def test_service_and_download_boundaries(self):
        cases = {
            "chatgpt.com": "AI ChatGPT Codex", "api.openai.com": "AI OpenAI API",
            "api.anthropic.com": "AI Claude", "gemini.google.com": "AI Gemini",
            "aistudio.google.com": "AI Studio", "antigravity.google": "AI Antigravity",
            "cloudcode-pa.googleapis.com": "AI Antigravity",
            "daily-cloudcode-pa.sandbox.googleapis.com": "AI Antigravity",
            "api.githubcopilot.com": "AI GitHub Copilot", "copilot-proxy.githubusercontent.com": "AI GitHub Copilot",
            "downloads.cursor.com": "容器与依赖", "api.cursor.com": "AI Cursor",
            "api.github.com": "GitHub API", "github.com": "开发", "raw.githubusercontent.com": "GitHub 文件",
            "ghcr.io": "容器与依赖", "registry-1.docker.io": "容器与依赖",
            "video.twimg.com": "媒体与下载", "pbs.twimg.com": "社交", "api.x.ai": "AI Grok",
            "modelscope.cn": "DIRECT", "deepseek.com": "DIRECT", "www.bilibili.com": "DIRECT",
        }
        for host, target in cases.items():
            with self.subTest(host=host):
                self.assertEqual(route(self.config, host), target)

    def test_shared_roots_do_not_enter_ai(self):
        for host in ["auth0.com", "sentry.io", "stripe.com", "gstatic.com", "storage.googleapis.com", "unrelated.sandbox.googleapis.com", "amazonaws.com", "azure.com"]:
            self.assertFalse(route(self.config, host).startswith("AI"))

    def test_refreshed_registry_and_ai_boundaries(self):
        cases = {
            "us-docker.pkg.dev": "容器与依赖", "asia.gcr.io": "容器与依赖",
            "registry.gitlab.com": "容器与依赖", "gitlab.com": "开发",
            "cdn.quay.io": "容器与依赖", "mcr.microsoft.com": "容器与依赖",
            "jitpack.io": "容器与依赖", "dhi.io": "容器与依赖",
            "download-cdn.jetbrains.com": "容器与依赖", "download.todesktop.com": "容器与依赖",
            "docker-images-prod.6aa30f8b08e16409b46e0173d6de2f56.r2.cloudflarestorage.com": "容器与依赖",
            "unrelated.r2.cloudflarestorage.com": "通用海外",
            "cdn-lfs.huggingface.co": "容器与依赖", "cas-bridge.xethub.hf.co": "容器与依赖",
            "chatgpt.livekit.cloud": "AI ChatGPT Codex", "unrelated.livekit.cloud": "通用海外",
            "daily-cloudcode-pa.googleapis.com": "AI Antigravity",
            "unrelated.googleapis.com": "通用海外", "registry.example.cn": "通用海外",
            "github.blog": "开发", "pages.gitlab.io": "开发",
        }
        for host, target in cases.items():
            with self.subTest(host=host):
                self.assertEqual(route(self.config, host), target)

    def test_all_ai_health_providers_are_independent(self):
        keys = []
        for service in SERVICES:
            group = next(group for group in self.config["proxy-groups"] if group["name"] == service["name"])
            if service["auto"]:
                self.assertEqual(group["type"], "fallback")
                self.assertEqual(group["use"], [f"{service['id']}-primary", f"{service['id']}-bulk"])
                keys.extend(group["use"])
            else:
                self.assertEqual(group["type"], "select")
                self.assertNotIn("url", group)
        self.assertEqual(len(keys), 46)
        self.assertEqual(len(set(keys)), 46)

    def test_bulk_never_automatically_uses_primary(self):
        for group in self.config["proxy-groups"]:
            if group["name"] in {"GitHub 文件", "容器与依赖", "媒体与下载"}:
                self.assertTrue(all(key.endswith("-bulk") for key in group["use"]))

    def test_high_multiplier_stays_manual(self):
        self.assertTrue(any(proxy["name"] == "P-05" for proxy in self.config["proxies"]))
        for payload in self.payloads.values():
            self.assertNotIn("P-05", [proxy["name"] for proxy in payload["proxies"]])

    def test_block_removes_primary_from_all_active_paths(self):
        config, payloads = generate(self.settings, self.sources, demo=True, block_primary=True)
        self.assertTrue(all(not key.endswith("-primary") for key in config["proxy-providers"]))
        self.assertTrue(all(not proxy["name"].startswith("P-") for proxy in config["proxies"]))
        directory = next(group for group in config["proxy-groups"] if group["name"] == "全部节点 primary")
        self.assertEqual(directory["proxies"], ["REJECT"])
        self.assertEqual(len([key for key in payloads if key.startswith("providers/chatgpt")]), 1)

    def test_empty_qualified_pool_rejects(self):
        settings = copy.deepcopy(self.settings)
        for node in settings["nodes"]:
            node["qualified"] = False
        config, payloads = generate(settings, self.sources, demo=True)
        self.assertEqual(payloads, {})
        group = next(group for group in config["proxy-groups"] if group["name"] == "AI ChatGPT Codex")
        self.assertEqual(group["proxies"], ["REJECT"])

    def test_unreviewed_service_is_excluded(self):
        settings = copy.deepcopy(self.settings)
        settings["nodes"][0]["services"] = ["claude"]
        _, payloads = generate(settings, self.sources, demo=True)
        self.assertEqual([proxy["name"] for proxy in payloads["providers/chatgpt-primary.yaml"]["proxies"]], ["P-02"])

    def test_demo_refused_in_production(self):
        with self.assertRaises(ValueError):
            generate(self.settings, self.sources)
        settings = copy.deepcopy(self.settings)
        settings["demo"] = False
        with self.assertRaises(ValueError):
            generate(settings, self.sources)

    def test_network_fields_preserved(self):
        base = {"dns": {"enable": True, "nameserver": ["https://dns.google/dns-query"]}, "tun": {"enable": False}}
        config, _ = generate(self.settings, self.sources, base, demo=True)
        self.assertEqual(config["dns"], base["dns"])
        self.assertEqual(config["tun"], base["tun"])
        self.assertFalse(config["allow-lan"])

    def test_subscription_hosts_preserved_and_conflicts_rejected(self):
        sources = copy.deepcopy(self.sources)
        sources["primary"]["hosts"] = {"alias.invalid": "canonical.invalid"}
        config, _ = generate(self.settings, sources, demo=True)
        self.assertEqual(config["hosts"]["alias.invalid"], "canonical.invalid")
        config, _ = generate(self.settings, sources, {"hosts": {"alias.invalid": "override.invalid"}}, demo=True)
        self.assertEqual(config["hosts"]["alias.invalid"], "override.invalid")
        sources["bulk"]["hosts"] = {"alias.invalid": "conflict.invalid"}
        with self.assertRaises(ValueError):
            generate(self.settings, sources, demo=True)

    def test_bad_metadata_rejected(self):
        for field, value in [("multiplier", 0), ("multiplier", float("nan")), ("multiplier", float("inf")),
                             ("alias", "DIRECT"), ("qualified_on", "bad-date"), ("services", ["unknown"])]:
            settings = copy.deepcopy(self.settings)
            settings["nodes"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                generate(settings, self.sources, demo=True)


class MeasurementTests(unittest.TestCase):
    def test_reconnect_or_http_error_invalidates_latency(self):
        rows = [{"http_code": 200, "num_connects": 1 if index == 0 else 0} for index in range(11)]
        self.assertTrue(validate_latency(rows, 0))
        rows[5]["num_connects"] = 1
        self.assertFalse(validate_latency(rows, 0))
        rows[5]["num_connects"] = 0
        rows[4]["http_code"] = 403
        self.assertFalse(validate_latency(rows, 0))

    def test_incomplete_download_is_invalid(self):
        rows = [{"http_code": 200, "num_connects": 1, "size_download": 10_000_000, "time_total": 2}]
        self.assertTrue(validate_bandwidth(rows, 0, 10_000_000))
        rows[0]["size_download"] = 100
        self.assertFalse(validate_bandwidth(rows, 0, 10_000_000))


if __name__ == "__main__":
    unittest.main()
