"""Preparacion Dry-Run (diff + SHA-256) y consolidacion segura auditada."""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from scripts.entity_resolver import normalize_text
from scripts.id_manager import IdManager
from scripts.markdown_io import (
    NoteDocument,
    atomic_write_text,
    dump_markdown_note,
    iter_consolidated_notes,
    parse_markdown_note,
)
from scripts.schema_loader import get_workspace_root, load_schema
from scripts.staging import StagingManager
from scripts.validator import VaultValidator


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _today_iso() -> str:
    return date.today().isoformat()


def sha256_of_file(path: Path) -> str:
    """Devuelve SHA-256 de un archivo existente o 'ABSENT' si no existe."""
    if not path.exists():
        return "ABSENT"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_filename(title: str) -> str:
    """Genera un nombre de archivo legible para Obsidian sin caracteres prohibidos."""
    cleaned = re.sub(r'[<>:"/\\|?*]', "", title).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "Nota sin titulo"


class SafeCommitter:
    """Ejecuta Dry-Run y consolidacion verificada sobre Conocimiento/ e Historia/."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = get_workspace_root(root)
        self.schema = load_schema(self.root)
        self.staging = StagingManager(self.root)
        self.auditoria_dir = self.staging.auditoria_dir
        self.audit_log_path = self.auditoria_dir / "audit_log.jsonl"

    def _append_audit(self, event: dict[str, Any]) -> None:
        self.auditoria_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False)
        with self.audit_log_path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")

    def _next_batch_id(self) -> str:
        stamp = date.today().strftime("%Y%m%d")
        existing = sorted(self.auditoria_dir.glob(f"batch-{stamp}-*.json"))
        seq = len(existing) + 1
        return f"batch-{stamp}-{seq:03d}"

    @staticmethod
    def _allocate_in_memory(counters: dict[str, int], prefix: str) -> str:
        counters[prefix] = counters.get(prefix, 0) + 1
        return f"{prefix}-{counters[prefix]:06d}"

    def _build_node_frontmatter(
        self,
        *,
        node_id: str,
        tipo: str,
        subtipo: str | None,
        titulo: str,
        aliases: list[str],
        ambito: str,
        estado: str,
        fuente: str,
        evidencia: str,
        confianza: str,
        registrado_el: str,
        ocurrio_el: str | None,
        criterio: str | None = None,
        solicitada_por_usuario: bool = False,
    ) -> dict[str, Any]:
        today = _today_iso()
        fm: dict[str, Any] = {
            "schema_version": self.schema["schema_version"],
            "id": node_id,
            "tipo": tipo,
            "subtipo": subtipo,
            "titulo": titulo,
            "aliases": aliases,
            "ambito": ambito,
            "estado": estado,
            "creado_el": today,
            "actualizado_el": today,
            "ocurrio_el": ocurrio_el,
            "registrado_el": registrado_el,
            "evidencia": evidencia,
            "fuente": fuente,
            "confianza": confianza,
            "tags": [],
            "relaciones": [],
        }
        if tipo == "decision":
            fm["alternativas"] = []
            fm["criterio"] = criterio or "Criterio registrado en conversacion"
            fm["estado_decision"] = "aprobada"
        elif tipo == "accion":
            fm["prioridad"] = None
            fm["plazo"] = None
            fm["responsable_id"] = None
            fm["solicitada_por_usuario"] = solicitada_por_usuario
        return fm

    def _resolve_or_plan_node(
        self,
        *,
        titulo: str,
        tipo: str,
        subtipo: str | None,
        aliases: list[str],
        ambito: str,
        fuente: str,
        evidencia: str,
        confianza: str,
        registrado_el: str,
        ocurrio_el: str | None,
        criterio: str | None,
        solicitada_por_usuario: bool,
        virtual_docs: dict[Path, NoteDocument],
        counters: dict[str, int],
        estado_override: str | None = None,
    ) -> tuple[Path, NoteDocument]:
        """Busca un nodo existente en el estado virtual o planifica uno nuevo."""
        norm_title = normalize_text(titulo)
        for path, doc in virtual_docs.items():
            fm = doc.frontmatter
            if fm.get("tipo") != tipo:
                continue
            names = {normalize_text(str(fm.get("titulo", "")))}
            names.update(normalize_text(str(a)) for a in (fm.get("aliases") or []))
            if norm_title in names:
                return path, doc

        prefix = self.schema["classes"][tipo]["prefix"]
        folder = self.root / self.schema["classes"][tipo]["folder"]
        node_id = self._allocate_in_memory(counters, prefix)
        target_path = (folder / f"{safe_filename(titulo)}.md").resolve()
        if target_path in virtual_docs:
            target_path = (folder / f"{safe_filename(titulo)} ({node_id}).md").resolve()

        default_estado = "historico" if tipo == "evento" else "activo"
        fm = self._build_node_frontmatter(
            node_id=node_id,
            tipo=tipo,
            subtipo=subtipo,
            titulo=titulo,
            aliases=aliases,
            ambito=ambito,
            estado=estado_override or default_estado,
            fuente=fuente,
            evidencia=evidencia,
            confianza=confianza,
            registrado_el=registrado_el,
            ocurrio_el=ocurrio_el,
            criterio=criterio,
            solicitada_por_usuario=solicitada_por_usuario,
        )
        body = f"# {titulo}\n\nNota generada desde propuesta consolidada ({fuente}).\n"
        doc = NoteDocument(path=target_path, frontmatter=fm, body=body, raw_yaml="")
        virtual_docs[target_path] = doc
        return target_path, doc

    def _assert_safe_consolidated_path(self, path: Path) -> None:
        resolved = path.resolve()
        allowed_roots = (
            (self.root / "Conocimiento").resolve(),
            (self.root / "Historia").resolve(),
        )
        if not any(resolved.is_relative_to(r) for r in allowed_roots):
            raise PermissionError(
                f"Consolidacion rechazada fuera de Conocimiento/ o Historia/: {resolved}"
            )

    def prepare_commit(
        self,
        proposal_ids: list[str],
        *,
        allow_actions: bool = False,
    ) -> dict[str, Any]:
        """Genera Dry-Run con diff exacto y SHA-256 previo para propuestas aprobadas."""
        if not proposal_ids:
            raise ValueError("Debe indicar al menos una propuesta aprobada.")

        unique_ids = list(dict.fromkeys(proposal_ids))
        proposals: list[dict[str, Any]] = []
        for pid in unique_ids:
            prop = self.staging.get_proposal(pid)
            if prop.get("estado") != "aprobada":
                raise ValueError(
                    f"La propuesta '{pid}' tiene estado '{prop.get('estado')}'; "
                    "solo se pueden preparar propuestas en estado 'aprobada'."
                )
            if prop.get("target_tipo") == "accion":
                if not allow_actions or not prop.get("solicitada_por_usuario"):
                    raise PermissionError(
                        f"La propuesta '{pid}' crea una accion y requiere solicitud explicita + allow_actions."
                    )
            proposals.append(prop)

        virtual_docs: dict[Path, NoteDocument] = {}
        original_texts: dict[Path, str] = {}
        for path in iter_consolidated_notes(self.root):
            resolved = path.resolve()
            original_texts[resolved] = resolved.read_text(encoding="utf-8")
            virtual_docs[resolved] = parse_markdown_note(resolved)

        counters = IdManager(self.root).load_counters()
        touched_paths: set[Path] = set()

        for prop in proposals:
            op_type = prop.get("op_type", "create_node")
            target_tipo = str(prop["target_tipo"])
            target_titulo = str(prop["target_titulo"])
            fuente = str(prop.get("fuente", "[[Conversación]]"))
            evidencia = str(prop.get("evidencia", "reportada"))
            confianza = str(prop.get("confianza", "media"))
            reg_date = str(prop.get("registrado_el") or _today_iso())
            occ_date = prop.get("ocurrio_el")
            ambito = str(prop.get("ambito", "transversal"))

            src_path, src_doc = self._resolve_or_plan_node(
                titulo=target_titulo,
                tipo=target_tipo,
                subtipo=prop.get("target_subtipo"),
                aliases=list(prop.get("aliases") or []),
                ambito=ambito,
                fuente=fuente,
                evidencia=evidencia,
                confianza=confianza,
                registrado_el=reg_date,
                ocurrio_el=occ_date,
                criterio=prop.get("criterio"),
                solicitada_por_usuario=bool(prop.get("solicitada_por_usuario", False)),
                virtual_docs=virtual_docs,
                counters=counters,
            )
            touched_paths.add(src_path)

            if op_type in ("add_relation", "temporal_change"):
                dst_tipo = str(prop["destino_tipo"])
                dst_titulo = str(prop["destino_titulo"])
                dst_path, dst_doc = self._resolve_or_plan_node(
                    titulo=dst_titulo,
                    tipo=dst_tipo,
                    subtipo=prop.get("destino_subtipo"),
                    aliases=[],
                    ambito=ambito,
                    fuente=fuente,
                    evidencia=evidencia,
                    confianza=confianza,
                    registrado_el=reg_date,
                    ocurrio_el=occ_date,
                    criterio=None,
                    solicitada_por_usuario=False,
                    virtual_docs=virtual_docs,
                    counters=counters,
                )
                touched_paths.add(dst_path)

                if op_type == "temporal_change" and prop.get("old_destino_titulo"):
                    old_dst_norm = normalize_text(str(prop["old_destino_titulo"]))
                    for rel in src_doc.frontmatter.get("relaciones") or []:
                        if (
                            isinstance(rel, dict)
                            and rel.get("predicado") == prop.get("predicado")
                            and normalize_text(str(rel.get("destino", "")).strip("[]")) == old_dst_norm
                            and rel.get("vigencia") != "historica"
                        ):
                            rel["vigencia"] = "historica"
                            rel["vigente_hasta"] = occ_date or reg_date
                            rel["nota"] = (
                                (rel.get("nota") + " | " if rel.get("nota") else "")
                                + f"Cerrada por cambio temporal ({fuente})"
                            )

                    eve_titulo = f"Cambio de {prop.get('predicado')} de {target_titulo}"
                    eve_path, eve_doc = self._resolve_or_plan_node(
                        titulo=eve_titulo,
                        tipo="evento",
                        subtipo="cambio_estado",
                        aliases=[],
                        ambito=ambito,
                        fuente=fuente,
                        evidencia=evidencia,
                        confianza=confianza,
                        registrado_el=reg_date,
                        ocurrio_el=occ_date,
                        criterio=None,
                        solicitada_por_usuario=False,
                        virtual_docs=virtual_docs,
                        counters=counters,
                        estado_override="historico",
                    )
                    eve_rel_id = self._allocate_in_memory(counters, "rel")
                    eve_doc.frontmatter["relaciones"].append(
                        {
                            "id": eve_rel_id,
                            "predicado": "afecta_a",
                            "destino_id": src_doc.frontmatter["id"],
                            "destino": f"[[{src_doc.frontmatter['titulo']}]]",
                            "evidencia": evidencia,
                            "fuente": fuente,
                            "registrado_el": reg_date,
                            "ocurrio_el": occ_date,
                            "vigente_desde": None,
                            "vigente_hasta": None,
                            "vigencia": "historica",
                            "nota": prop.get("texto_fuente") or "Cambio temporal registrado.",
                        }
                    )
                    touched_paths.add(eve_path)

                predicado = str(prop["predicado"])
                dst_id = dst_doc.frontmatter["id"]
                already_has_rel = any(
                    isinstance(r, dict)
                    and r.get("predicado") == predicado
                    and r.get("destino_id") == dst_id
                    and r.get("vigencia") != "historica"
                    for r in src_doc.frontmatter["relaciones"]
                )
                if not already_has_rel:
                    rel_id = self._allocate_in_memory(counters, "rel")
                    src_doc.frontmatter["relaciones"].append(
                        {
                            "id": rel_id,
                            "predicado": predicado,
                            "destino_id": dst_id,
                            "destino": f"[[{dst_doc.frontmatter['titulo']}]]",
                            "evidencia": evidencia,
                            "fuente": fuente,
                            "registrado_el": reg_date,
                            "ocurrio_el": occ_date,
                            "vigente_desde": occ_date,
                            "vigente_hasta": None,
                            "vigencia": prop.get("vigencia", "desconocida"),
                            "nota": prop.get("nota"),
                        }
                    )
                src_doc.frontmatter["actualizado_el"] = _today_iso()

        changes: list[dict[str, Any]] = []
        for path in sorted(touched_paths):
            self._assert_safe_consolidated_path(path)
            doc = virtual_docs[path]
            new_text = dump_markdown_note(doc.frontmatter, doc.body)
            old_text = original_texts.get(path, "")
            prev_hash = sha256_of_file(path)
            new_hash = hashlib.sha256(new_text.encode("utf-8")).hexdigest()
            if prev_hash == new_hash:
                continue
            rel_path = str(path.relative_to(self.root)).replace("\\", "/")
            diff_lines = list(
                difflib.unified_diff(
                    old_text.splitlines(keepends=True),
                    new_text.splitlines(keepends=True),
                    fromfile=f"a/{rel_path}",
                    tofile=f"b/{rel_path}",
                )
            )
            changes.append(
                {
                    "relative_path": rel_path,
                    "action": "create" if prev_hash == "ABSENT" else "update",
                    "prev_sha256": prev_hash,
                    "new_sha256": new_hash,
                    "diff": "".join(diff_lines),
                    "new_content": new_text,
                }
            )

        batch_id = self._next_batch_id()
        manifest = {
            "batch_id": batch_id,
            "status": "prepared",
            "created_at": _utc_now_iso(),
            "proposal_ids": unique_ids,
            "changes": changes,
        }
        manifest_path = self.auditoria_dir / f"{batch_id}.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        self._append_audit(
            {
                "timestamp": _utc_now_iso(),
                "event": "prepare_commit",
                "batch_id": batch_id,
                "proposal_ids": unique_ids,
                "files_count": len(changes),
            }
        )
        return manifest

    def apply_commit(
        self,
        batch_id: str,
        *,
        confirm: bool = False,
        writer_fn: Callable[[Path, str], None] | None = None,
    ) -> dict[str, Any]:
        """Aplica cambios aprobados verificando hashes previos, YAML y lectura posterior."""
        if not confirm:
            raise PermissionError("La consolidacion exige --confirm explicito tras revisar el Dry-Run.")

        manifest_path = self.auditoria_dir / f"{batch_id}.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Lote Dry-Run no encontrado: {batch_id}")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") != "prepared":
            raise ValueError(
                f"El lote '{batch_id}' tiene estado '{manifest.get('status')}' y no puede aplicarse."
            )

        changes: list[dict[str, Any]] = manifest.get("changes", [])

        for ch in changes:
            target = (self.root / ch["relative_path"]).resolve()
            self._assert_safe_consolidated_path(target)
            current_hash = sha256_of_file(target)
            if current_hash != ch["prev_sha256"]:
                manifest["status"] = "aborted_stale"
                manifest_path.write_text(
                    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
                self._append_audit(
                    {
                        "timestamp": _utc_now_iso(),
                        "event": "apply_aborted_stale",
                        "batch_id": batch_id,
                        "file": ch["relative_path"],
                        "expected_sha256": ch["prev_sha256"],
                        "actual_sha256": current_hash,
                    }
                )
                raise RuntimeError(
                    f"Dry-Run obsoleto: '{ch['relative_path']}' cambio en disco "
                    f"(esperado {ch['prev_sha256']}, actual {current_hash})."
                )

        written_files: list[str] = []
        failed_files: list[dict[str, str]] = []
        for ch in changes:
            target = (self.root / ch["relative_path"]).resolve()
            try:
                if writer_fn is not None:
                    writer_fn(target, ch["new_content"])
                else:
                    atomic_write_text(target, ch["new_content"], overwrite=True)
                written_files.append(ch["relative_path"])
            except Exception as exc:
                failed_files.append({"relative_path": ch["relative_path"], "error": str(exc)})
                manifest["status"] = "partial_failure"
                manifest["written_files"] = written_files
                manifest["failed_files"] = failed_files
                manifest_path.write_text(
                    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
                self._append_audit(
                    {
                        "timestamp": _utc_now_iso(),
                        "event": "apply_partial_failure",
                        "batch_id": batch_id,
                        "written_files": written_files,
                        "failed_files": failed_files,
                    }
                )
                raise RuntimeError(
                    f"Fallo parcial al aplicar '{batch_id}' en '{ch['relative_path']}'. "
                    f"Escritos: {written_files}. Revisar auditoria."
                ) from exc

        for rel_path in written_files:
            parse_markdown_note((self.root / rel_path).resolve())

        report = VaultValidator(self.root).validate_all()
        if not report.is_valid:
            manifest["status"] = "validation_failed_post_write"
            manifest["validation_errors"] = [e.to_dict() for e in report.errors]
            manifest_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            self._append_audit(
                {
                    "timestamp": _utc_now_iso(),
                    "event": "apply_validation_error",
                    "batch_id": batch_id,
                    "errors": [e.to_dict() for e in report.errors],
                }
            )
            raise RuntimeError(
                f"Error de validacion posterior al commit '{batch_id}': "
                + "; ".join(e.message for e in report.errors)
            )

        IdManager(self.root).rebuild_registry()
        for pid in manifest.get("proposal_ids", []):
            prop = self.staging.get_proposal(pid)
            prop["estado"] = "consolidada"
            prop["batch_id"] = batch_id
            prop["actualizado_en"] = _utc_now_iso()
            self.staging.save_proposal(prop)

        manifest["status"] = "committed"
        manifest["committed_at"] = _utc_now_iso()
        manifest["written_files"] = written_files
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        self._append_audit(
            {
                "timestamp": _utc_now_iso(),
                "event": "apply_committed",
                "batch_id": batch_id,
                "proposal_ids": manifest.get("proposal_ids", []),
                "written_files": written_files,
            }
        )
        return manifest
