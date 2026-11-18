"""Lectura y escritura segura de notas Markdown con YAML frontmatter."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

CONSOLIDATED_FOLDERS = ("Conocimiento", "Historia")


@dataclass
class NoteDocument:
    """Representa una nota Markdown con frontmatter y cuerpo."""

    path: Path
    frontmatter: dict[str, Any]
    body: str
    raw_yaml: str


def _normalize_yaml_dates(obj: Any) -> Any:
    """Convierte objetos date/datetime cargados por PyYAML en cadenas ISO."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, list):
        return [_normalize_yaml_dates(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _normalize_yaml_dates(v) for k, v in obj.items()}
    return obj


def parse_markdown_note(path: Path) -> NoteDocument:
    """Lee un archivo Markdown UTF-8 y separa su frontmatter YAML."""
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"Falta delimitador inicial '---' de frontmatter en {path}")

    closing_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            closing_idx = idx
            break
    if closing_idx is None:
        raise ValueError(f"Falta delimitador final '---' de frontmatter en {path}")

    raw_yaml = "".join(lines[1:closing_idx])
    body = "".join(lines[closing_idx + 1 :])
    data = yaml.safe_load(raw_yaml)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"El frontmatter YAML debe ser un diccionario en {path}")

    normalized = _normalize_yaml_dates(data)
    return NoteDocument(path=path, frontmatter=normalized, body=body, raw_yaml=raw_yaml)


def dump_markdown_note(frontmatter: dict[str, Any], body: str) -> str:
    """Serializa frontmatter YAML legible para Obsidian junto al cuerpo Markdown."""
    dumped = yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=120,
    )
    clean_body = body.lstrip("\r\n")
    if clean_body:
        return f"---\n{dumped}---\n\n{clean_body.rstrip()}\n"
    return f"---\n{dumped}---\n"


def atomic_write_text(path: Path, text: str, *, overwrite: bool = False) -> None:
    """Escribe un archivo de forma atomica respetando overwrite=False."""
    if path.exists() and not overwrite:
        raise FileExistsError(f"El archivo ya existe y no se permite sobrescribirlo: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp_", suffix=".md", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except Exception:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise


def iter_consolidated_notes(root: Path) -> list[Path]:
    """Lista todas las notas .md dentro de Conocimiento/ e Historia/."""
    notes: list[Path] = []
    for folder_name in CONSOLIDATED_FOLDERS:
        folder = root / folder_name
        if folder.exists():
            notes.extend(sorted(folder.rglob("*.md")))
    return notes
