import os

import pytest

os.environ["AAP_MODE"] = "offline"


@pytest.fixture(autouse=True)
def _reset_kill_switch():
    from agentplatform.harness.killswitch import KILL_SWITCH

    KILL_SWITCH.reset(everything=True)
    yield
    KILL_SWITCH.reset(everything=True)
