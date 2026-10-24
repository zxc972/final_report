"""A pending or refused conditional release never starts another subject."""
import importlib.util
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[4]/"tools/macaque_batch_followup.py"
spec=importlib.util.spec_from_file_location("macaque_batch_gate",path)
batch=importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)

@pytest.mark.parametrize("state,verified,choice,allow,expected",[
    ("pass",True,"awaiting_user_choice",[],True),
    ("conditional_pass",True,"awaiting_user_choice",["ION_32198"],False),
    ("conditional_pass",True,"strict_bbox",["ION_32198"],False),
    ("conditional_pass",True,"allow_global_warnings",["ION_32198"],True),
    ("conditional_pass",True,"allow_global_warnings",[],False),
    ("conditional_pass",False,"allow_global_warnings",["ION_32198"],False),
    ("fail",True,"allow_global_warnings",["ION_32198"],False),
])
def test_release_requires_actual_acceptance_and_recorded_human_choice(state,verified,choice,allow,expected):
    acceptance={"subject":"ION_32198","status":state,"scale_verified":verified}
    policy={"full_pass_release":True,"conditional_release":choice,"conditional_allowed_prerequisites":allow}
    assert batch.release_allowed(acceptance,policy) is expected
