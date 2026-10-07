import os
from pathlib import Path


def data_dir() -> Path:
    path = Path(os.environ.get("COACH_DATA_DIR", ".local")).expanduser().absolute()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        path.chmod(0o700)
    return path


def user_id() -> str:
    return "local"
