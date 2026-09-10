from __future__ import annotations

import hmac
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from app.core.settings import get_settings
from app.models.paiements import StatutTransactionKopar


logger = logging.getLogger(__name__)


KOPAR_SERVICES = {
    "orange_money_sn": "Orange Money Sénégal",
    "wave_checkout": "Wave Sénégal",
    "wave_checkout_ci": "Wave Côte d'Ivoire",
    "kopar_services_cross": "Paiement par carte bancaire",
}


class KoparError(Exception):
    def __init__(self, message: str, status_code: int = 500, details: Any = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details


@dataclass(frozen=True)
class KoparPaiementInitie:
    token: str
    payment_url: str | None
    qr_code: str | None
    montant: int
    devise: str
    provider_response: dict | None


@dataclass(frozen=True)
class KoparTransactionDetail:
    token: str
    kopar_id: str | None
    statut: StatutTransactionKopar
    montant: int
    devise: str
    service: str | None
    data: dict


def verify_kopar_signature(request_body: str, signature: str, private_key: str) -> bool:
    if not request_body or not signature or not private_key:
        return False
    computed = hmac.new(
        private_key.encode("utf-8"),
        request_body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, signature.lower())


def webhook_statut_to_enum(statut: str) -> StatutTransactionKopar:
    s = (statut or "").strip().lower()
    mapping = {
        "new": StatutTransactionKopar.new,
        "pending": StatutTransactionKopar.pending,
        "success": StatutTransactionKopar.success,
        "failed": StatutTransactionKopar.failed,
        "failed_orange_money_timeout": StatutTransactionKopar.failed,
        "cancelled": StatutTransactionKopar.cancelled,
        "canceled": StatutTransactionKopar.cancelled,
        "refunded": StatutTransactionKopar.refunded,
    }
    return mapping.get(s, StatutTransactionKopar.pending)


def api_statut_to_enum(statut: str) -> StatutTransactionKopar:
    return webhook_statut_to_enum(statut)


class KoparClient:
    def __init__(self):
        settings = get_settings()
        self.enabled = settings.kopar_enabled
        self.base_url = (settings.kopar_base_url or "https://koparpay.com").rstrip("/")
        self.api_key = settings.kopar_api_key or ""
        self.private_key = settings.kopar_private_key or ""
        self.timeout = 30.0

    async def _post(self, path: str, payload: dict) -> dict:
        if not self.enabled:
            raise KoparError("Kopar Pay désactivé (KOPAR_ENABLED=false)", 503)
        if not self.api_key:
            raise KoparError("Kopar API Key absente", 500)
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
                if r.status_code >= 500:
                    logger.error(
                        "Kopar erreur serveur HTTP %s sur %s — body=%s — payload envoyé=%s",
                        r.status_code,
                        url,
                        r.text[:500],
                        payload,
                    )
                    raise KoparError(
                        f"Kopar erreur serveur HTTP {r.status_code}",
                        r.status_code,
                        r.text[:500],
                    )
                try:
                    data = r.json()
                except Exception:
                    data = {"_raw": r.text[:500]}
                if r.status_code >= 400:
                    msg = data.get("message") or data.get("error") or f"Erreur Kopar HTTP {r.status_code}"
                    err_details = data.get("details") or data.get("errors") or data.get("data") or data
                    logger.warning(
                        "Kopar HTTP %s sur %s — message=%s — details bruts kopar=%s — payload envoyé=%s",
                        r.status_code,
                        url,
                        msg,
                        err_details,
                        payload,
                    )
                    raise KoparError(msg, r.status_code, data)
                return data
        except KoparError:
            raise
        except httpx.TimeoutException as e:
            raise KoparError("Délai Kopar dépassé", 504, str(e))
        except Exception as e:
            raise KoparError(f"Echec appel Kopar: {e}", 500)

    async def _get(self, path: str) -> dict:
        if not self.enabled:
            raise KoparError("Kopar Pay désactivé (KOPAR_ENABLED=false)", 503)
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(url, headers={"Content-Type": "application/json"})
                if r.status_code >= 500:
                    raise KoparError(
                        f"Kopar erreur serveur HTTP {r.status_code}",
                        r.status_code,
                        r.text[:500],
                    )
                try:
                    data = r.json()
                except Exception:
                    data = {"_raw": r.text[:500]}
                if r.status_code >= 400:
                    msg = data.get("message") or f"Erreur Kopar HTTP {r.status_code}"
                    raise KoparError(msg, r.status_code, data)
                return data
        except KoparError:
            raise
        except httpx.TimeoutException as e:
            raise KoparError("Délai Kopar dépassé", 504, str(e))
        except Exception as e:
            raise KoparError(f"Echec appel Kopar: {e}", 500)

    async def creer_transaction(
        self,
        *,
        item_price: int,
        command_name: str,
        command_ref: str,
        ipn_url: str,
        success_url: str,
        cancel_url: str,
        first_name: str | None = None,
        last_name: str | None = None,
        email: str | None = None,
        phone_number: str | None = None,
        country_code: str = "SN",
        currency: str = "XOF",
        editable_amount: bool = False,
        custom_fields: dict | None = None,
        document_number: str | None = None,
        document_type: str = "CNI",
        birth_date: date | None = None,
        birth_place: str | None = "",
        city: str | None = "",
        address: str | None = "",
        service_paiement: str | None = None,
    ) -> KoparPaiementInitie:
        payload: dict[str, Any] = {
            "apiKey": self.api_key,
            "itemPrice": item_price,
            "commandName": command_name,
            "commandRef": command_ref,
            "ipnUrl": ipn_url,
            "successUrl": success_url,
            "cancelUrl": cancel_url,
            "editableAmount": editable_amount,
            "currency": currency,
            "countryCode": country_code,
        }
        if first_name:
            payload["firstName"] = first_name
        if last_name:
            payload["lastName"] = last_name
        if email:
            payload["email"] = email
        if phone_number:
            payload["phoneNumber"] = phone_number
        if custom_fields:
            payload["customFields"] = json.dumps(custom_fields, ensure_ascii=False)

        user_kyc: dict[str, Any] = {}
        if first_name:
            user_kyc["firstName"] = first_name
        if last_name:
            user_kyc["lastName"] = last_name
        if phone_number:
            user_kyc["phoneNumber"] = phone_number
        if email:
            user_kyc["email"] = email
        if document_number:
            user_kyc["documentNumber"] = document_number
            user_kyc["documentType"] = document_type or "CNI"
        if birth_date is not None:
            user_kyc["birthDate"] = (
                birth_date.isoformat() if hasattr(birth_date, "isoformat") else str(birth_date)
            )
        if birth_place:
            user_kyc["birthPlace"] = birth_place
        if country_code:
            user_kyc["country"] = country_code
        if city is not None:
            user_kyc["city"] = city
        if address is not None:
            user_kyc["address"] = address
        payload["userKyc"] = user_kyc

        service = service_paiement or "kopar_services_cross"
        mapping: dict[str, str] = {
            "wave_checkout": "wave",
            "orange_money_sn": "orange_money",
            "wave_checkout_ci": "wave",
            "kopar_services_cross": "kopar_cross",
        }
        payment_method = mapping.get(service, service)
        bank_details: dict[str, Any] = {
            "paymentMethod": payment_method,
            "phone": phone_number or "",
            "country": country_code or "SN",
            "currency": currency or "XOF",
            "serviceId": service,
        }
        payload["bankDetails"] = bank_details

        data = await self._post("/api/v2/transaction/request", payload)
        status = data.get("status")
        token = data.get("token")
        if not token or str(status).upper() != "SUCCESS":
            raise KoparError(
                data.get("message") or "Echec création transaction Kopar",
                502,
                data,
            )
        payment_url = f"{self.base_url}/payment/orders/{token}"
        return KoparPaiementInitie(
            token=token,
            payment_url=payment_url,
            qr_code=None,
            montant=item_price,
            devise=currency,
            provider_response=data,
        )

    async def checkout(
        self,
        token: str,
        service: str,
        *,
        user_kyc: dict | None = None,
        bank_details: dict | None = None,
        country_code: str = "SN",
        currency: str = "XOF",
        phone_number: str | None = None,
    ) -> KoparPaiementInitie:
        payload: dict[str, Any] = {"service": service}
        if user_kyc:
            payload["userKyc"] = user_kyc
        else:
            payload["userKyc"] = {
                "country": country_code,
                "city": "",
                "address": "",
            }
        if bank_details:
            payload["bankDetails"] = bank_details
        else:
            mapping = {
                "wave_checkout": "wave",
                "orange_money_sn": "orange_money",
                "wave_checkout_ci": "wave",
                "kopar_services_cross": "kopar_cross",
            }
            payment_method = mapping.get(service, service)
            payload["bankDetails"] = {
                "paymentMethod": payment_method,
                "phone": phone_number or "",
                "country": country_code,
                "currency": currency,
                "serviceId": service,
            }
        data = await self._post(f"/api/v2/transaction/{token}/checkout", payload)
        data_node = data.get("data") or {}
        tx = data_node.get("transaction") or {}
        provider = data_node.get("providerResponse") or {}
        montant = int(tx.get("amountXof") or tx.get("amount") or 0)
        devise = str(tx.get("currency") or "XOF")
        payment_url = provider.get("paymentUrl")
        qr_code = provider.get("qrCode")
        return KoparPaiementInitie(
            token=token,
            payment_url=payment_url,
            qr_code=qr_code,
            montant=montant,
            devise=devise,
            provider_response=data,
        )

    async def get_transaction_detail(self, token: str) -> KoparTransactionDetail:
        data = await self._get(f"/api/v2/transaction/{token}")
        statut_str = "new"
        inner = data.get("data") or {}
        if isinstance(inner, dict):
            statut_str = inner.get("status") or data.get("status") or "new"
        else:
            statut_str = data.get("status") or "new"
        statut = api_statut_to_enum(statut_str)
        montant = int(inner.get("amountXof") or inner.get("amount") or 0) if isinstance(inner, dict) else 0
        devise = (inner.get("currency") if isinstance(inner, dict) else None) or "XOF"
        service_obj = (inner.get("service") if isinstance(inner, dict) else None) or {}
        service = service_obj.get("serviceName") if isinstance(service_obj, dict) else None
        kopar_id = (inner.get("koparId") if isinstance(inner, dict) else None) or None
        return KoparTransactionDetail(
            token=token,
            kopar_id=kopar_id,
            statut=statut,
            montant=montant,
            devise=devise,
            service=service,
            data=data,
        )

    async def rembourser(self, token: str, reason: str = "") -> dict:
        return await self._post(
            f"/api/v2/transaction/{token}/refund",
            {"reason": reason},
        )
