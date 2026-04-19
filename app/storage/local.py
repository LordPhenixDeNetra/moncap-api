from __future__ import annotations

import pathlib
import uuid

from fastapi import UploadFile

from app.core.settings import get_settings


class LocalStorage:
    def __init__(self) -> None:
        settings = get_settings()
        self.root_dir = pathlib.Path(settings.storage_dir)
        self.public_prefix = settings.public_files_path.rstrip("/")

    def _ensure_dir(self, subdir: str) -> pathlib.Path:
        d = self.root_dir / subdir
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def save(self, *, file: UploadFile, subdir: str) -> str:
        ext = pathlib.Path(file.filename or "").suffix
        name = f"{uuid.uuid4().hex}{ext}"
        target_dir = self._ensure_dir(subdir)
        path = target_dir / name

        with path.open("wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)

        rel_path = f"{subdir}/{name}"
        return f"{self.public_prefix}/{rel_path}"
