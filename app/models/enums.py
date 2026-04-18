from __future__ import annotations

from enum import StrEnum


class AdhesionStatus(StrEnum):
    en_attente = "en_attente"
    validee = "validee"
    rejetee = "rejetee"
    complement = "complement"


class EngagementType(StrEnum):
    politique = "politique"
    syndicalisme = "syndicalisme"
    societe_civile = "societe_civile"
    autre = "autre"


class PaymentMode(StrEnum):
    wave = "wave"
    orange_money = "orange_money"
    free_money = "free_money"
    carte_bancaire = "carte_bancaire"
    prelevement_bancaire = "prelevement_bancaire"
    especes = "especes"


class AppRole(StrEnum):
    admin = "admin"
    moderator = "moderator"
    user = "user"

