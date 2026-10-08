"""Static checks on the deploy surface (no Azure calls)."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
BICEP = shutil.which("bicep") or str(Path.home() / ".azure/bin/bicep")


def test_azure_yaml_services_match_container_app_tags():
    services = set(yaml.safe_load((ROOT / "azure.yaml").read_text())["services"])
    main = (ROOT / "infra/main.bicep").read_text()
    tagged = set(re.findall(r"service: '([a-z0-9-]+)'", main))
    assert services <= tagged, services - tagged
    for s in services:
        df = yaml.safe_load((ROOT / "azure.yaml").read_text())["services"][s]["docker"]["path"]
        assert (ROOT / df).exists()


def test_cost_min_is_default_and_private_link_off():
    main = (ROOT / "infra/main.bicep").read_text()
    assert "param costProfile string = 'cost-min'" in main
    assert "param privateLink bool = false" in main
    assert "'cost-min': { apim: 'Consumption', search: 'basic', serviceBus: 'Basic', minReplicas: 0" in main


def test_no_local_auth_on_data_services():
    mods = {p.name: p.read_text() for p in (ROOT / "infra/modules").glob("*.bicep")}
    for name in ("foundry.bicep", "search.bicep", "cognitive.bicep", "cosmos.bicep", "servicebus.bicep"):
        assert "disableLocalAuth: true" in mods[name], name


@pytest.mark.skipif(not os.path.exists(BICEP), reason="bicep CLI not installed")
def test_bicep_builds_cleanly():
    out = subprocess.run(
        [BICEP, "build", str(ROOT / "infra/main.bicep"), "--stdout"], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr
    assert "Warning" not in out.stderr and "Error" not in out.stderr, out.stderr
    arm = json.loads(out.stdout)
    assert arm["$schema"].endswith("subscriptionDeploymentTemplate.json#")


def test_bicep_matches_terraform_for_nsgs():
    net_b = (ROOT / "infra/modules/network.bicep").read_text()
    net_t = (ROOT / "infra/terraform/modules/network/main.tf").read_text()
    assert net_t.count("azurerm_subnet_network_security_group_association") == 2
    assert "Microsoft.Network/networkSecurityGroups" in net_b
    assert net_b.count("networkSecurityGroup: { id: nsg.id }") == 2


def test_alerts_diagnostics_and_defender_match_in_both_tools():
    main_b = (ROOT / "infra/main.bicep").read_text()
    main_t = (ROOT / "infra/terraform/main.tf").read_text()
    alerts_t = main_t.split('module "alerts"')[1].split('module "defender"')[0]
    names_b = set(re.findall(r"\{ name: '([a-z0-9-]+)', (?:scope|query):", main_b))
    names_t = set(re.findall(r"^\s+([a-z0-9-]+)\s+= \{ (?:scope|query) =", alerts_t, re.M))
    assert names_b == names_t and len(names_b) == 7, (names_b, names_t)
    diag_b = (ROOT / "infra/modules/diagnostics.bicep").read_text()
    diag_t = set(re.findall(r"^\s+([a-z-]+)\s+= module\.", alerts_t.split("diagnostic_targets")[1], re.M))
    assert diag_t == set(re.findall(r"'([a-z-]+)'", diag_b.split("output targets array =")[1]))
    assert diag_b.count("categoryGroup: 'allLogs'") == 1 and diag_b.count("scope:") == len(diag_t) == 8
    # alerts on by default; Defender for Cloud is subscription-wide and billed, so opt-in in both tools
    assert "param enableAlerts bool = true" in main_b and "param enableDefender bool = false" in main_b
    variables = (ROOT / "infra/terraform/variables.tf").read_text()
    assert re.search(r'variable "enable_defender" \{[^}]*default\s+= false', variables)
    assert re.search(r'variable "enable_alerts" \{[^}]*default\s+= true', variables)
    assert "pricingTier: 'Standard'" in (ROOT / "infra/modules/defender.bicep").read_text()
