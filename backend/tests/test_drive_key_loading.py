"""
Regression tests for service-account key loading from a Render Secret File.
Uses a throwaway locally generated RSA key -- never a real Google credential,
and no key material is ever printed.
"""
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.services.drive_service import DriveSourceError, _load_service_account_info


def _fake_service_account_info():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return {
        "type": "service_account",
        "project_id": "probe-project",
        "private_key_id": "probekeyid",
        "private_key": pem,
        "client_email": "probe@probe-project.iam.gserviceaccount.com",
        "client_id": "123456789",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def _write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_loads_valid_key_with_real_newlines(tmp_path):
    info = _fake_service_account_info()
    path = _write(tmp_path, "good.json", json.dumps(info))
    loaded = _load_service_account_info(path)
    assert "\n" in loaded["private_key"]
    assert loaded["type"] == "service_account"


def test_loads_key_with_literal_backslash_n_newlines(tmp_path):
    """Render Secret File mangling: private_key newlines stored as \\n text."""
    info = _fake_service_account_info()
    mangled = dict(info)
    mangled["private_key"] = info["private_key"].replace("\n", "\\n")
    path = _write(tmp_path, "escaped.json", json.dumps(mangled))
    loaded = _load_service_account_info(path)
    assert "\n" in loaded["private_key"]
    assert "\\n" not in loaded["private_key"]
    assert loaded["private_key"] == info["private_key"]


def test_loads_key_from_double_quoted_secret(tmp_path):
    """Render Secret File mangling: whole JSON wrapped in double quotes."""
    info = _fake_service_account_info()
    path = _write(tmp_path, "quoted.json", json.dumps(json.dumps(info)))
    loaded = _load_service_account_info(path)
    assert loaded["private_key"] == info["private_key"]


def test_rejects_invalid_json_without_leaking_contents(tmp_path):
    path = _write(tmp_path, "bad.json", "not json at all")
    try:
        _load_service_account_info(path)
    except DriveSourceError as exc:
        assert "not valid JSON" in str(exc)
        assert "not json" not in str(exc).replace("not valid JSON", "")
    else:
        raise AssertionError("expected DriveSourceError")


def test_rejects_json_without_private_key(tmp_path):
    path = _write(tmp_path, "empty.json", json.dumps({"type": "service_account"}))
    try:
        _load_service_account_info(path)
    except DriveSourceError as exc:
        assert "private_key" in str(exc)
    else:
        raise AssertionError("expected DriveSourceError")
