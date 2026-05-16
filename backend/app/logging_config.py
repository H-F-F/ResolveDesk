from __future__ import annotations

import logging

from .config import Settings, settings


def configure_logging(app_settings: Settings | None = None) -> None:
    runtime_settings = app_settings or settings
    runtime_settings.ensure_directories()
    log_path = runtime_settings.logs_dir / "app.log"

    logging.basicConfig(
        level=getattr(logging, runtime_settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
        force=True,
    )
