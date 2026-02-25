"""spaCy NER: extract PERSON/ORG/GPE entities → Concept nodes via outbox.

Model: en_core_web_sm (deterministic, no LLM).
Loaded lazily; graceful degradation if model unavailable.

Entity types extracted:
  PERSON — people, including fictional
  ORG    — organisations, companies, agencies
  GPE    — countries, cities, states
"""
from __future__ import annotations

import functools

import structlog

log = structlog.get_logger()

ENTITY_LABELS = {"PERSON", "ORG", "GPE"}


@functools.lru_cache(maxsize=1)
def _get_nlp():
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        log.info("ner_model_loaded", model="en_core_web_sm")
        return nlp
    except Exception as exc:
        log.warning("ner_model_unavailable", error=str(exc))
        return None


def extract_entities(text: str) -> list[dict]:
    """Return list of {text, label} dicts for PERSON/ORG/GPE entities.

    Returns empty list if model unavailable.
    """
    nlp = _get_nlp()
    if nlp is None:
        return []
    try:
        doc = nlp(text[:10_000])  # cap to avoid OOM on huge chunks
        seen: set[tuple[str, str]] = set()
        entities = []
        for ent in doc.ents:
            if ent.label_ in ENTITY_LABELS:
                key = (ent.text.strip(), ent.label_)
                if key not in seen:
                    seen.add(key)
                    entities.append({"text": ent.text.strip(), "label": ent.label_})
        return entities
    except Exception as exc:
        log.error("ner_extract_failed", error=str(exc))
        return []


def build_concept_outbox_events(
    doc_id: str,
    chunk_id: str,
    entities: list[dict],
    ingested_at: str,
) -> list[dict]:
    """Convert extracted entities into outbox event payloads.

    Each event:
      event_type: 'concept_added'
      payload: {doc_id, chunk_id, entity_text, entity_label, valid_at}
    """
    return [
        {
            "event_type": "concept_added",
            "payload": {
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "entity_text": ent["text"],
                "entity_label": ent["label"],
                "valid_at": ingested_at,
            },
        }
        for ent in entities
    ]
