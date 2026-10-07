import pytest
from fastapi.testclient import TestClient

from coach import api, config, server


@pytest.fixture
def production(monkeypatch, tmp_path):
    monkeypatch.setenv("COACH_ENV", "production")
    monkeypatch.setenv("COACH_PUBLIC_URL", "https://coach.example")
    monkeypatch.setenv("COACH_ACCESS_KEY", "x" * 40)
    monkeypatch.setenv("COACH_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_ID", raising=False)
    monkeypatch.delenv("RAILWAY_PUBLIC_DOMAIN", raising=False)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://coach.example",
        "https://coach.example/path",
        "https://user:pass@coach.example",
        "https://*.example",
    ],
)
def test_production_rejects_invalid_origin(production, monkeypatch, url):
    monkeypatch.setenv("COACH_PUBLIC_URL", url)
    with pytest.raises(ValueError):
        config.web_settings()


def test_key_and_railway_domain(production, monkeypatch):
    monkeypatch.delenv("COACH_PUBLIC_URL")
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "coach.up.railway.app")
    settings = config.web_settings()
    assert settings.origins == {"https://coach.up.railway.app"}
    assert "healthcheck.railway.app" in settings.hosts
    monkeypatch.setenv("COACH_ACCESS_KEY", "weak")
    with pytest.raises(ValueError):
        config.web_settings()


def test_secure_session_and_cross_origin(production, monkeypatch):
    settings = config.web_settings()
    monkeypatch.setattr(api, "settings", settings)
    monkeypatch.setattr(api, "ALLOWED_ORIGINS", settings.origins)
    api.sessions.clear()
    api.login_attempts.clear()
    # Fresh middleware stack with production Host allowlist, without reloading global modules.
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    monkeypatch.setattr(api.app, "middleware_stack", None)
    monkeypatch.setattr(api.app, "user_middleware", list(api.app.user_middleware))
    for middleware in api.app.user_middleware:
        if middleware.cls is TrustedHostMiddleware:
            api.app.user_middleware[api.app.user_middleware.index(middleware)] = type(middleware)(
                TrustedHostMiddleware, allowed_hosts=settings.hosts
            )
            break
    with TestClient(
        api.app, base_url="https://coach.example", headers={"Origin": "https://coach.example"}
    ) as client:
        assert client.get("/api/dashboard").status_code == 401
        assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400
        assert (
            client.get("/api/health", headers={"Host": "healthcheck.railway.app"}).status_code
            == 200
        )
        assert (
            client.post(
                "/api/login",
                json={"access_key": "x" * 40},
                headers={"Origin": "http://localhost:8000"},
            ).status_code
            == 403
        )
        response = client.post("/api/login", json={"access_key": "x" * 40})
        assert response.status_code == 200
        assert "Secure" in response.headers["set-cookie"]
        assert "HttpOnly" in response.headers["set-cookie"]
        assert client.get("/api/dashboard").status_code == 200
        assert client.post("/api/logout").status_code == 200
        assert client.get("/api/dashboard").status_code == 401
    api.app.middleware_stack = None


def test_railway_refuses_ephemeral_storage(production, monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "test-environment")
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    with pytest.raises(ValueError, match="volume"):
        server.main()


def test_railway_start_uses_port_and_one_worker(production, monkeypatch, tmp_path):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "test-environment")
    monkeypatch.setenv("RAILWAY_VOLUME_MOUNT_PATH", str(tmp_path))
    monkeypatch.setenv("PORT", "9000")
    calls = []
    monkeypatch.setattr(server.uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs))
    server.main()
    assert calls == [{"host": "0.0.0.0", "port": 9000, "workers": 1, "proxy_headers": False}]
