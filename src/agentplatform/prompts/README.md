# `prompts/`: versioned prompt pack

The prompt layer. Each prompt is a markdown file with front matter (`id`, `version`, `owner`,
`risk_tier`, `output_schema`) stored in [`pack/`](pack/), reviewed like code and pinned by
reference (`id@version`) in agent cards, so an eval score always maps to the prompt that
produced it. `output_schema` must name a Pydantic model in `schemas.py`; loading fails
otherwise.

| File | What it does |
|---|---|
| [`__init__.py`](__init__.py) | Package docstring. |
| [`registry.py`](registry.py) | `load_pack()` parses every `pack/*.md` file into a `PromptSpec` (`ref`, `sha`, `schema`); `PromptPack.get(id, version=None)` returns a pinned or latest version, `refs()` lists them. |
| [`schemas.py`](schemas.py) | Output contracts for anything that feeds a write, a letter or a critic: `Narrative`, `ConditionOut`, `ConditionSet`, `CriticReport`, `DecisionLetter`, `PolicyAnswer`, `TicketTriage`. |
| [`pack/`](pack/) | The prompt files themselves (documented below, no README inside). |

## `pack/` contents

`registry.load_pack()` globs `pack/*.md` and parses **every** markdown file as a prompt, so a
README in that folder would break loading. The pack is documented here instead.

| Prompt file | Output schema | Risk tier | Used by |
|---|---|---|---|
| `hr.policy@1.0.0.md` | `PolicyAnswer` | medium | HR policy single agent |
| `it.servicedesk@1.0.0.md` | `TicketTriage` | medium | IT service desk single agent |
| `mortgage.intake@1.0.0.md` | `Narrative` | medium | intake agent |
| `mortgage.income@1.0.0.md` | `Narrative` | high | income agent |
| `mortgage.assets@1.0.0.md` | `Narrative` | high | asset agent |
| `mortgage.credit@1.0.0.md` | `Narrative` | high | credit agent |
| `mortgage.conditions@1.0.0.md` | `ConditionSet` | high | conditions writer |
| `mortgage.critic@1.0.0.md` | `CriticReport` | high | critic |
| `mortgage.decision_letter@1.0.0.md` | `DecisionLetter` | high | decision letter after approval |

To add a prompt, create `pack/<id>@<semver>.md` with the front matter above and run
`pytest tests/test_harness.py -k prompt_pack`.
