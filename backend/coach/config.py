import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class WebSettings:
    production: bool
    origins: set[str]
    hosts: list[str]


def web_settings() -> WebSettings:
    environment = os.environ.get("COACH_ENV", "local")
    if environment not in {"local", "production"}:
        raise ValueError("COACH_ENV doit valoir local ou production")
    if environment == "local":
        return WebSettings(
            False,
            {
                f"http://{host}:{port}"
                for host in ("127.0.0.1", "localhost")
                for port in (5173, 8000)
            },
            ["127.0.0.1", "localhost", "testserver"],
        )
    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
    url = os.environ.get("COACH_PUBLIC_URL") or (f"https://{domain}" if domain else "")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or "*" in parsed.netloc
    ):
        raise ValueError("Configurer COACH_PUBLIC_URL avec une origine HTTPS valide")
    if len(os.environ.get("COACH_ACCESS_KEY", "")) < 32:
        raise ValueError("COACH_ACCESS_KEY doit contenir au moins 32 caractères aléatoires")
    return WebSettings(
        True,
        {f"https://{parsed.netloc}"},
        [parsed.hostname, "127.0.0.1", "localhost", "healthcheck.railway.app"],
    )


def data_dir() -> Path:
    path = Path(os.environ.get("COACH_DATA_DIR", ".local")).expanduser().absolute()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        path.chmod(0o700)
    return path


def user_id() -> str:
    return "local"
