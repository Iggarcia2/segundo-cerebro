"""Indice reconstruible SQLite (lexical + metadatos + grafo) en Indices/."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.entity_resolver import normalize_text
from scripts.markdown_io import iter_consolidated_notes, parse_markdown_note
from scripts.schema_loader import get_workspace_root, load_schema


class VaultIndex:
    """Construye y consulta Indices/brain_index.sqlite desde los archivos Markdown."""

    def __init__(self, root: Path | None = None, db_path: Path | None = None) -> None:
        self.root = get_workspace_root(root)
        self.schema = load_schema(self.root)
        self.db_path = db_path or (self.root / "Indices" / "brain_index.sqlite")

    def _connect(self, *, memory: bool = False) -> sqlite3.Connection:
        target = ":memory:" if memory else str(self.db_path)
        if not memory:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(target)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self, conn: sqlite3.Connection) -> bool:
        """Inicializa tablas e intenta crear FTS5; devuelve si FTS5 esta disponible."""
        conn.executescript(
            """
            DROP TABLE IF EXISTS edges;
            DROP TABLE IF EXISTS nodes;
            DROP TABLE IF EXISTS meta;
            DROP TABLE IF EXISTS nodes_fts;

            CREATE TABLE meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE nodes (
                id TEXT PRIMARY KEY,
                tipo TEXT NOT NULL,
                subtipo TEXT,
                titulo TEXT NOT NULL,
                titulo_norm TEXT NOT NULL,
                aliases_json TEXT NOT NULL,
                aliases_norm TEXT NOT NULL,
                ambito TEXT NOT NULL,
                estado TEXT NOT NULL,
                evidencia TEXT NOT NULL,
                fuente TEXT NOT NULL,
                confianza TEXT NOT NULL,
                registrado_el TEXT NOT NULL,
                ocurrio_el TEXT,
                tags_json TEXT NOT NULL,
                path TEXT NOT NULL,
                body TEXT NOT NULL,
                body_norm TEXT NOT NULL
            );

            CREATE TABLE edges (
                rel_id TEXT NOT NULL,
                src_id TEXT NOT NULL,
                predicado TEXT NOT NULL,
                inversa TEXT NOT NULL,
                dst_id TEXT NOT NULL,
                dst_titulo TEXT NOT NULL,
                evidencia TEXT NOT NULL,
                fuente TEXT NOT NULL,
                registrado_el TEXT NOT NULL,
                ocurrio_el TEXT,
                vigente_desde TEXT,
                vigente_hasta TEXT,
                vigencia TEXT NOT NULL,
                nota TEXT
            );

            CREATE INDEX idx_nodes_tipo ON nodes(tipo);
            CREATE INDEX idx_nodes_ambito ON nodes(ambito);
            CREATE INDEX idx_edges_src ON edges(src_id);
            CREATE INDEX idx_edges_dst ON edges(dst_id);
            CREATE INDEX idx_edges_pred ON edges(predicado);
            """
        )
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE nodes_fts USING fts5(id UNINDEXED, titulo_norm, aliases_norm, tags_norm, body_norm);"
            )
            return True
        except sqlite3.OperationalError:
            return False

    def populate_connection(self, conn: sqlite3.Connection) -> dict[str, Any]:
        """Puebla una conexion SQLite desde Conocimiento/ e Historia/."""
        has_fts = self._init_schema(conn)
        predicates_cfg = self.schema["predicates"]
        nodes_count = 0
        edges_count = 0

        for note_path in iter_consolidated_notes(self.root):
            try:
                doc = parse_markdown_note(note_path)
            except ValueError:
                continue
            fm = doc.frontmatter
            node_id = str(fm.get("id", ""))
            if not node_id:
                continue
            titulo = str(fm.get("titulo", ""))
            aliases = [str(a) for a in (fm.get("aliases") or [])]
            tags = [str(t) for t in (fm.get("tags") or [])]
            titulo_norm = normalize_text(titulo)
            aliases_norm = " ".join(normalize_text(a) for a in aliases)
            tags_norm = " ".join(normalize_text(t) for t in tags)
            body_norm = normalize_text(doc.body)
            rel_path = str(note_path.relative_to(self.root)).replace("\\", "/")

            conn.execute(
                """
                INSERT INTO nodes (
                    id, tipo, subtipo, titulo, titulo_norm, aliases_json, aliases_norm,
                    ambito, estado, evidencia, fuente, confianza, registrado_el, ocurrio_el,
                    tags_json, path, body, body_norm
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node_id,
                    str(fm.get("tipo", "")),
                    fm.get("subtipo"),
                    titulo,
                    titulo_norm,
                    json.dumps(aliases, ensure_ascii=False),
                    aliases_norm,
                    str(fm.get("ambito", "")),
                    str(fm.get("estado", "")),
                    str(fm.get("evidencia", "")),
                    str(fm.get("fuente", "")),
                    str(fm.get("confianza", "")),
                    str(fm.get("registrado_el", "")),
                    fm.get("ocurrio_el"),
                    json.dumps(tags, ensure_ascii=False),
                    rel_path,
                    doc.body,
                    body_norm,
                ),
            )
            if has_fts:
                conn.execute(
                    "INSERT INTO nodes_fts (id, titulo_norm, aliases_norm, tags_norm, body_norm) VALUES (?, ?, ?, ?, ?)",
                    (node_id, titulo_norm, aliases_norm, tags_norm, body_norm),
                )
            nodes_count += 1

            for rel in fm.get("relaciones") or []:
                if not isinstance(rel, dict):
                    continue
                pred = str(rel.get("predicado", ""))
                inversa = predicates_cfg.get(pred, {}).get("inversa", pred)
                conn.execute(
                    """
                    INSERT INTO edges (
                        rel_id, src_id, predicado, inversa, dst_id, dst_titulo,
                        evidencia, fuente, registrado_el, ocurrio_el,
                        vigente_desde, vigente_hasta, vigencia, nota
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(rel.get("id", "")),
                        node_id,
                        pred,
                        inversa,
                        str(rel.get("destino_id", "")),
                        str(rel.get("destino", "")).strip("[]"),
                        str(rel.get("evidencia", "")),
                        str(rel.get("fuente", "")),
                        str(rel.get("registrado_el", "")),
                        rel.get("ocurrio_el"),
                        rel.get("vigente_desde"),
                        rel.get("vigente_hasta"),
                        str(rel.get("vigencia", "desconocida")),
                        rel.get("nota"),
                    ),
                )
                edges_count += 1

        built_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        conn.execute("INSERT INTO meta (key, value) VALUES ('built_at', ?)", (built_at,))
        conn.execute("INSERT INTO meta (key, value) VALUES ('has_fts5', ?)", (str(has_fts).lower(),))
        conn.commit()
        return {
            "db_path": str(self.db_path),
            "nodes_indexed": nodes_count,
            "edges_indexed": edges_count,
            "has_fts5": has_fts,
            "built_at": built_at,
        }

    def rebuild(self) -> dict[str, Any]:
        """Reconstruye el indice SQLite en Indices/brain_index.sqlite."""
        conn = self._connect(memory=False)
        try:
            return self.populate_connection(conn)
        finally:
            conn.close()

    def open_for_read(self) -> sqlite3.Connection:
        """Abre el indice existente o construye uno efimero en memoria sin escribir en disco."""
        if self.db_path.exists():
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            return conn
        conn = self._connect(memory=True)
        self.populate_connection(conn)
        return conn
