"""Focused identity and behavior tests for the Phase 2a contract migration."""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from cacheroute.contracts.v1.common import (
    ContractModel, GatewayTargetedRequest, SupportState, TokenInput,
    TokenReference, VersionedMessage,
)
from cacheroute.contracts.v1.errors import ContractError, ContractErrorDetail, OutcomeCode
from cacheroute.runtime import RuntimeProfile
from kdn_server.contracts import common as legacy_common
from kdn_server.contracts import errors as legacy_errors
from kdn_server.domain import RuntimeProfile as LegacyRuntimeProfile


def test_runtime_profile_identity_values_and_resolution():
    assert LegacyRuntimeProfile is RuntimeProfile
    assert [profile.value for profile in RuntimeProfile] == ["v1", "legacy", "test/mock", "auto"]
    assert RuntimeProfile.normalize("modern") is RuntimeProfile.V1
    assert RuntimeProfile.normalize("old") is RuntimeProfile.LEGACY
    assert RuntimeProfile.resolve_startup("auto", v1_available=True) is RuntimeProfile.V1
    assert RuntimeProfile.resolve_startup("auto", v1_available=False) is RuntimeProfile.LEGACY
    assert RuntimeProfile.resolve_auto.__func__ is RuntimeProfile.resolve_startup.__func__
    with pytest.raises(ValueError, match="unsupported CACHEROUTE_RUNTIME_PROFILE"):
        RuntimeProfile.normalize("future")


def test_legacy_common_and_error_symbols_preserve_identity():
    for symbol in (
        ContractModel, VersionedMessage, GatewayTargetedRequest, SupportState,
        TokenReference, TokenInput,
    ):
        assert getattr(legacy_common, symbol.__name__) is symbol
    assert legacy_errors.OutcomeCode is OutcomeCode
    assert legacy_errors.ContractErrorDetail is ContractErrorDetail
    assert legacy_errors.ContractError is ContractError is ContractErrorDetail


def test_common_contract_behavior_is_preserved():
    message = VersionedMessage(runtime_profile="modern", request_id="request")
    assert message.model_dump(mode="json")["runtime_profile"] == "v1"
    assert VersionedMessage.model_validate_json(message.model_dump_json()) == message
    with pytest.raises(ValidationError, match="unsupported contract version"):
        message.model_copy(update={"contract_version": "kdn.v2"})
    with pytest.raises(ValidationError, match="startup-only"):
        VersionedMessage(runtime_profile="auto")

    legacy = GatewayTargetedRequest(
        runtime_profile="legacy", compatibility_profile_id="compat",
        endpoint_id="endpoint_" + "a" * 32, endpoint_generation=0,
    )
    assert legacy.endpoint_generation == 0
    with pytest.raises(ValidationError, match="only valid for Legacy"):
        legacy.model_copy(update={"runtime_profile": "v1"})


def test_token_input_support_state_and_outcome_wire_values():
    assert TokenInput(token_ids=(0, 2)).token_ids == (0, 2)
    assert TokenInput(token_reference={"reference_id": "tokens"}).token_reference.reference_id == "tokens"
    for invalid in ({}, {"token_ids": (1,), "token_reference": {"reference_id": "tokens"}}):
        with pytest.raises(ValidationError, match="provide exactly one"):
            TokenInput(**invalid)
    assert bool(SupportState.SUPPORTED)
    assert not bool(SupportState.UNSUPPORTED)
    assert not bool(SupportState.UNKNOWN)
    assert [code.value for code in OutcomeCode] == [
        "success", "unsupported", "incompatible", "stale", "partial", "failed",
        "cancelled", "text_fallback", "idempotency_conflict",
    ]


def test_legacy_foundation_modules_are_import_only_shims():
    root = Path(__file__).resolve().parents[1]
    for relative in ("kdn_server/contracts/common.py", "kdn_server/contracts/errors.py"):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        assert all(
            isinstance(node, ast.ImportFrom)
            or (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str))
            for node in tree.body
        )
