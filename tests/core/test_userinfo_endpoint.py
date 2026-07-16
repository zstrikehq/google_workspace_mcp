from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import core.server as server_module


def _client(monkeypatch, provider):
    monkeypatch.setattr(server_module, "get_auth_provider", lambda: provider)
    app = Starlette(routes=[Route("/userinfo", server_module.userinfo, methods=["GET"])])
    return TestClient(app)


@pytest.mark.parametrize(
    "authorization",
    [None, "", "Basic abc", "Bearer", "Bearer one two"],
)
def test_userinfo_requires_one_bearer_token(monkeypatch, authorization):
    provider = SimpleNamespace(load_access_token=AsyncMock())
    client = _client(monkeypatch, provider)
    headers = {"Authorization": authorization} if authorization is not None else {}

    response = client.get("/userinfo", headers=headers)

    assert response.status_code == 401
    assert response.json() == {"error": "invalid_token"}
    assert response.headers["www-authenticate"] == 'Bearer error="invalid_token"'
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    provider.load_access_token.assert_not_awaited()


def test_userinfo_rejects_invalid_mcp_token(monkeypatch):
    provider = SimpleNamespace(load_access_token=AsyncMock(return_value=None))
    client = _client(monkeypatch, provider)

    response = client.get(
        "/userinfo", headers={"Authorization": "Bearer invalid-token"}
    )

    assert response.status_code == 401
    assert response.json() == {"error": "invalid_token"}
    provider.load_access_token.assert_awaited_once_with("invalid-token")


def test_userinfo_returns_google_identity_for_valid_mcp_token(monkeypatch):
    validated_token = SimpleNamespace(
        client_id="google-subject-123",
        claims={
            "email": "user@company.com",
            "email_verified": "true",
        },
    )
    provider = SimpleNamespace(
        load_access_token=AsyncMock(return_value=validated_token)
    )
    client = _client(monkeypatch, provider)

    response = client.get(
        "/userinfo", headers={"Authorization": "Bearer mcp.jwt.token"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "sub": "google-subject-123",
        "email": "user@company.com",
        "email_verified": True,
    }
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    provider.load_access_token.assert_awaited_once_with("mcp.jwt.token")


def test_userinfo_is_registered_on_the_fastmcp_http_app(monkeypatch):
    validated_token = SimpleNamespace(
        client_id="google-subject-123",
        claims={
            "email": "user@company.com",
            "email_verified": True,
        },
    )
    provider = SimpleNamespace(
        load_access_token=AsyncMock(return_value=validated_token)
    )
    monkeypatch.setattr(server_module, "get_auth_provider", lambda: provider)
    app = server_module.server.http_app(transport="streamable-http", path="/mcp")
    client = TestClient(app)

    response = client.get(
        "/userinfo", headers={"Authorization": "Bearer mcp.jwt.token"}
    )

    assert response.status_code == 200
    assert response.json()["sub"] == "google-subject-123"


def test_userinfo_prefers_explicit_google_sub_and_preserves_unverified_email(
    monkeypatch,
):
    validated_token = SimpleNamespace(
        client_id="fallback-subject",
        claims={
            "sub": "explicit-google-subject",
            "email": "user@company.com",
            "email_verified": "false",
        },
    )
    provider = SimpleNamespace(
        load_access_token=AsyncMock(return_value=validated_token)
    )
    client = _client(monkeypatch, provider)

    response = client.get(
        "/userinfo", headers={"Authorization": "Bearer mcp.jwt.token"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "sub": "explicit-google-subject",
        "email": "user@company.com",
        "email_verified": False,
    }


def test_userinfo_rejects_token_without_google_identity(monkeypatch):
    validated_token = SimpleNamespace(client_id=None, claims={})
    provider = SimpleNamespace(
        load_access_token=AsyncMock(return_value=validated_token)
    )
    client = _client(monkeypatch, provider)

    response = client.get(
        "/userinfo", headers={"Authorization": "Bearer mcp.jwt.token"}
    )

    assert response.status_code == 401
    assert response.json() == {"error": "invalid_token"}


def test_userinfo_returns_service_unavailable_when_provider_is_missing(monkeypatch):
    client = _client(monkeypatch, None)

    response = client.get(
        "/userinfo", headers={"Authorization": "Bearer mcp.jwt.token"}
    )

    assert response.status_code == 503
    assert response.json() == {"error": "temporarily_unavailable"}


def test_userinfo_hides_provider_failures(monkeypatch):
    provider = SimpleNamespace(
        load_access_token=AsyncMock(side_effect=RuntimeError("storage details"))
    )
    client = _client(monkeypatch, provider)

    response = client.get(
        "/userinfo", headers={"Authorization": "Bearer mcp.jwt.token"}
    )

    assert response.status_code == 503
    assert response.json() == {"error": "temporarily_unavailable"}
    assert "storage details" not in response.text
