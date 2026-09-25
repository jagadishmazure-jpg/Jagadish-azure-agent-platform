import importlib.util
import logging
from datetime import date
from pathlib import Path

from agentplatform.evals.evaluators import ConditionRecallEvaluator, PolicyComplianceEvaluator, call
from agentplatform.evals.runner import hr_rows, mortgage_rows, score_offline
from agentplatform.knowledge.index_schema import build_index, to_document
from agentplatform.knowledge.search import load_corpus

logging.getLogger("agent_framework").setLevel(logging.ERROR)
ROOT = Path(__file__).resolve().parents[1]


async def test_golden_sets_pass_release_gate():
    report = score_offline(await mortgage_rows(), await hr_rows())
    assert report.passed, report.failures
    assert report.metrics["policy_compliance"] == 1.0


def test_policy_evaluator_catches_violations():
    ev = PolicyComplianceEvaluator()
    bad = ev(
        response="Your loan is denied. SSN 123-45-6789",
        conditions=[{"id": "C1", "guideline_ids": []}, {"id": "C2", "guideline_ids": ["GL-DTI-200.v2"]}],
        as_of="2025-01-15",
    )
    reasons = " ".join(bad["policy_compliance_reasons"])
    assert bad["policy_compliance"] == 0.0
    assert "uncited" in reasons and "not in force" in reasons and "adverse" in reasons and "SSN" in reasons
    ok = ev(response="Your income decline needs a letter of explanation.", conditions=[], as_of="2025-01-15")
    assert ok["policy_compliance"] == 1.0


def test_gate_fails_on_regression():
    rows = [
        {
            "id": "x",
            "response": "",
            "conditions": [],
            "as_of": str(date.today()),
            "recommendation": "referred",
            "expected_recommendation": "approved_with_conditions",
            "must_include": ["C-A"],
            "must_exclude": [],
        }
    ]
    rep = score_offline(rows, [])
    assert not rep.passed and any("condition_recall" in f for f in rep.failures)
    assert call(ConditionRecallEvaluator(), rows[0])["recommendation_match"] == 0.0


def test_custom_evaluator_runs_under_azure_ai_evaluation(tmp_path):
    """evaluate() with only local (non-AI-assisted) evaluators runs offline — proves signature compatibility."""
    import json

    from azure.ai.evaluation import evaluate

    data = tmp_path / "rows.jsonl"
    data.write_text(json.dumps({"response": "ok", "conditions": [], "as_of": "2025-01-01"}) + "\n")
    r = evaluate(
        data=str(data),
        evaluators={"policy": PolicyComplianceEvaluator()},
        evaluator_config={
            "policy": {
                "column_mapping": {
                    "response": "${data.response}",
                    "conditions": "${data.conditions}",
                    "as_of": "${data.as_of}",
                }
            }
        },
    )
    assert r["metrics"]["policy.policy_compliance"] == 1.0


def test_search_index_definition_matches_query_contract():
    idx = build_index("investor-guidelines", "https://x.openai.azure.com")
    names = {f.name for f in idx.fields}
    assert {"effective_from", "effective_to", "allowed_groups", "content_vector", "params_json"} <= names
    assert idx.semantic_search.configurations[0].name == "default"
    doc = to_document(load_corpus()[0])
    assert "." not in doc["id"] and doc["effective_from"].endswith("Z")


def test_seed_script_dry_run(capsys):
    spec = importlib.util.spec_from_file_location("seed", ROOT / "scripts" / "seed_search_index.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["--dry-run"]) == 0
    assert "semantic" in capsys.readouterr().out.lower()
