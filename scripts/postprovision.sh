#!/bin/sh
# azd postprovision hook: seed AI Search indexes, register Foundry agents, run the eval gate.
# azd exports every Bicep output as an env var (FOUNDRY_PROJECT_ENDPOINT, AZURE_SEARCH_ENDPOINT, ...).
set -eu
export AAP_MODE=azure
python -m pip install -q -e ".[eval]"
python scripts/seed_search_index.py
python scripts/foundry_register.py --apply
python scripts/export_agent_cards.py --check
echo "postprovision complete: indexes seeded, Foundry agents registered."
