"""Single-process entry point for a service behind Railway's HTTPS ingress."""

import os
from pathlib import Path

import uvicorn

from coach.config import data_dir, web_settings


def main():
    settings = web_settings()
    if settings.production:
        storage = data_dir()
        if os.environ.get("RAILWAY_ENVIRONMENT_ID"):
            mount = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
            if not mount or storage != Path(mount).resolve():
                raise ValueError("Attacher le volume Railway au dossier COACH_DATA_DIR")
    # One worker: SQLite, sessions and integration locks are process-local.
    # Do not trust client-supplied forwarded headers for authentication rate limits.
    uvicorn.run(
        "coach.api:app",
        host="0.0.0.0" if settings.production else "127.0.0.1",
        port=int(os.environ.get("PORT", "8000")),
        workers=1,
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
