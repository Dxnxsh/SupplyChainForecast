#!/usr/bin/env python3
"""Regression check for title-driven disruption detection."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.preprocessing import detect_potential_events
from src.filter_events import has_supply_chain_context


TITLE = "Germany news: Lufthansa pilots back strike action"
TEXT = "Short paragraph about pilots and unions"


def main():
    potential_events = detect_potential_events(TEXT, TITLE)
    passes_filter = has_supply_chain_context(TEXT, TITLE) or bool(potential_events)

    print(f"Potential events: {potential_events}")
    print(f"Has supply chain context: {has_supply_chain_context(TEXT, TITLE)}")
    print(f"Passes filter: {passes_filter}")

    if "Labor_Issue" not in potential_events:
        raise SystemExit("Title-driven strike did not produce Labor_Issue")

    if not passes_filter:
        raise SystemExit("Title-driven strike was still filtered out")

    print("Title-driven detection regression passed.")


if __name__ == "__main__":
    main()