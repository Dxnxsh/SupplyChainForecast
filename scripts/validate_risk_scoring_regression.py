#!/usr/bin/env python3
"""Quick regression check for risk scoring false positives."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.risk_scoring import calculate_risk_score


FALSE_POSITIVE_CASE = {
    "article_title": "Shakespeare in war: bard’s ‘existential’ theatre takes hold in Ukraine",
    "event_text_segment": (
        "The Ukrainian Shakespeare festival in the city of Ivano-Frankivsk did not open with a play. "
        "Another kind of performance was staged on the steps of the theatre, one that did not deal with "
        "sad stories of the death of kings but with tragedy unfolding in real life."
    ),
    "potential_event_types": ["Labor_Issue", "Industrial_Accident"],
}


TRUE_POSITIVE_CASE = {
    "article_title": "India: 35 killed in Telangana pharmaceutical factory blast",
    "event_text_segment": (
        "An explosion at a pharmaceutical factory near Hyderabad has left at least 35 people dead and "
        "dozens more injured. India's pharmaceutical industry is a major global supplier of generic medicines and vaccines."
    ),
    "potential_event_types": ["Industrial_Accident"],
}


def main():
    false_positive_score = calculate_risk_score(FALSE_POSITIVE_CASE)
    true_positive_score = calculate_risk_score(TRUE_POSITIVE_CASE)

    print(f"False positive score: {false_positive_score}")
    print(f"True positive score: {true_positive_score}")

    if false_positive_score != 0:
        raise SystemExit("False positive still scores above zero")

    if true_positive_score <= 0:
        raise SystemExit("True positive no longer scores as a disruption")

    print("Regression check passed.")


if __name__ == "__main__":
    main()