import json
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from coach.chatgpt import ISSUER, authorization, consume_events, validate_callback, verify_identity


def test_pkce_and_dynamic_registration():
    url, redirect = authorization("test-verifier", "state", "nonce", "host", 1455, {})
    p = parse_qs(urlsplit(url).query)
    assert p["client_id"] == ["dynamic_agent_client"]
    assert p["agent_name_hint"] == ["Coach AI"]
    assert p["code_challenge_method"] == ["S256"]
    assert "test-verifier" not in url
    assert redirect == "http://127.0.0.1:1455/auth/callback"
    url, _ = authorization(
        "v", "s", "n", "host", 1455, {"client_id": "issued", "id_token": "secret-identity-token"}
    )
    assert "agent_name_hint" not in url
    assert "secret-identity-token" not in url
    assert parse_qs(urlsplit(url).query)["client_id"] == ["issued"]


@pytest.mark.parametrize(
    "params",
    [
        {"state": "wrong", "code": "c", "client_id": "issued"},
        {"state": "state", "error": "access_denied"},
        {"state": "state", "code": "c"},
        {"state": "state", "code": "c", "client_id": "dynamic_agent_client"},
    ],
)
def test_invalid_callback_rejected(params):
    with pytest.raises(ValueError):
        validate_callback(params, "state", {})


def test_returning_callback_cannot_replace_client():
    with pytest.raises(ValueError):
        validate_callback(
            {"state": "s", "code": "c", "client_id": "other"}, "s", {"client_id": "issued"}
        )
    assert validate_callback({"state": "s", "code": "c"}, "s", {"client_id": "issued"}) == (
        "issued",
        "c",
    )


def test_identity_signature_nonce_audience_and_permissions():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_client = SimpleNamespace(
        get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key())
    )
    claims = {
        "iss": ISSUER,
        "aud": "issued",
        "sub": "user",
        "exp": time.time() + 60,
        "iat": time.time(),
        "nonce": "nonce",
    }
    tokens = {
        "id_token": jwt.encode(claims, private, algorithm="RS256"),
        "scope": "chatgpt.tokens.use.direct",
    }
    assert verify_identity(tokens, "issued", "nonce", {}, key_client)["sub"] == "user"
    with pytest.raises(ValueError):
        verify_identity(tokens, "issued", "wrong", {}, key_client)
    with pytest.raises(jwt.InvalidAudienceError):
        verify_identity(tokens, "wrong", "nonce", {}, key_client)
    with pytest.raises(ValueError):
        verify_identity({**tokens, "scope": "openid"}, "issued", "nonce", {}, key_client)
    with pytest.raises(ValueError):
        verify_identity(tokens, "issued", "nonce", {"subject": "another"}, key_client)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(jwt.InvalidSignatureError):
        verify_identity(
            {**tokens, "id_token": jwt.encode(claims, other, algorithm="RS256")},
            "issued",
            "nonce",
            {},
            key_client,
        )


def events(*values):
    return ["data: " + json.dumps(v) for v in values]


def test_sse_requires_terminal_success():
    delta = {"type": "response.output_text.delta", "delta": "Bonjour"}
    assert consume_events(
        events(delta, {"type": "response.completed", "response": {"usage": {"input_tokens": 12}}})
    ) == ("Bonjour", {"input_tokens": 12})
    with pytest.raises(ValueError):
        consume_events(events(delta))
    with pytest.raises(ValueError):
        consume_events(events(delta, {"type": "response.failed"}))
    with pytest.raises(ValueError):
        consume_events(events(delta, {"type": "response.incomplete"}))
