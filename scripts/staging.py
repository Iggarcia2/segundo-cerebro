"""Bandeja provisional (Memoria-Pendiente) y extraccion selectiva idempotente."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from scripts.entity_resolver import EntityResolver, normalize_text
from scripts.markdown_io import iter_consolidated_notes, parse_markdown_note
from scripts.schema_loader import get_workspace_root, load_schema

VALID_PROPOSAL_STATES = (
    "pendiente",
    "requiere_aclaracion",
    "aprobada",
    "consolidada",
    "descartada",
)

TRIVIAL_MESSAGES = {
    "hola",
    "buen dia",
    "buenos dias",
    "buenas tardes",
    "buenas noches",
    "gracias",
    "muchas gracias",
    "ok",
    "dale",
    "perfecto",
    "chau",
    "hasta luego",
}

ISO_DATE_INLINE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
CAPABILITY_RE = re.compile(
    r"^(?P<persona>[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]+){0,3})\s+"
    r"(?:sabe|domina|hace|realiza)\s+(?P<cap>[^.;,\n]+)",
    re.IGNORECASE,
)
CHANGE_WORK_RE = re.compile(
    r"^(?P<persona>[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]+){0,3})\s+"
    r"(?:dej[oó]\s+de\s+trabajar\s+en|dej[oó])\s+(?P<old_org>[^.;,\n]+?)\s+"
    r"y\s+(?:ahora\s+)?trabaja\s+en\s+(?P<new_org>[^.;,\n]+)",
    re.IGNORECASE,
)
WORK_RE = re.compile(
    r"^(?P<persona>[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]+){0,3})\s+"
    r"trabaja\s+en\s+(?P<org>[^.;,\n]+)",
    re.IGNORECASE,
)
NEED_RE = re.compile(
    r"^(?:necesitamos|se\s+requiere|requiere|falta)\s+(?P<need>[^.;\n]+)",
    re.IGNORECASE,
)
DECISION_RE = re.compile(
    r"^(?:decisi[oó]n|se\s+decidi[oó])\s*[:\-]?\s*(?P<dec>[^.\n]+)",
    re.IGNORECASE,
)
EVENT_RE = re.compile(
    r"^(?:evento|hito)\s*[:\-]?\s*(?P<eve>[^.\n]+)",
    re.IGNORECASE,
)
LEARNING_RE = re.compile(
    r"^(?:aprendizaje|experiencia)\s*[:\-]?\s*(?P<learn>[^.\n]+)",
    re.IGNORECASE,
)
QUESTION_RE = re.compile(
    r"^(?:pregunta\s*[:\-]\s*(?P<q>.+)|(?P<qm>¿[^?]+\?))$",
    re.IGNORECASE,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _today_iso() -> str:
    return date.today().isoformat()


def compute_idempotency_key(payload: dict[str, Any]) -> str:
    """Genera una huella SHA-256 estable para evitar propuestas duplicadas."""
    canonical_parts = {
        "op_type": payload.get("op_type", ""),
        "target_tipo": payload.get("target_tipo", ""),
        "target_titulo": normalize_text(str(payload.get("target_titulo", ""))),
        "predicado": payload.get("predicado", ""),
        "destino_titulo": normalize_text(str(payload.get("destino_titulo", ""))),
        "old_destino_titulo": normalize_text(str(payload.get("old_destino_titulo", ""))),
        "ocurrio_el": payload.get("ocurrio_el"),
        "fuente": normalize_text(str(payload.get("fuente", ""))),
    }
    raw = json.dumps(canonical_parts, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class IngestSummary:
    """Resumen de ejecucion de ingesta hacia Memoria-Pendiente."""

    created_proposals: list[str] = field(default_factory=list)
    created_questions: list[str] = field(default_factory=list)
    skipped_duplicates: int = 0
    ignored_trivial: int = 0


class StagingManager:
    """Administra propuestas y preguntas provisionales dentro de Memoria-Pendiente/."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = get_workspace_root(root)
        self.schema = load_schema(self.root)
        self.staging_dir = (self.root / "Memoria-Pendiente").resolve()
        self.propuestas_dir = self.staging_dir / "Propuestas"
        self.preguntas_dir = self.staging_dir / "Preguntas"
        self.auditoria_dir = self.staging_dir / "Auditoria"
        self.propuestas_dir.mkdir(parents=True, exist_ok=True)
        self.preguntas_dir.mkdir(parents=True, exist_ok=True)
        self.auditoria_dir.mkdir(parents=True, exist_ok=True)

    def _assert_in_staging(self, path: Path) -> None:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.staging_dir):
            raise PermissionError(
                f"Escritura provisional bloqueada fuera de Memoria-Pendiente/: {resolved}"
            )

    def _next_sequence_id(self, folder: Path, prefix: str) -> str:
        max_num = 0
        pattern = re.compile(rf"^{re.escape(prefix)}-(\d{{6}})\.ya?ml$")
        for p in folder.iterdir():
            m = pattern.match(p.name)
            if m:
                max_num = max(max_num, int(m.group(1)))
        return f"{prefix}-{max_num + 1:06d}"

    def _save_yaml_file(self, path: Path, data: dict[str, Any]) -> None:
        self._assert_in_staging(path)
        text = yaml.safe_dump(
            data,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=120,
        )
        path.write_text(text, encoding="utf-8", newline="\n")

    def _load_yaml_file(self, path: Path) -> dict[str, Any]:
        self._assert_in_staging(path)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Archivo de staging invalido: {path}")
        return data

    def list_proposals(self, estado: str | None = None) -> list[dict[str, Any]]:
        """Lista propuestas en Memoria-Pendiente/Propuestas filtrando opcionalmente por estado."""
        if estado is not None and estado not in VALID_PROPOSAL_STATES:
            raise ValueError(f"Estado de propuesta invalido: '{estado}'")
        items: list[dict[str, Any]] = []
        for path in sorted(self.propuestas_dir.glob("prop-*.yaml")):
            data = self._load_yaml_file(path)
            if estado is None or data.get("estado") == estado:
                items.append(data)
        return items

    def list_questions(self) -> list[dict[str, Any]]:
        """Lista preguntas diferidas en Memoria-Pendiente/Preguntas."""
        items: list[dict[str, Any]] = []
        for path in sorted(self.preguntas_dir.glob("preg-*.yaml")):
            items.append(self._load_yaml_file(path))
        return items

    def get_proposal(self, prop_id: str) -> dict[str, Any]:
        path = self.propuestas_dir / f"{prop_id}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Propuesta no encontrada: {prop_id}")
        return self._load_yaml_file(path)

    def save_proposal(self, data: dict[str, Any]) -> None:
        prop_id = data["id"]
        path = self.propuestas_dir / f"{prop_id}.yaml"
        self._save_yaml_file(path, data)

    def _find_existing_by_key(self, key: str) -> dict[str, Any] | None:
        for prop in self.list_proposals():
            if prop.get("huella_idempotencia") == key:
                return prop
        return None

    def _relation_exists_in_vault(
        self,
        source_titulo: str,
        predicado: str,
        destino_titulo: str,
    ) -> bool:
        src_norm = normalize_text(source_titulo)
        dst_norm = normalize_text(destino_titulo)
        for path in iter_consolidated_notes(self.root):
            try:
                doc = parse_markdown_note(path)
            except ValueError:
                continue
            fm = doc.frontmatter
            names = {normalize_text(str(fm.get("titulo", "")))}
            names.update(normalize_text(str(a)) for a in (fm.get("aliases") or []))
            if src_norm not in names:
                continue
            for rel in fm.get("relaciones") or []:
                if not isinstance(rel, dict):
                    continue
                if rel.get("predicado") != predicado:
                    continue
                if rel.get("vigencia") == "historica":
                    continue
                rel_dst = normalize_text(str(rel.get("destino", "")).strip("[]"))
                if rel_dst == dst_norm:
                    return True
        return False

    def _check_ambiguity_or_conflict(
        self,
        candidate: dict[str, Any],
        resolver: EntityResolver,
    ) -> tuple[str, list[str]]:
        """Detecta homonimos ambiguos o contradicciones con relaciones vigentes."""
        notes: list[str] = []
        target_titulo = str(candidate.get("target_titulo", ""))
        target_tipo = candidate.get("target_tipo")
        contexto = candidate.get("contexto")
        proyecto = candidate.get("proyecto")

        if target_titulo and target_tipo:
            res = resolver.resolve(
                target_titulo,
                tipo=target_tipo,
                proyecto=proyecto,
                contexto=contexto,
            )
            if res.status == "ambiguous":
                ids = ", ".join(c.node_id for c in res.candidates)
                notes.append(
                    f"Ambiguedad de identidad para '{target_titulo}' ({target_tipo}): "
                    f"candidatos [{ids}] sin fusion automatica."
                )
            elif candidate.get("op_type", "create_node") == "create_node" and res.status in (
                "exact_id",
                "unique_match",
            ):
                existing = res.candidates[0]
                notes.append(
                    f"Ya existe '{existing.titulo}' ({existing.node_id}, ambito='{existing.ambito}'); "
                    "aclarar si es la misma entidad o un homonimo independiente."
                )

            if (
                candidate.get("op_type") == "add_relation"
                and candidate.get("predicado") == "trabaja_en"
                and res.status in ("exact_id", "unique_match")
            ):
                doc = resolver.by_id[res.candidates[0].node_id]
                new_dst = normalize_text(str(candidate.get("destino_titulo", "")))
                for rel in doc.frontmatter.get("relaciones") or []:
                    if (
                        isinstance(rel, dict)
                        and rel.get("predicado") == "trabaja_en"
                        and rel.get("vigencia") == "vigente"
                    ):
                        old_dst = normalize_text(str(rel.get("destino", "")).strip("[]"))
                        if old_dst and old_dst != new_dst:
                            notes.append(
                                f"Contradiccion potencial con relacion vigente {rel.get('id')} "
                                f"({rel.get('destino')}); requiere aclarar si reemplaza la anterior."
                            )

        estado = "requiere_aclaracion" if notes else "pendiente"
        return estado, notes

    def queue_candidate(self, candidate: dict[str, Any]) -> tuple[str | None, str]:
        """Encola una propuesta o pregunta en Memoria-Pendiente evitando duplicados."""
        kind = candidate.get("kind", "proposal")
        if kind == "question":
            q_text = str(candidate.get("texto", "")).strip()
            q_norm = normalize_text(q_text)
            for existing in self.list_questions():
                if normalize_text(str(existing.get("texto", ""))) == q_norm:
                    return None, "duplicate"
            preg_id = self._next_sequence_id(self.preguntas_dir, "preg")
            q_doc = {
                "id": preg_id,
                "estado": "pendiente",
                "texto": q_text,
                "fuente": candidate.get("fuente", "[[Conversación]]"),
                "registrado_el": candidate.get("registrado_el") or _today_iso(),
                "contexto": candidate.get("contexto"),
            }
            self._save_yaml_file(self.preguntas_dir / f"{preg_id}.yaml", q_doc)
            return preg_id, "created_question"

        key = compute_idempotency_key(candidate)
        if self._find_existing_by_key(key) is not None:
            return None, "duplicate"

        op_type = candidate.get("op_type", "create_node")
        if op_type == "add_relation" and self._relation_exists_in_vault(
            str(candidate.get("target_titulo", "")),
            str(candidate.get("predicado", "")),
            str(candidate.get("destino_titulo", "")),
        ):
            return None, "duplicate"

        resolver = EntityResolver(self.root)
        estado, conflict_notes = self._check_ambiguity_or_conflict(candidate, resolver)

        prop_id = self._next_sequence_id(self.propuestas_dir, "prop")
        prop_doc = {
            "id": prop_id,
            "estado": estado,
            "op_type": op_type,
            "target_tipo": candidate.get("target_tipo"),
            "target_subtipo": candidate.get("target_subtipo"),
            "target_titulo": candidate.get("target_titulo"),
            "aliases": list(candidate.get("aliases") or []),
            "ambito": candidate.get("ambito", "transversal"),
            "predicado": candidate.get("predicado"),
            "destino_tipo": candidate.get("destino_tipo"),
            "destino_subtipo": candidate.get("destino_subtipo"),
            "destino_titulo": candidate.get("destino_titulo"),
            "old_destino_titulo": candidate.get("old_destino_titulo"),
            "evidencia": candidate.get("evidencia", "reportada"),
            "confianza": candidate.get("confianza", "media"),
            "fuente": candidate.get("fuente", "[[Conversación]]"),
            "texto_fuente": candidate.get("texto_fuente", ""),
            "registrado_el": candidate.get("registrado_el") or _today_iso(),
            "ocurrio_el": candidate.get("ocurrio_el"),
            "vigencia": candidate.get("vigencia", "desconocida"),
            "contexto": candidate.get("contexto"),
            "proyecto": candidate.get("proyecto"),
            "solicitada_por_usuario": bool(candidate.get("solicitada_por_usuario", False)),
            "criterio": candidate.get("criterio"),
            "nota": candidate.get("nota"),
            "aclaraciones_pendientes": conflict_notes,
            "huella_idempotencia": key,
            "creado_en": _utc_now_iso(),
            "actualizado_en": _utc_now_iso(),
            "batch_id": None,
        }
        self.save_proposal(prop_doc)
        return prop_id, "created_proposal"

    @staticmethod
    def _infer_evidence(sentence: str) -> str:
        low = normalize_text(sentence)
        if any(tok in low for tok in ("quizas", "quiza", "creo que", "posiblemente", "tal vez")):
            return "inferida"
        return "reportada"

    @staticmethod
    def _extract_inline_date(sentence: str) -> str | None:
        m = ISO_DATE_INLINE_RE.search(sentence)
        return m.group(1) if m else None

    def extract_candidates_from_text(
        self,
        text: str,
        *,
        fuente: str,
        registrado_el: str | None = None,
        ocurrio_el: str | None = None,
        ambito: str = "transversal",
        contexto: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Extrae candidatos estructurados desde texto libre espanol de forma selectiva."""
        reg_date = registrado_el or _today_iso()
        candidates: list[dict[str, Any]] = []
        ignored_trivial = 0

        raw_chunks = [c.strip() for c in re.split(r"[\r\n]+|(?<=[.!?])\s+", text) if c.strip()]
        for chunk in raw_chunks:
            clean = chunk.strip(" .")
            if normalize_text(clean) in TRIVIAL_MESSAGES or len(clean) < 5:
                ignored_trivial += 1
                continue

            inline_date = ocurrio_el or self._extract_inline_date(chunk)
            evidencia = self._infer_evidence(chunk)

            m_q = QUESTION_RE.match(chunk)
            if m_q:
                q_text = (m_q.group("q") or m_q.group("qm") or chunk).strip()
                candidates.append(
                    {
                        "kind": "question",
                        "texto": q_text,
                        "fuente": fuente,
                        "registrado_el": reg_date,
                        "contexto": contexto,
                    }
                )
                continue

            m_chg = CHANGE_WORK_RE.match(clean)
            if m_chg:
                candidates.append(
                    {
                        "kind": "proposal",
                        "op_type": "temporal_change",
                        "target_tipo": "persona",
                        "target_subtipo": "contacto",
                        "target_titulo": m_chg.group("persona").strip(),
                        "predicado": "trabaja_en",
                        "destino_tipo": "organizacion",
                        "destino_subtipo": "empresa",
                        "destino_titulo": m_chg.group("new_org").strip(),
                        "old_destino_titulo": m_chg.group("old_org").strip(),
                        "ambito": ambito,
                        "evidencia": evidencia,
                        "fuente": fuente,
                        "texto_fuente": chunk,
                        "registrado_el": reg_date,
                        "ocurrio_el": inline_date,
                        "vigencia": "vigente",
                        "contexto": contexto,
                    }
                )
                continue

            m_cap = CAPABILITY_RE.match(clean)
            if m_cap:
                candidates.append(
                    {
                        "kind": "proposal",
                        "op_type": "add_relation",
                        "target_tipo": "persona",
                        "target_subtipo": "especialista",
                        "target_titulo": m_cap.group("persona").strip(),
                        "predicado": "tiene_capacidad",
                        "destino_tipo": "conocimiento",
                        "destino_subtipo": "capacidad",
                        "destino_titulo": m_cap.group("cap").strip().capitalize(),
                        "ambito": ambito,
                        "evidencia": evidencia,
                        "fuente": fuente,
                        "texto_fuente": chunk,
                        "registrado_el": reg_date,
                        "ocurrio_el": inline_date,
                        "vigencia": "desconocida" if inline_date is None else "vigente",
                        "contexto": contexto,
                    }
                )
                continue

            m_work = WORK_RE.match(clean)
            if m_work:
                candidates.append(
                    {
                        "kind": "proposal",
                        "op_type": "add_relation",
                        "target_tipo": "persona",
                        "target_subtipo": "contacto",
                        "target_titulo": m_work.group("persona").strip(),
                        "predicado": "trabaja_en",
                        "destino_tipo": "organizacion",
                        "destino_subtipo": "empresa",
                        "destino_titulo": m_work.group("org").strip(),
                        "ambito": ambito,
                        "evidencia": evidencia,
                        "fuente": fuente,
                        "texto_fuente": chunk,
                        "registrado_el": reg_date,
                        "ocurrio_el": inline_date,
                        "vigencia": "vigente" if inline_date else "desconocida",
                        "contexto": contexto,
                    }
                )
                continue

            m_dec = DECISION_RE.match(clean)
            if m_dec:
                candidates.append(
                    {
                        "kind": "proposal",
                        "op_type": "create_node",
                        "target_tipo": "decision",
                        "target_subtipo": "tecnica",
                        "target_titulo": m_dec.group("dec").strip(),
                        "ambito": ambito,
                        "evidencia": evidencia,
                        "fuente": fuente,
                        "texto_fuente": chunk,
                        "registrado_el": reg_date,
                        "ocurrio_el": inline_date,
                        "criterio": chunk,
                        "contexto": contexto,
                    }
                )
                continue

            m_eve = EVENT_RE.match(clean)
            if m_eve:
                candidates.append(
                    {
                        "kind": "proposal",
                        "op_type": "create_node",
                        "target_tipo": "evento",
                        "target_subtipo": "hito",
                        "target_titulo": m_eve.group("eve").strip(),
                        "ambito": ambito,
                        "evidencia": evidencia,
                        "fuente": fuente,
                        "texto_fuente": chunk,
                        "registrado_el": reg_date,
                        "ocurrio_el": inline_date,
                        "contexto": contexto,
                    }
                )
                continue

            m_learn = LEARNING_RE.match(clean)
            if m_learn:
                candidates.append(
                    {
                        "kind": "proposal",
                        "op_type": "create_node",
                        "target_tipo": "conocimiento",
                        "target_subtipo": "aprendizaje",
                        "target_titulo": m_learn.group("learn").strip(),
                        "ambito": ambito,
                        "evidencia": evidencia,
                        "fuente": fuente,
                        "texto_fuente": chunk,
                        "registrado_el": reg_date,
                        "ocurrio_el": inline_date,
                        "contexto": contexto,
                    }
                )
                continue

            m_need = NEED_RE.match(clean)
            if m_need:
                candidates.append(
                    {
                        "kind": "proposal",
                        "op_type": "create_node",
                        "target_tipo": "necesidad",
                        "target_subtipo": "tecnica",
                        "target_titulo": m_need.group("need").strip(),
                        "ambito": ambito,
                        "evidencia": evidencia,
                        "fuente": fuente,
                        "texto_fuente": chunk,
                        "registrado_el": reg_date,
                        "ocurrio_el": inline_date,
                        "contexto": contexto,
                    }
                )
                continue

        return candidates, ignored_trivial

    def ingest_text(
        self,
        text: str,
        *,
        fuente: str,
        registrado_el: str | None = None,
        ocurrio_el: str | None = None,
        ambito: str = "transversal",
        contexto: str | None = None,
    ) -> IngestSummary:
        """Extrae candidatos del texto y los guarda solo en Memoria-Pendiente/."""
        candidates, ignored = self.extract_candidates_from_text(
            text,
            fuente=fuente,
            registrado_el=registrado_el,
            ocurrio_el=ocurrio_el,
            ambito=ambito,
            contexto=contexto,
        )
        summary = IngestSummary(ignored_trivial=ignored)
        for cand in candidates:
            item_id, status = self.queue_candidate(cand)
            if status == "created_proposal" and item_id:
                summary.created_proposals.append(item_id)
            elif status == "created_question" and item_id:
                summary.created_questions.append(item_id)
            elif status == "duplicate":
                summary.skipped_duplicates += 1
        return summary

    def approve_proposal(self, prop_id: str) -> dict[str, Any]:
        """Aprueba una propuesta especifica sin alterar ninguna otra."""
        prop = self.get_proposal(prop_id)
        if prop["estado"] == "consolidada":
            raise ValueError(f"La propuesta '{prop_id}' ya fue consolidada.")
        if prop["estado"] == "descartada":
            raise ValueError(f"La propuesta '{prop_id}' fue descartada y no puede aprobarse directamente.")
        prop["estado"] = "aprobada"
        prop["actualizado_en"] = _utc_now_iso()
        self.save_proposal(prop)
        return prop

    def discard_proposal(self, prop_id: str, *, reason: str | None = None) -> dict[str, Any]:
        """Descarta una propuesta especifica conservando su huella para idempotencia."""
        prop = self.get_proposal(prop_id)
        if prop["estado"] == "consolidada":
            raise ValueError(f"La propuesta '{prop_id}' ya fue consolidada y no puede descartarse.")
        prop["estado"] = "descartada"
        if reason:
            prop["nota"] = reason
        prop["actualizado_en"] = _utc_now_iso()
        self.save_proposal(prop)
        return prop
