import json
import sys
import unittest
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build import CAPACITY, INTERACTIVE, SERVICES, generate, read_yaml
from render_rule_diagrams import artifacts


class RuleDiagramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = artifacts()
        cls.manifest = json.loads(cls.files["manifest.json"])
        settings = read_yaml(ROOT / "examples/settings.example.yaml")
        sources = {key: read_yaml(ROOT / "examples" / value) for key, value in settings["sources"].items()}
        cls.config, _ = generate(settings, sources, demo=True)

    def test_every_generated_rule_is_visible_once_across_chapters(self):
        visible = []
        for chapter in self.manifest["chapters"]:
            svg = ET.fromstring(self.files[chapter["file"]])
            visible.extend(node.get("data-rule") for node in svg.iter() if node.get("data-rule"))
        self.assertEqual(Counter(visible), Counter(self.config["rules"]))
        self.assertEqual(len(visible), len(self.config["rules"]))

    def test_complete_chart_contains_rules_and_all_business_groups(self):
        svg = ET.fromstring(self.files["17-all-rules.svg"])
        visible = [node.get("data-rule") for node in svg.iter() if node.get("data-rule")]
        self.assertEqual(Counter(visible), Counter(self.config["rules"]))
        labels = {node.text for node in svg.iter("{http://www.w3.org/2000/svg}text")}
        expected = {service["name"] for service in SERVICES} | set(INTERACTIVE) | set(CAPACITY) | {"DIRECT"}
        self.assertTrue(expected <= labels)

    def test_svg_is_static_accessible_bracket_structure(self):
        allowed = {"svg", "g", "path", "rect", "text", "title", "desc"}
        for name, content in self.files.items():
            if not name.endswith(".svg"):
                continue
            with self.subTest(file=name):
                svg = ET.fromstring(content)
                self.assertEqual(svg.get("role"), "img")
                self.assertTrue(svg.get("aria-labelledby"))
                self.assertTrue(any(node.get("data-brace") == "true" for node in svg.iter()))
                for node in svg.iter():
                    self.assertIn(node.tag.rsplit("}", 1)[-1], allowed)
                    self.assertFalse(any(key.startswith("on") or key in {"href", "marker-end"} for key in node.attrib))


if __name__ == "__main__":
    unittest.main()
