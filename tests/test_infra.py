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
