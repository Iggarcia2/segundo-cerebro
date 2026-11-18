"""Resolucion de entidades por ID, nombre/aliases, tipo, proyecto y contexto."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.markdown_io import NoteDocument, iter_consolidated_notes, parse_markdown_note
from scripts.schema_loader import get_workspace_root


def normalize_text(value: str) -> str:
    """Normaliza texto en minusculas, sin tildes y espacios colapsados."""
    nfkd = unicodedata.normalize("NFKD", value)
    without_accents = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return " ".join(without_accents.lower().strip().split())


@dataclass
class EntityCandidate:
    """Candidato encontrado durante la resolucion."""

    node_id: str
    tipo: str
    subtipo: str | None
    titulo: str
    aliases: list[str]
    ambito: str
    path: Path
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class ResolutionResult:
    """Resultado estructurado de resolucion sin fusion silenciosa ante ambiguedad."""

    query: str
    status: str  # exact_id | unique_match | ambiguous | not_found
    candidates: list[EntityCandidate] = field(default_factory=list)


class EntityResolver:
    """Resuelve menciones de entidades contra notas consolidadas de la boveda."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = get_workspace_root(root)
        self.notes: list[NoteDocument] = []
        self.by_id: dict[str, NoteDocument] = {}
        self.reload()

    def reload(self) -> None:
        """Recarga notas consolidadas desde disco."""
        self.notes = []
        self.by_id = {}
        for path in iter_consolidated_notes(self.root):
            try:
                doc = parse_markdown_note(path)
            except ValueError:
                continue
            self.notes.append(doc)
            node_id = doc.frontmatter.get("id")
            if isinstance(node_id, str):
                self.by_id[node_id] = doc

    def _context_bonus(
        self,
        doc: NoteDocument,
        *,
        proyecto: str | None = None,
        contexto: str | None = None,
    ) -> tuple[float, list[str]]:
        """Calcula afinidad contextual usando ambito, relaciones y cuerpo."""
        bonus = 0.0
        reasons: list[str] = []
        fm = doc.frontmatter
        rels = fm.get("relaciones") or []

        if proyecto:
            proj_norm = normalize_text(proyecto)
            for rel in rels:
                if not isinstance(rel, dict):
                    continue
                dest = normalize_text(str(rel.get("destino", "")))
                dest_id = normalize_text(str(rel.get("destino_id", "")))
                if proj_norm in dest or proj_norm == dest_id:
                    bonus += 0.35
                    reasons.append(f"vinculado al proyecto '{proyecto}'")
                    break

        if contexto:
            ctx_norm = normalize_text(contexto)
            ambito = normalize_text(str(fm.get("ambito", "")))
            if ctx_norm == ambito:
                bonus += 0.15
                reasons.append(f"ambito '{ambito}'")
            for rel in rels:
                if not isinstance(rel, dict):
                    continue
                dest = normalize_text(str(rel.get("destino", "")))
                nota = normalize_text(str(rel.get("nota") or ""))
                if ctx_norm in dest or ctx_norm in nota:
                    bonus += 0.25
                    reasons.append(f"coincide contexto en relacion '{rel.get('predicado')}'")
                    break
            if ctx_norm in normalize_text(doc.body):
                bonus += 0.15
                reasons.append("coincide contexto en cuerpo de nota")

        return bonus, reasons

    def resolve(
        self,
        query: str,
        *,
        tipo: str | None = None,
        proyecto: str | None = None,
        contexto: str | None = None,
    ) -> ResolutionResult:
        """Resuelve un ID, titulo o alias aplicando desambiguacion por contexto."""
        q_clean = query.strip()
        if not q_clean:
            return ResolutionResult(query=query, status="not_found")

        if q_clean in self.by_id:
            doc = self.by_id[q_clean]
            fm = doc.frontmatter
            if tipo and fm.get("tipo") != tipo:
                return ResolutionResult(query=query, status="not_found")
            return ResolutionResult(
                query=query,
                status="exact_id",
                candidates=[
                    EntityCandidate(
                        node_id=str(fm.get("id")),
                        tipo=str(fm.get("tipo")),
                        subtipo=fm.get("subtipo"),
                        titulo=str(fm.get("titulo")),
                        aliases=list(fm.get("aliases") or []),
                        ambito=str(fm.get("ambito", "")),
                        path=doc.path,
                        score=1.0,
                        reasons=["coincidencia exacta por id"],
                    )
                ],
            )

        q_norm = normalize_text(q_clean)
        matches: list[EntityCandidate] = []
        for doc in self.notes:
            fm = doc.frontmatter
            if tipo and fm.get("tipo") != tipo:
                continue

            titulo = str(fm.get("titulo", ""))
            aliases = [str(a) for a in (fm.get("aliases") or [])]
            base_score = 0.0
            reasons: list[str] = []

            if normalize_text(titulo) == q_norm:
                base_score = 0.65
                reasons.append("titulo exacto")
            elif any(normalize_text(alias) == q_norm for alias in aliases):
                base_score = 0.60
                reasons.append("alias exacto")
            elif q_norm in normalize_text(titulo) or any(
                q_norm in normalize_text(alias) for alias in aliases
            ):
                base_score = 0.40
                reasons.append("coincidencia parcial en titulo/alias")
            else:
                continue

            bonus, ctx_reasons = self._context_bonus(doc, proyecto=proyecto, contexto=contexto)
            reasons.extend(ctx_reasons)
            matches.append(
                EntityCandidate(
                    node_id=str(fm.get("id", "")),
                    tipo=str(fm.get("tipo", "")),
                    subtipo=fm.get("subtipo"),
                    titulo=titulo,
                    aliases=aliases,
                    ambito=str(fm.get("ambito", "")),
                    path=doc.path,
                    score=round(min(base_score + bonus, 1.0), 3),
                    reasons=reasons,
                )
            )

        if not matches:
            return ResolutionResult(query=query, status="not_found")

        matches.sort(key=lambda c: (-c.score, c.node_id))
        if len(matches) == 1:
            return ResolutionResult(query=query, status="unique_match", candidates=matches)

        top_score = matches[0].score
        second_score = matches[1].score
        if round(top_score - second_score, 6) >= 0.15 and (proyecto or contexto):
            return ResolutionResult(query=query, status="unique_match", candidates=matches)
        return ResolutionResult(query=query, status="ambiguous", candidates=matches)
