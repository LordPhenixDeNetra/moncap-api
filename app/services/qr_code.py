from __future__ import annotations

import io
import pathlib
import uuid
from typing import Tuple

from app.core.settings import get_settings
from app.core.urls import to_absolute_public_url


QR_SUBDIR = "qr_codes"


class QRCodeStorageService:
    def __init__(self):
        settings = get_settings()
        self.root_dir = pathlib.Path(settings.storage_dir)
        self.public_prefix = settings.public_files_path.rstrip("/")

    def _ensure_dir(self) -> pathlib.Path:
        d = self.root_dir / QR_SUBDIR
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _file_path(self, adhesion_id: uuid.UUID | str) -> pathlib.Path:
        return self._ensure_dir() / f"{str(adhesion_id)}.png"

    def _relative_url(self, adhesion_id: uuid.UUID | str) -> str:
        return f"{self.public_prefix}/{QR_SUBDIR}/{str(adhesion_id)}.png"

    def build_paiement_url(self, adhesion_id: uuid.UUID | str) -> str:
        """
        Contenu textuel du QR Permanent d'un·e adhérent·e.

        (1) SCAN CAMÉRA → GET SIMPLE (pas de JWT). On DOIT pointer VERS L'URL BACKEND
        PUBLIC : `{BACKEND_URL}/api/v1/paiements/cotisation/qr-paiement-direct`
        qui initie AUTOMATIQUEMENT paiement mois courant puis HTTP 302 → Kopar.

        Ordre PRIORITÉ (IMPORTANT : jamais frontend) :
          1. settings.backend_public_base_url          ← paramètre EXPLICITE dédié QR (si renseigné en .env = le plus sûr)
          2. settings.api_base_url                     ← si ça ressemble clairement à un backend (alwaysdata / localhost / port API)
          3. fallback sûr prod Alwaysdata : https://thior.alwaysdata.net
        """
        settings = get_settings()
        explicit = (getattr(settings, "backend_public_base_url", None) or "").strip()
        if explicit.rstrip("/"):
            base_backend = explicit.rstrip("/")
        else:
            base_backend = ""
            api_val = (getattr(settings, "api_base_url", None) or "").strip()
            if api_val:
                low = api_val.lower()
                if (
                    "alwaysdata.net" in low
                    or "localhost" in low
                    or ":8000" in low
                    or ":8080" in low
                    or low.endswith("/api")
                ):
                    base_backend = api_val.rstrip("/")
            if not base_backend:
                # Fallback 100% sûr. Jamais https://moncap.innovamind.tech (= frontend)
                base_backend = "https://thior.alwaysdata.net"
        from urllib.parse import quote as _q
        return f"{base_backend}/api/v1/paiements/cotisation/qr-paiement-direct?adh={_q(str(adhesion_id))}&mois=auto"

    def generate_qr_png_bytes(self, content: str) -> bytes:
        try:
            import qrcode
        except ImportError as e:
            raise RuntimeError(
                "La bibliothèque 'qrcode' est requise. Installez-la avec : pip install qrcode[pil]"
            ) from e
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(content)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def generer_qr_adherent(
        self, adhesion_id: uuid.UUID | str, force_regenerate: bool = False
    ) -> Tuple[str, str]:
        path = self._file_path(adhesion_id)
        if not path.exists() or force_regenerate:
            content = self.build_paiement_url(adhesion_id)
            png = self.generate_qr_png_bytes(content)
            with path.open("wb") as f:
                f.write(png)
        rel = self._relative_url(adhesion_id)
        abs_url = to_absolute_public_url(rel)
        return rel, abs_url

    def regenerer_tous_sync_depuis_cli(self) -> int:
        """
        Usage : exclusivement depuis un CLI SYNCHRONE (python -m app.cli.regenerate_qrs).
        Depuis un contexte async (route/uvicorn), préférez regenerer_tous_async(db).
        """
        from sqlalchemy import select
        from app.db.session import AsyncSessionLocal
        from app.models.adhesion import Adhesion
        import asyncio

        async def _do() -> int:
            count = 0
            async with AsyncSessionLocal() as session:
                q = select(Adhesion.id)
                res = await session.execute(q)
                ids = list(res.scalars().all())
            for aid in ids:
                self.generer_qr_adherent(aid, force_regenerate=True)
                count += 1
            return count

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is None:
            return asyncio.run(_do())
        # déjà dans une loop async : créer une task mais l'appelant est sync
        # → lancer dans un thread séparé avec nouvelle loop
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(asyncio.run, _do()).result()

    async def regenerer_tous_async(self, db: AsyncSession) -> int:
        """
        Usage depuis contexte async (routes/services). Prend une session existante
        pour éviter de créer une nouvelle AsyncSessionLocal.
        """
        from sqlalchemy import select
        from app.models.adhesion import Adhesion

        q = select(Adhesion.id)
        res = await db.execute(q)
        ids = list(res.scalars().all())
        count = 0
        for aid in ids:
            self.generer_qr_adherent(aid, force_regenerate=True)
            count += 1
        return count
