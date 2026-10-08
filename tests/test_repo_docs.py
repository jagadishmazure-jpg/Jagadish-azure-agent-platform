"""Documentation structure checks: component docs, guides, folder READMEs, ownership, counts."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECTIONS = [
    "Purpose",
    "Architecture",
    "How it works",
    "Key files",
    "Code excerpts",
    "Configuration",
    "Commands",
    "Real output",
    "Tests and eval gates",
    "Guardrails",
    "Security and governance",
    "Observability",
    "Failure modes",
    "Mapping to Azure services",
    "Limitations",
    "Interview talking points",
    "Adopt this",
]
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".checkpoints", ".terraform"}
# prompts/pack: every .md there is parsed as a prompt, so it cannot hold a README.
# .github: GitHub would show .github/README.md instead of the root README on the repo page.
NO_README = {Path("src/agentplatform/prompts/pack"), Path(".github")}


def _component_docs():
    return sorted(p for p in (ROOT / "docs/components").glob("*.md") if p.name != "README.md")


def test_every_component_doc_has_the_17_sections_in_order():
    docs = _component_docs()
    assert len(docs) >= 14
    for p in docs:
        heads = re.findall(r"^## \d+\. (.+)$", p.read_text(), re.M)
        assert heads == SECTIONS, p.name
        assert "```mermaid" in p.read_text(), p.name


def test_component_docs_are_indexed():
    index = (ROOT / "docs/components/README.md").read_text()
    for p in _component_docs():
        assert f"({p.name})" in index, p.name


def test_guides_exist_and_link_components():
    for name in ("implementation-guide.md", "adopt-this.md"):
        text = (ROOT / "docs" / name).read_text()
        assert "components/" in text, name


def test_every_folder_has_a_readme():
    missing = []
    for d in ROOT.rglob("*"):
        if not d.is_dir() or SKIP_DIRS & set(d.relative_to(ROOT).parts):
            continue
        rel = d.relative_to(ROOT)
        if rel.parts and (rel.parts[0].endswith(".egg-info") or rel in NO_README):
            continue
        if not (d / "README.md").exists():
            missing.append(str(rel))
    assert not missing, missing
    assert not (ROOT / ".github/README.md").exists()


def test_codeowners():
    assert "* @jagadishmazure-jpg" in (ROOT / ".github/CODEOWNERS").read_text()


def test_no_placeholders_or_dates_in_docs():
    bad = []
    for p in ROOT.rglob("*.md"):
        if SKIP_DIRS & set(p.relative_to(ROOT).parts):
            continue
        text = p.read_text()
        if re.search(r"\b(TODO|TBD|FIXME)\b", text):
            bad.append(f"{p}: placeholder")
        if re.search(r"\b20\d\d-\d\d-\d\d\b", re.sub(r"`[^`]*`|```.*?```", "", text, flags=re.S)):
            bad.append(f"{p}: date")
    # API versions, model versions and fixture dates are written in code spans: identifiers, not doc dates.
    assert not bad, bad


def test_readme_test_count_matches_collection():
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--co", "-q", "-p", "no:cacheprovider", str(ROOT / "tests")],
        capture_output=True,
        text=True,
        cwd=ROOT,
    ).stdout
    n = int(re.search(r"(\d+) tests? collected", out).group(1))
    readme = (ROOT / "README.md").read_text()
    counts = {int(x) for x in re.findall(r"(\d+) (?:automated |offline )?tests", readme)}
    assert counts == {n}, (counts, n)


def test_workflows_are_hardened():
    """Supply-chain guard: every third-party action is pinned to a full commit SHA with a version
    comment, every workflow sets top-level permissions, CI runs gitleaks, and CodeQL and Dependabot
    are configured. Dependabot bumps keep the SHA and the comment together, so this stays green."""
    wf_dir = ROOT / ".github" / "workflows"
    for f in sorted(wf_dir.glob("*.yml")):
        text = f.read_text()
        assert re.search(r"^permissions:", text, re.M), f"{f.name}: no top-level permissions"
        for line in text.splitlines():
            m = re.search(r"\buses:\s*([^\s#]+)\s*(#.*)?$", line)
            if m and not m.group(1).startswith("./"):
                assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", m.group(1)), f"{f.name}: {line.strip()}"
                assert m.group(2) and re.match(r"#\s*v\d", m.group(2)), f"{f.name}: no version comment"
    assert "gitleaks/gitleaks-action@" in (wf_dir / "ci.yml").read_text()
    assert "github/codeql-action/analyze@" in (wf_dir / "codeql.yml").read_text()
    deps = (ROOT / ".github" / "dependabot.yml").read_text()
    assert "package-ecosystem: github-actions" in deps and "interval: weekly" in deps
