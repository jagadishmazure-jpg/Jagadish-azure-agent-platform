import os
import tempfile

import pytest

os.environ["AAP_MODE"] = "offline"
# keep file checkpoints from BFF/A2A tests out of the working tree
os.environ.setdefault("AAP_CHECKPOINT_DIR", os.path.join(tempfile.gettempdir(), "aap-test-checkpoints"))


@pytest.fixture(autouse=True)
def _reset_kill_switch():
    from agentplatform.harness.killswitch import KILL_SWITCH

    KILL_SWITCH.reset(everything=True)
    yield
    KILL_SWITCH.reset(everything=True)
