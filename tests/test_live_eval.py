"""Live eval mode stays offline unless Azure OpenAI env vars are present."""

import importlib.util
import json
import os
from pathlib import Path

import pytest

from agentplatform.evals.live import (
    agreement,
    cohens_kappa,
    cost_report,
    judge_vs_human,
    load_human_labels,
    missing_live_env,
    run_live_evaluation,
)
from agentplatform.evals.pricing import cost_per_1k_tasks

ROOT = Path(__file__).resolve().parents[1]


def test_kappa_matches_the_balanced_example():
    human = [1, 1, 1, 1, 0, 0, 0, 0]
    judge = [1, 1, 1, 0, 0, 0, 0, 1]
    assert cohens_kappa(human, judge) == pytest.approx(0.5)
    assert agreement(
        [
            {"id": "a", "groundedness": 1, "human_grounded": 1},
            {"id": "b", "groundedness": 0, "human_grounded": 1},
        ],
        judge_key="groundedness",
        human_key="human_grounded",
    )["disagreements"] == ["b"]


def test_cost_per_1k_tasks_scales_the_batch():
    # 1,000,000 input tokens at 0.25 USD / 1M is 0.25 USD. Spread over 1,000 tasks that is 0.25 per 1k.
    assert cost_per_1k_tasks(1_000_000, 0, 1000) == pytest.approx(0.25)
    report = cost_report([{"query": "q", "response": "r", "context": "c"}])
    assert report["measured"] is False
    assert report["usd_per_1k_tasks"] > 0


def test_human_labels_disagree_with_the_lexical_judge_on_the_wrong_number():
    report = judge_vs_human()
    assert report["judge"] == "lexical"
    assert report["groundedness"]["n"] == 7
    assert report["groundedness"]["accuracy"] < 1
    assert "hl-007" in report["groundedness"]["disagreements"]
    assert load_human_labels()[0]["human_grounded"] in (0, 1)


def test_live_report_skips_without_env(monkeypatch):
    for name in (
        "AZURE_OPENAI_ENDPOINT",
        "EVAL_MODEL_DEPLOYMENT",
        "AZURE_OPENAI_DEPLOYMENT",
        "FOUNDRY_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    assert missing_live_env()
    report = run_live_evaluation([], [], env=dict(os.environ), labels=load_human_labels())
    assert report["skipped"] is True
    assert report["live"] is None
    assert report["cost"]["live_calls"] == 0
    assert report["langsmith"]["logged"] is False
    assert "usd_per_1k_tasks" in report["cost"]


def test_live_report_uses_injected_sdk_and_langsmith():
    labels = load_human_labels()

    def fake_eval(rows, env):
        assert env["AZURE_OPENAI_ENDPOINT"].startswith("https://")
        assert any(row["id"] == "hl-001" for row in rows)
        return {
            "metrics": {"groundedness.gpt_groundedness": 0.5, "relevance.relevance": 0.25},
            "rows": [
                {"id": "hl-001", "groundedness": 1, "relevance": 1},
                {"id": "hl-003", "groundedness": 0, "relevance": 0},
            ],
            "studio_url": "https://example.invalid/studio",
            "foundry_project": True,
            "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 0},
        }

    class Client:
        def __init__(self):
            self.runs = []

        def create_run(self, **kwargs):
            self.runs.append(kwargs)

    client = Client()
    env = {
        "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
        "EVAL_MODEL_DEPLOYMENT": "gpt-5-mini",
        "FOUNDRY_PROJECT_ENDPOINT": "https://example.services.ai.azure.com/api/projects/demo",
        "LANGSMITH_API_KEY": "local-test",
        "LANGSMITH_PROJECT": "aap",
        "AAP_MODE": "offline",
    }
    report = run_live_evaluation(
        [], [], env=env, evaluate_fn=fake_eval, langsmith_client=client, labels=labels
    )
    assert report["skipped"] is False
    assert report["live"]["metrics"]["groundedness"] == pytest.approx(0.5)
    assert report["live"]["metrics"]["relevance"] == pytest.approx(0.25)
    assert report["judge_vs_human_live"]["groundedness"]["n"] == 2
    assert report["judge_vs_human_live"]["groundedness"]["accuracy"] == 1
    assert report["cost"]["measured"] is True
    assert report["cost"]["usd_per_1k_tasks"] == pytest.approx(cost_per_1k_tasks(1_000_000, 0, len(labels)))
    assert report["langsmith"] == {"logged": True, "project": "aap"}
    assert client.runs[0]["project_name"] == "aap"
    assert "Do not subtract" in report["comparison"]["note"]


def test_langsmith_skips_without_a_key():
    env = {
        "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
        "EVAL_MODEL_DEPLOYMENT": "gpt-5-mini",
    }

    def fake_eval(rows, env):
        return {"metrics": {"groundedness": 1.0}, "rows": []}

    report = run_live_evaluation([], [], env=env, evaluate_fn=fake_eval, labels=[])
    assert report["langsmith"]["logged"] is False
    assert "LANGSMITH_API_KEY" in report["langsmith"]["reason"]


def test_live_cli_skips_cleanly(monkeypatch, tmp_path, capsys):
    spec = importlib.util.spec_from_file_location("run_evals", ROOT / "scripts" / "run_evals.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    async def empty():
        return []

    monkeypatch.setattr(mod, "mortgage_rows", empty)
    monkeypatch.setattr(mod, "hr_rows", empty)
    for name in (
        "AZURE_OPENAI_ENDPOINT",
        "EVAL_MODEL_DEPLOYMENT",
        "AZURE_OPENAI_DEPLOYMENT",
        "FOUNDRY_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    assert mod.main(["--live", "--out", str(tmp_path)]) == 0
    report = json.loads((tmp_path / "live-report.json").read_text())
    assert report["skipped"] is True
    assert report["live"] is None
    assert "skipped" in capsys.readouterr().out
