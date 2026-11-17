# `prompty/`: versioned Prompty files

[Prompty](https://prompty.ai) files for the prompt pack. Each file is `<id>@<version>.prompty`
with model, parameters and inputs in the front matter and the instruction text after it.
`mortgage.critic` has `1.0.0` (stable) and `1.1.0` (canary). The markdown files in `pack/`
remain what the agents load at runtime; these files are the LLMOps artifact API Management
routes between.

| File | What it does |
|---|---|
| `hr.policy@1.0.0.prompty` | HR policy assistant. |
| `it.servicedesk@1.0.0.prompty` | IT service desk triage. |
| `mortgage.intake@1.0.0.prompty` | Intake narrative. |
| `mortgage.income@1.0.0.prompty` | Income narrative. |
| `mortgage.assets@1.0.0.prompty` | Asset narrative. |
| `mortgage.credit@1.0.0.prompty` | Credit narrative. |
| `mortgage.conditions@1.0.0.prompty` | Condition writer. |
| `mortgage.critic@1.0.0.prompty` | Stable critic. |
| `mortgage.critic@1.1.0.prompty` | Canary critic: also fails ACL misses and adverse-action language. |
| `mortgage.decision_letter@1.0.0.prompty` | Decision letter after human approval. |

`load_prompty_pack()` in [`../prompty.py`](../prompty.py) parses them. The loader globs only
this directory, so this README is not treated as a prompt.
