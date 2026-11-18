"""Carga y helpers del esquema de conocimiento V1.0."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

NODE_ID_RE = re.compile(r"^(per|org|pro|con|nec|rec|doc|acc|dec|eve)-(\d{6})$")
REL_ID_RE = re.compile(r"^rel-(\d{6})$")
WIKILINK_RE = re.compile(r"^\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:\d{2}|Z))?$")


def get_workspace_root(start: Path | None = None) -> Path:
    """Devuelve la raiz del workspace buscando Sistema/Esquemas/modelo_v1.json."""
    candidate = (start or Path(__file__).resolve().parent.parent).resolve()
    if (candidate / "Sistema" / "Esquemas" / "modelo_v1.json").exists():
        return candidate
    for parent in candidate.parents:
        if (parent / "Sistema" / "Esquemas" / "modelo_v1.json").exists():
            return parent
    return candidate


def load_schema(root: Path | None = None) -> dict[str, Any]:
    """Carga el archivo JSON del modelo V1.0."""
    ws = get_workspace_root(root)
    schema_path = ws / "Sistema" / "Esquemas" / "modelo_v1.json"
    with schema_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def is_valid_iso_date(value: Any) -> bool:
    """Verifica fechas YYYY-MM-DD o ISO-8601 completas."""
    if isinstance(value, (date, datetime)):
        return True
    if not isinstance(value, str) or not ISO_DATE_RE.match(value):
        return False
    try:
        if "T" in value:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            date.fromisoformat(value)
        return True
    except ValueError:
        return False


def extract_wikilink_target(value: Any) -> str | None:
    """Extrae el titulo destino de un string [[Titulo]] o devuelve None."""
    if not isinstance(value, str):
        return None
    match = WIKILINK_RE.match(value.strip())
    return match.group(1).strip() if match else None
