"""Static guard for explicit runtime privileges introduced through OE-4."""

import importlib.util
from pathlib import Path
from types import ModuleType

TOOL = Path(__file__).parents[3] / "tools" / "postgres_roles.py"


def _policy() -> ModuleType:
    spec = importlib.util.spec_from_file_location("twf_postgres_roles", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_oe4_runtime_privileges_are_explicit_and_minimal() -> None:
    policy = _policy()
    expected = {
        "twf_public_id_counters": {"SELECT", "INSERT", "UPDATE"},
        "twf_order_public_ids": {"SELECT", "INSERT"},
        "twf_queue_dispatch_policies": {"SELECT", "INSERT", "UPDATE"},
        "twf_queue_policy_events": {"SELECT", "INSERT"},
        "twf_dispatch_attempts": {"SELECT", "INSERT", "UPDATE"},
    }
    assert {table: set(policy._expected_table_privileges(table)) for table in expected} == expected
    assert not expected.keys() & policy.REQUIRED_DELETE_TABLES
    assert policy.RUNTIME_SEQUENCES == frozenset()
    assert policy.PROTECTED_TRIGGER_FUNCTIONS == {
        "twf_dispatch_attempt_identity_immutable",
        "twf_order_event_immutable",
        "twf_queue_event_immutable",
        "twf_queue_snapshot_immutable",
    }
    assert "GRANT ALL" not in TOOL.read_text()
