"""Loads the versioned, allow-listed checklist template registry."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.schemas.coverage import ChecklistTemplate

TEMPLATES_PATH = Path(__file__).resolve().parent.parent / "templates" / "symptom_templates.json"


@lru_cache
def load_registry() -> dict[str, ChecklistTemplate]:
    data = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
    templates = [ChecklistTemplate.model_validate(t) for t in data["templates"]]
    registry = {t.template_id: t for t in templates}
    if len(registry) != len(templates):
        raise ValueError("Duplicate template IDs in symptom_templates.json")
    return registry


def registry_notice() -> str:
    return json.loads(TEMPLATES_PATH.read_text(encoding="utf-8")).get("notice", "")


def get_templates(template_ids: list[str] | None = None) -> list[ChecklistTemplate]:
    """Return the requested templates (all when none requested). Unknown IDs raise KeyError."""
    registry = load_registry()
    if not template_ids:
        return list(registry.values())
    unknown = [t for t in template_ids if t not in registry]
    if unknown:
        raise KeyError(", ".join(unknown))
    return [registry[t] for t in dict.fromkeys(template_ids)]
