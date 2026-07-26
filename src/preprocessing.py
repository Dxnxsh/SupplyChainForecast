"""Location entity extraction for the live geocoding step (rebuild of the broken Phase 3.2
placeholder). Uses spaCy's small English model (GPE/LOC entities) — fully offline, no network
call and no LLM, matching scripts/ingest_live.py's self-enforced LLM-free constraint.
"""

from __future__ import annotations

import spacy

NER_MAX_CHARS = 1000
_NLP = None


def _get_nlp():
    global _NLP
    if _NLP is None:
        _NLP = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer", "tagger"])
    return _NLP


def extract_locations_batch(texts: list[str]) -> list[list[tuple[str, str]]]:
    """For each input text, return [(entity_text, spacy_label), ...] for GPE/LOC entities,
    in document order. Empty list if none found."""
    nlp = _get_nlp()
    truncated = [(t or "")[:NER_MAX_CHARS] for t in texts]
    return [
        [(ent.text, ent.label_) for ent in doc.ents if ent.label_ in ("GPE", "LOC")]
        for doc in nlp.pipe(truncated, batch_size=32)
    ]
