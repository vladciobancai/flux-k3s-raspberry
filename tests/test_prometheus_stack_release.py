"""Regression coverage for the kube-prometheus-stack 93.4.1 upgrade.

Requires PyYAML (also used by the repository's YAML lint tooling).
Run from the repository root with:
    python3 -m unittest discover -s tests -p 'test_prometheus_stack_release.py'

These tests validate the Flux configuration without a cluster or network access.
They do not render or exercise the upstream chart.
"""

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
MONITORING = ROOT / "infrastructure" / "monitoring"


def load_manifest(path):
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


class PrometheusStackReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.release = load_manifest(MONITORING / "prom-stack.HelmRelease.yaml")
        cls.chart = cls.release["spec"]["chart"]["spec"]

    def test_chart_is_pinned_to_the_reviewed_patch(self):
        # Exact equality rejects rollback, ranges, wildcards, and prereleases.
        self.assertEqual(self.chart["version"], "93.4.1")

    def test_upgrade_targets_the_existing_monitoring_release(self):
        self.assertEqual(self.release["apiVersion"], "helm.toolkit.fluxcd.io/v2")
        self.assertEqual(self.release["kind"], "HelmRelease")
        self.assertEqual(self.release["metadata"]["name"], "kube-prometheus-stack")
        self.assertEqual(self.release["metadata"]["namespace"], "monitoring")
        self.assertEqual(self.chart["chart"], "kube-prometheus-stack")

    def test_chart_source_resolves_to_the_prometheus_community_repository(self):
        source = self.chart["sourceRef"]
        self.assertEqual(source["kind"], "HelmRepository")
        namespace = source.get("namespace", self.release["metadata"]["namespace"])
        # Resolve by Kubernetes identity, including Flux's namespace default.
        # A matching name in another namespace must not satisfy the reference.
        matches = []
        for path in MONITORING.glob("*.yaml"):
            manifest = load_manifest(path)
            if (
                manifest["kind"] == source["kind"]
                and manifest["metadata"]["name"] == source["name"]
                and manifest["metadata"].get("namespace") == namespace
            ):
                matches.append(manifest)
        self.assertEqual(len(matches), 1, "Chart source must resolve unambiguously")
        self.assertEqual(
            matches[0]["spec"]["url"],
            "https://prometheus-community.github.io/helm-charts",
        )

    def test_upgrade_can_replace_prometheus_operator_crds(self):
        self.assertEqual(self.release["spec"]["upgrade"]["crds"], "CreateReplace")

    def test_upgrade_preserves_discovery_of_external_monitors(self):
        prometheus = self.release["spec"]["values"]["prometheus"]["prometheusSpec"]
        for selector in (
            "podMonitorSelectorNilUsesHelmValues",
            "serviceMonitorSelectorNilUsesHelmValues",
        ):
            with self.subTest(selector=selector):
                # Boolean identity also rejects YAML strings such as "false".
                self.assertIs(prometheus[selector], False)

    def test_upgrade_preserves_persistent_monitoring_data(self):
        values = self.release["spec"]["values"]
        prometheus = values["prometheus"]["prometheusSpec"]
        self.assertEqual(prometheus["retention"], "7d")
        self.assertEqual(
            prometheus["storageSpec"]["volumeClaimTemplate"]["spec"]["resources"]
            ["requests"]["storage"],
            "10Gi",
        )
        self.assertIs(values["grafana"]["persistence"]["enabled"], True)
        self.assertEqual(values["grafana"]["persistence"]["size"], "5Gi")


if __name__ == "__main__":
    unittest.main()
