"""Tests for apply.db, apply.vault, and apply.profile."""

from __future__ import annotations

from pathlib import Path

import pytest

from apply.db import (
    create_application,
    create_apply_engine,
    get_auth_credential,
    get_or_create_default_user,
    list_applications,
    update_user_profile,
    upsert_auth_credential,
)
from apply.profile import resolve_application_email
from apply.vault import Vault, generate_strong_password


def test_vault_encrypt_decrypt_roundtrip(tmp_path: Path) -> None:
    key_file = tmp_path / "vault.key"
    vault = Vault(key_file=key_file)
    secret = "super-secret-workday-password-!23"
    token = vault.encrypt(secret)
    assert token != secret
    assert vault.decrypt(token) == secret

    # Reloading from the same key_file decrypts identically
    vault2 = Vault(key_file=key_file)
    assert vault2.decrypt(token) == secret


def test_vault_wrong_key_raises(tmp_path: Path) -> None:
    v1 = Vault(key_file=tmp_path / "k1.key")
    v2 = Vault(key_file=tmp_path / "k2.key")
    token = v1.encrypt("hello")
    with pytest.raises(ValueError, match="Unable to decrypt"):
        v2.decrypt(token)


def test_generate_strong_password() -> None:
    pw = generate_strong_password(20)
    assert len(pw) == 20
    assert any(c.islower() for c in pw)
    assert any(c.isupper() for c in pw)
    assert any(c.isdigit() for c in pw)


def test_resolve_application_email() -> None:
    assert resolve_application_email("alex@gmail.com", "direct", "cae") == "alex@gmail.com"
    assert (
        resolve_application_email("alex@gmail.com", "plus_address", "TD Bank")
        == "alex+tdbank@gmail.com"
    )
    assert (
        resolve_application_email("alex+old@gmail.com", "plus_address", "cae")
        == "alex+cae@gmail.com"
    )


def test_apply_db_crud_and_credentials() -> None:
    engine = create_apply_engine("sqlite:///:memory:")
    user = get_or_create_default_user(engine)
    assert user.id >= 1
    assert user.settings["execution_mode"] == "copilot"

    updated = update_user_profile(
        engine,
        user.id,
        display_name="Alex Rivera",
        primary_email="alex@example.com",
        email_alias_strategy="plus_address",
    )
    assert updated.display_name == "Alex Rivera"
    assert updated.email_alias_strategy == "plus_address"

    upsert_auth_credential(
        engine,
        user_id=user.id,
        auth_scope="tenant",
        domain_key="cae.wd3.myworkdayjobs.com",
        board="workday",
        email_used="alex+cae@example.com",
        encrypted_password="enc",
        encrypted_storage_state=None,
        provision_method="auto_created",
        status="needs_verification",
    )
    cred = get_auth_credential(engine, user.id, "cae.wd3.myworkdayjobs.com")
    assert cred is not None
    assert cred.email_used == "alex+cae@example.com"

    app = create_application(
        engine,
        user_id=user.id,
        job_snapshot={
            "id": "cae:R100",
            "company": "CAE",
            "title": "Software Engineer",
            "url": "https://cae.wd3.myworkdayjobs.com/en-US/career/job/R100",
            "source": "workday",
        },
        match_score=82.5,
        status="ready_for_review",
    )
    apps = list_applications(engine, user.id)
    assert len(apps) == 1
    assert apps[0].id == app.id
