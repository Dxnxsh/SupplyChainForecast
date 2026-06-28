"""Weak supervision: keyword buckets → disruption category → binary + heuristic impact (optional training path)."""

from __future__ import annotations

CATEGORY_RULES: dict[str, list[str]] = {
    "Port Congestion": [
        "port congestion", "port delay", "container backlog", "terminal congestion",
        "dockworker", "longshoreman", "port strike", "berth", "vessel queue",
        "port capacity", "container terminal", "port closure", "shipping terminal",
        "la port", "los angeles port", "long beach", "rotterdam port",
        "shanghai port", "singapore port", "container ship queue",
    ],
    "Shipping Delay": [
        "shipping delay", "freight delay", "ocean freight", "sea freight",
        "container shortage", "blank sailing", "vessel delay", "ship delay",
        "cargo delay", "shipping backlog", "transit time", "delayed shipment",
        "freight rate", "suez canal", "panama canal", "red sea", "shipping route",
        "air freight capacity", "shipping disruption", "carrier", "booking",
    ],
    "Manufacturing Shortage": [
        "semiconductor shortage", "chip shortage", "chip supply", "microchip",
        "raw material shortage", "material shortage", "component shortage",
        "factory shutdown", "production halt", "plant closure", "production cut",
        "manufacturing disruption", "supply shortage", "inventory shortage",
        "auto parts", "electronics shortage", "battery shortage", "lithium",
        "rare earth", "steel shortage", "aluminum shortage", "resin shortage",
    ],
    "Geopolitical": [
        "trade war", "tariff", "sanction", "trade restriction", "trade ban",
        "geopolit", "military conflict", "war", "invasion", "blockade",
        "trade dispute", "trade tension", "export control", "import ban",
        "embargo", "nato", "china us trade", "us china", "russia ukraine",
        "middle east", "iran", "north korea", "taiwan strait", "trade policy",
    ],
    "Weather / Natural Disaster": [
        "hurricane", "typhoon", "cyclone", "flood", "flooding", "earthquake",
        "tsunami", "wildfire", "drought", "storm", "blizzard", "snowstorm",
        "extreme weather", "natural disaster", "climate", "tornado",
        "heat wave", "monsoon", "landslide", "volcano", "infrastructure damage",
    ],
}

NORMAL_LABEL = "Normal"

IMPACT_HEURISTIC_BY_CATEGORY: dict[str, float] = {
    NORMAL_LABEL: 0.0,
    "Port Congestion": 110.0,
    "Shipping Delay": 95.0,
    "Manufacturing Shortage": 130.0,
    "Geopolitical": 100.0,
    "Weather / Natural Disaster": 125.0,
}


def rule_based_disruption_category(title: str, body: str) -> str:
    text_lower = f"{title or ''} {body or ''}".lower()
    scores: dict[str, int] = {}
    for category, keywords in CATEGORY_RULES.items():
        hit = sum(1 for kw in keywords if kw in text_lower)
        if hit:
            scores[category] = hit
    if not scores:
        return NORMAL_LABEL
    return max(scores, key=scores.get)


def apply_rule_labels_df(df):
    out = df.copy()

    def row_category(r):
        return rule_based_disruption_category(
            str(r.get("article_title", "")),
            str(r.get("event_text_segment", "")),
        )

    out["rule_disruption_category"] = out.apply(row_category, axis=1)
    out["manual_is_disruption"] = (out["rule_disruption_category"] != NORMAL_LABEL).astype(int)
    out["manual_impact_score"] = out["rule_disruption_category"].map(
        lambda c: float(IMPACT_HEURISTIC_BY_CATEGORY.get(c, 0.0))
    )
    return out
