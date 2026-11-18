"""Generacion de IDs estables independientes del nombre o ruta de la nota."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.markdown_io import iter_consolidated_notes, parse_markdown_note
from scripts.schema_loader import NODE_ID_RE, REL_ID_RE, get_workspace_root, load_schema


class IdManager:
    """Administra IDs secuenciales estables por prefijo y para relaciones."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = get_workspace_root(root)
        self.schema = load_schema(self.root)
        self.registry_path = self.root / "Sistema" / "id_registry.json"

    def scan_existing_max_ids(self) -> dict[str, int]:
        """Escanea las notas consolidadas para obtener el mayor contador real por prefijo."""
        counters: dict[str, int] = {
            cfg["prefix"]: 0 for cfg in self.schema["classes"].values()
        }
        counters["rel"] = 0

        for note_path in iter_consolidated_notes(self.root):
            try:
                doc = parse_markdown_note(note_path)
            except ValueError:
                continue
            node_id = doc.frontmatter.get("id")
            if isinstance(node_id, str):
                match = NODE_ID_RE.match(node_id)
                if match:
                    prefix, num = match.group(1), int(match.group(2))
                    counters[prefix] = max(counters.get(prefix, 0), num)
            rels = doc.frontmatter.get("relaciones")
            if isinstance(rels, list):
                for rel in rels:
                    if isinstance(rel, dict) and isinstance(rel.get("id"), str):
                        rmatch = REL_ID_RE.match(rel["id"])
                        if rmatch:
                            counters["rel"] = max(counters["rel"], int(rmatch.group(1)))
        return counters

    def load_counters(self) -> dict[str, int]:
        """Carga contadores combinando id_registry.json y escaneo real de la boveda."""
        scanned = self.scan_existing_max_ids()
        if self.registry_path.exists():
            with self.registry_path.open("r", encoding="utf-8") as fh:
                stored: dict[str, Any] = json.load(fh)
            for prefix, val in stored.items():
                if isinstance(val, int):
                    scanned[prefix] = max(scanned.get(prefix, 0), val)
        return scanned

    def save_counters(self, counters: dict[str, int]) -> None:
        """Guarda contadores actualizados en Sistema/id_registry.json."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with self.registry_path.open("w", encoding="utf-8", newline="\n") as fh:
            json.dump(dict(sorted(counters.items())), fh, indent=2, ensure_ascii=False)
            fh.write("\n")

    def rebuild_registry(self) -> dict[str, int]:
        """Reconstruye id_registry.json estrictamente desde las notas existentes."""
        counters = self.scan_existing_max_ids()
        self.save_counters(counters)
        return counters

    def peek_next_node_id(self, tipo: str) -> str:
        """Calcula el siguiente ID disponible sin modificar archivos (modo lectura)."""
        if tipo not in self.schema["classes"]:
            raise ValueError(f"Tipo de nodo desconocido: '{tipo}'")
        prefix = self.schema["classes"][tipo]["prefix"]
        counters = self.load_counters()
        return f"{prefix}-{counters.get(prefix, 0) + 1:06d}"

    def allocate_node_id(self, tipo: str, *, persist: bool = True) -> str:
        """Asigna un nuevo ID estable para una clase de nodo."""
        if tipo not in self.schema["classes"]:
            raise ValueError(f"Tipo de nodo desconocido: '{tipo}'")
        prefix = self.schema["classes"][tipo]["prefix"]
        counters = self.load_counters()
        next_num = counters.get(prefix, 0) + 1
        counters[prefix] = next_num
        if persist:
            self.save_counters(counters)
        return f"{prefix}-{next_num:06d}"

    def allocate_relation_id(self, *, persist: bool = True) -> str:
        """Asigna un nuevo ID estable de relacion."""
        counters = self.load_counters()
        next_num = counters.get("rel", 0) + 1
        counters["rel"] = next_num
        if persist:
            self.save_counters(counters)
        return f"rel-{next_num:06d}"
