"""Prompty versions, the file/MLflow tracker, and the offline canary decision."""

import importlib.util
import json
import sys
from pathlib import Path

from agentplatform.llmops.canary import decide_rollback
from agentplatform.llmops.tracking import log_prompt_run
from agentplatform.prompts.prompty import load_prompty_pack

ROOT = Path(__file__).resolve().parents[1]
STABLE = {
    "policy_compliance": 1.0,
    "condition_recall": 1.0,
    "condition_leak": 0.0,
    "recommendation_match": 1.0,
}


def test_prompty_pack_pins_two_critic_versions():
    pack = load_prompty_pack()
    stable = pack.get("mortgage.critic", "1.0.0")
    canary = pack.get("mortgage.critic", "1.1.0")
    assert stable.deployment == "gpt-5-mini"
    assert stable.sha != canary.sha
    assert pack.get("mortgage.critic").version == "1.1.0"
    assert "review the file" in stable.render({"task": "review the file"})
    rendered = canary.render({"application_date": "2026-01-15", "evidence": "guideline pack"})
    assert "guideline pack" in rendered
    assert "allowed" in canary.body
    markdown = (ROOT / "src/agentplatform/prompts/pack/mortgage.critic@1.0.0.md").read_text()
    assert "Fail the draft if any condition lacks a" in markdown
    assert "Fail the draft if any condition lacks a" in stable.body


def test_file_tracker_records_prompt_and_model(tmp_path, monkeypatch):
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    record = log_prompt_run(
        experiment="prompt-versions",
        prompt_ref="mortgage.critic@1.1.0",
        prompt_sha="abc123abc123",
        model="gpt-5-mini",
        metrics={"policy_compliance": 1.0},
        path=tmp_path / "experiments.jsonl",
    )
    assert record["backend"] == "file"
    saved = json.loads((tmp_path / "experiments.jsonl").read_text())
    assert saved["params"]["prompt_ref"] == "mortgage.critic@1.1.0"
    assert saved["params"]["model"] == "gpt-5-mini"
    assert saved["metrics"]["policy_compliance"] == 1.0


def test_tracker_uses_mlflow_when_the_package_is_present(monkeypatch):
    calls = {}

    class Info:
        run_id = "run-1"

    class Run:
        info = Info()

    class Start:
        def __enter__(self):
            return Run()

        def __exit__(self, *args):
            return False

    class FakeMLflow:
        def set_tracking_uri(self, uri):
            calls["uri"] = uri

        def set_experiment(self, name):
            calls["experiment"] = name

        def start_run(self):
            return Start()

        def log_params(self, params):
            calls["params"] = params

        def log_metrics(self, metrics):
            calls["metrics"] = metrics

    monkeypatch.setitem(sys.modules, "mlflow", FakeMLflow())
    record = log_prompt_run(
        experiment="prompt-versions",
        prompt_ref="mortgage.critic@1.0.0",
        prompt_sha="def456def456",
        model="gpt-5-mini",
        metrics={"condition_recall": 0.99},
        tracking_uri="file:/tmp/aap-mlruns",
    )
    assert record["backend"] == "mlflow"
    assert record["run_id"] == "run-1"
    assert calls["uri"] == "file:/tmp/aap-mlruns"
    assert calls["params"]["prompt_sha"] == "def456def456"
    assert calls["metrics"]["condition_recall"] == 0.99


def test_canary_rolls_back_on_regression_and_holds_otherwise():
    regressed = decide_rollback(
        STABLE, {**STABLE, "policy_compliance": 0.8, "condition_recall": 0.9}, weight=10
    )
    assert regressed["rollback"] is True
    assert regressed["new_weight"] == 0
    held = decide_rollback(STABLE, dict(STABLE), weight=10)
    assert held["rollback"] is False
    assert held["new_weight"] == 10
    within = decide_rollback(
        {"quality": 0.90},
        {"quality": 0.86},
        weight=25,
        max_drop=0.05,
        required=("quality",),
        thresholds={"quality": 0.80},
        max_metrics=set(),
    )
    assert within["rollback"] is False
    assert within["new_weight"] == 25
    leaked = decide_rollback(STABLE, {**STABLE, "condition_leak": 0.2}, weight=15)
    assert leaked["rollback"] is True
    missing = decide_rollback({"policy_compliance": 1.0}, {}, weight=5, required=("policy_compliance",))
    assert missing["new_weight"] == 0
    assert "fail closed" in missing["reasons"][0]


def test_canary_script_simulates_rollback_without_calling_azure(tmp_path, monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location("canary_rollback", ROOT / "scripts" / "canary_rollback.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.delenv("AZURE_SUBSCRIPTION_ID", raising=False)
    monkeypatch.delenv("AZURE_RESOURCE_GROUP", raising=False)
    monkeypatch.delenv("APIM_NAME", raising=False)
    assert mod.main(["--example", "regress", "--track-dir", str(tmp_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["applied"] is False
    assert payload["decision"]["new_weight"] == 0
    assert payload["canary_prompt"] == "mortgage.critic@1.1.0"
    assert "namedValues/canary-weight" in payload["command"][payload["command"].index("--url") + 1]
    assert '"value": "0"' in payload["command"][-1]
    assert (tmp_path / "experiments.jsonl").exists()
    assert mod.main(["--example", "hold", "--apply", "--track-dir", str(tmp_path)]) == 2
    assert "refusing" in capsys.readouterr().out


def test_synthetic_load_dry_run_and_injected_client(capsys):
    spec = importlib.util.spec_from_file_location("synthetic_load", ROOT / "scripts" / "synthetic_load.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["--base-url", "http://127.0.0.1:9", "--rounds", "2"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["dry_run"] is True
    assert report["requests"] == 14
    assert all(item["url"].startswith("http://127.0.0.1:9") for item in report["plan"])

    class Response:
        status_code = 202

    class Client:
        def request(self, method, url, json=None, headers=None):
            assert url.startswith("http://bff")
            return Response()

    results = mod.execute(mod.build_plan("http://bff", 1), Client())
    summary = mod.summarize(results)
    assert summary["requests"] == len(mod.SCENARIOS)
    assert summary["statuses"] == {"202": len(mod.SCENARIOS)}
