from __future__ import annotations

UNSPLASH_FREE_PHOTOS: list[tuple[str, list[str]]] = [
    ("photo-1523805009345-7448845a9e53", ["senegal", "dakar", "afrique"]),
    ("photo-1519677100203-a0e668c924af", ["senegal", "desert", "dakar"]),
    ("photo-1525254531821-936423f1c911", ["mobilisation", "foule", "rallye"]),
    ("photo-1529107386315-e1a2ed48a620", ["education", "enfants", "ecole"]),
    ("photo-1509099836639-18ba1795237d", ["sante", "hopital", "soins"]),
    ("photo-1500937386664-56d1dfef3854", ["agriculture", "champs", "ferme"]),
    ("photo-1500595046743-cd271d694e30", ["dakar", "urbain", "ville"]),
    ("photo-1524492412937-b28074a5d7da", ["culture", "dakar", "senegal"]),
    ("photo-1516627145497-ae6968895b74", ["enfants", "senegal", "sourire"]),
    ("photo-1521207417037-69e9c2dbf4a9", ["marche", "commerce", "senegal"]),
    ("photo-1522202176988-66273c2fd55f", ["reunion", "place", "publique"]),
    ("photo-1517705008128-361805f42e86", ["village", "afrique", "maison"]),
    ("photo-1516026672322-bc52d61a5f2f", ["campagne", "senegal", "rural"]),
    ("photo-1520975954732-35dd22299614", ["rallye", "foule", "citoyen"]),
    ("photo-1517486808906-6ca8b3f04846", ["jeunesse", "senegal", "groupe"]),
    ("photo-1517420704952-d9f39e95b43d", ["politique", "discours", "meeting"]),
    ("photo-1508873536684-2f8d0d0e8a1f", ["culture", "senegal", "musique"]),
    ("photo-1504754524776-8f4f37790ca0", ["eleves", "education", "salle"]),
    ("photo-1517766526484-68379e165386", ["senegal", "paysage", "horizon"]),
    ("photo-1542601906990-b4d3fb778b09", ["candidature", "senegal", "rallye"]),
    ("photo-1507003211169-0a1dd7228f2d", ["portrait", "senegal", "personne"]),
    ("photo-1531746020798-e6953c6e8e04", ["portrait", "femme", "senegal"]),
    ("photo-1500648767791-00dcc994a43e", ["portrait", "homme", "senegal"]),
    ("photo-1529390079861-4de05781e842", ["rencontre", "citoyen", "senegal"]),
    ("photo-1528874073707-7639a0f62ae5", ["rassemblement", "militant", "senegal"]),
    ("photo-1542314831-2c1560d3478e", ["senegal", "transport", "urbain"]),
    ("photo-1495567721969-6641e513d98e", ["enfants", "senegal", "jeu"]),
    ("photo-1520637836862-4d197d17c0c4", ["femme", "senegal", "fier"]),
    ("photo-1515169805671-3521f86a880a", ["senegal", "ocean", "dakar"]),
    ("photo-1523920290228-4f321a939b4c", ["portrait", "jeune", "senegal"]),
    ("photo-1487412720507-e7ab37603c6f", ["afrique", "senegal", "paysage"]),
    ("photo-1469571486292-0ba58a3f068b", ["senegal", "culture", "paysan"]),
    ("photo-1493976040374-85c8e12f0c0e", ["senegal", "ville", "architecture"]),
    ("photo-1501555088652-021faa106b9b", ["travail", "senegal", "femme"]),
    ("photo-1528148343865-51218c5a34ae", ["foule", "senegal", "manifestation"]),
    ("photo-1528459801416-a9e53bbf4e17", ["education", "senegal", "apprentissage"]),
    ("photo-1531207230099-5dc86fcfaa38", ["fete", "senegal", "culture"]),
    ("photo-1524234107056-1c1f48f64ab8", ["groupe", "senegal", "jeunesse"]),
    ("photo-1518837695005-2083093ee35b", ["sante", "senegal", "medecin"]),
    ("photo-1497534547329-069a1dfa1913", ["militant", "senegal", "determine"]),
    ("photo-1528164344705-47542687000d", ["eleve", "ecole", "senegal"]),
    ("photo-1473081556163-1a2a7df4ea65", ["senegal", "peche", "cayor"]),
    ("photo-1531745054745-9e59131e95d1", ["femme", "senegal", "pagne"]),
    ("photo-1501426026826-31c667bdf23d", ["senegal", "voyage", "decouverte"]),
    ("photo-1520342868574-5fa3804e551c", ["meeting", "senegal", "discours"]),
    ("photo-1518792528505-98d2b5aba04b", ["senegal", "candidat", "rallye"]),
    ("photo-1531482615713-2afd69097998", ["manifestation", "senegal", "foule"]),
    ("photo-1511578314322-379afb476865", ["commerce", "senegal", "marchand"]),
]


def build_url(photo_id: str, *, width: int, height: int | None = None) -> str:
    if height is None:
        height = max(600, width * 2 // 3)
    return (
        f"https://images.unsplash.com/{photo_id}"
        f"?auto=compress&cs=tinysrgb&fit=crop&crop=entropy"
        f"&w={width}&h={height}&fm=jpg&q=82"
    )
