"""Validador de esquema YAML, integridad referencial, duplicados y ciclos."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.entity_resolver import normalize_text
from scripts.markdown_io import NoteDocument, iter_consolidated_notes, parse_markdown_note
from scripts.schema_loader import (
    NODE_ID_RE,
    REL_ID_RE,
    extract_wikilink_target,
    get_workspace_root,
    is_valid_iso_date,
    load_schema,
)


@dataclass
class ValidationIssue:
    """Incidencia detectada durante la validacion."""

    severity: str  # ERROR | WARNING
    code: str
    message: str
    path: Path | None = None
    node_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "path": str(self.path) if self.path else None,
            "node_id": self.node_id,
        }


@dataclass
class ValidationReport:
    """Resultado agregado de la validacion de toda la boveda."""

    notes_checked: int = 0
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "ERROR"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "WARNING"]

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


class VaultValidator:
    """Valida notas consolidadas contra ESPECIFICACION_V1 y modelo_v1.json."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = get_workspace_root(root)
        self.schema = load_schema(self.root)

    def _validate_node_fields(
        self,
        doc: NoteDocument,
        issues: list[ValidationIssue],
    ) -> None:
        fm = doc.frontmatter
        node_id = fm.get("id") if isinstance(fm.get("id"), str) else None

        for req in self.schema["required_node_fields"]:
            if req not in fm:
                issues.append(
                    ValidationIssue(
                        severity="ERROR",
                        code="MISSING_FIELD",
                        message=f"Falta el campo obligatorio '{req}'.",
                        path=doc.path,
                        node_id=node_id,
                    )
                )

        if fm.get("schema_version") != self.schema["schema_version"]:
            issues.append(
                ValidationIssue(
                    severity="ERROR",
                    code="INVALID_SCHEMA_VERSION",
                    message=(
                        f"schema_version debe ser '{self.schema['schema_version']}', "
                        f"se encontro '{fm.get('schema_version')}'."
                    ),
                    path=doc.path,
                    node_id=node_id,
                )
            )

        tipo = fm.get("tipo")
        if tipo not in self.schema["classes"]:
            issues.append(
                ValidationIssue(
                    severity="ERROR",
                    code="INVALID_TIPO",
                    message=f"Tipo de nodo no valido: '{tipo}'.",
                    path=doc.path,
                    node_id=node_id,
                )
            )
        else:
            expected_prefix = self.schema["classes"][tipo]["prefix"]
            if not isinstance(node_id, str) or not NODE_ID_RE.match(node_id):
                issues.append(
                    ValidationIssue(
                        severity="ERROR",
                        code="INVALID_NODE_ID",
                        message=f"ID de nodo invalido: '{node_id}'.",
                        path=doc.path,
                        node_id=node_id,
                    )
                )
            elif not node_id.startswith(f"{expected_prefix}-"):
                issues.append(
                    ValidationIssue(
                        severity="ERROR",
                        code="ID_PREFIX_MISMATCH",
                        message=(
                            f"El nodo tipo '{tipo}' debe tener prefijo '{expected_prefix}-', "
                            f"se encontro '{node_id}'."
                        ),
                        path=doc.path,
                        node_id=node_id,
                    )
                )

            allowed_subtipos = self.schema["classes"][tipo]["subtipos"]
            if "subtipo" in fm and fm.get("subtipo") not in allowed_subtipos:
                issues.append(
                    ValidationIssue(
                        severity="ERROR",
                        code="INVALID_SUBTIPO",
                        message=(
                            f"Subtipo '{fm.get('subtipo')}' no valido para '{tipo}'. "
                            f"Permitidos: {allowed_subtipos}"
                        ),
                        path=doc.path,
                        node_id=node_id,
                    )
                )

        for enum_field in ("ambito", "estado", "evidencia", "confianza"):
            val = fm.get(enum_field)
            allowed = self.schema["enums"][enum_field]
            if val not in allowed:
                issues.append(
                    ValidationIssue(
                        severity="ERROR",
                        code="INVALID_ENUM",
                        message=f"Valor '{val}' invalido para '{enum_field}'. Permitidos: {allowed}",
                        path=doc.path,
                        node_id=node_id,
                    )
                )

        if not isinstance(fm.get("aliases"), list):
            issues.append(
                ValidationIssue(
                    severity="ERROR",
                    code="INVALID_ALIASES",
                    message="El campo 'aliases' debe ser una lista (puede ser []).",
                    path=doc.path,
                    node_id=node_id,
                )
            )

        for date_field in ("creado_el", "actualizado_el", "registrado_el"):
            if date_field in fm and not is_valid_iso_date(fm.get(date_field)):
                issues.append(
                    ValidationIssue(
                        severity="ERROR",
                        code="INVALID_DATE",
                        message=f"Fecha ISO invalida en '{date_field}': '{fm.get(date_field)}'.",
                        path=doc.path,
                        node_id=node_id,
                    )
                )

        if "ocurrio_el" in fm and fm.get("ocurrio_el") is not None:
            if not is_valid_iso_date(fm.get("ocurrio_el")):
                issues.append(
                    ValidationIssue(
                        severity="ERROR",
                        code="INVALID_DATE",
                        message=f"Fecha ISO invalida en 'ocurrio_el': '{fm.get('ocurrio_el')}'.",
                        path=doc.path,
                        node_id=node_id,
                    )
                )

        if tipo == "accion" and fm.get("solicitada_por_usuario") is not True:
            issues.append(
                ValidationIssue(
                    severity="ERROR",
                    code="UNAPPROVED_ACTION",
                    message="Toda nota 'accion' consolidada requiere 'solicitada_por_usuario: true'.",
                    path=doc.path,
                    node_id=node_id,
                )
            )

        if not isinstance(fm.get("relaciones"), list):
            issues.append(
                ValidationIssue(
                    severity="ERROR",
                    code="INVALID_RELATIONS_TYPE",
                    message="El campo 'relaciones' debe ser una lista.",
                    path=doc.path,
                    node_id=node_id,
                )
            )

    def _validate_relations(
        self,
        docs_by_path: dict[Path, NoteDocument],
        nodes_by_id: dict[str, list[NoteDocument]],
        issues: list[ValidationIssue],
    ) -> list[tuple[str, str]]:
        """Valida predicados, tipos origen/destino, links rotos e IDs de relacion."""
        rel_ids: dict[str, list[Path]] = defaultdict(list)
        dependency_edges: list[tuple[str, str]] = []

        for path, doc in docs_by_path.items():
            fm = doc.frontmatter
            source_id = str(fm.get("id", ""))
            source_tipo = fm.get("tipo")
            rels = fm.get("relaciones")
            if not isinstance(rels, list):
                continue

            for idx, rel in enumerate(rels):
                if not isinstance(rel, dict):
                    issues.append(
                        ValidationIssue(
                            severity="ERROR",
                            code="INVALID_RELATION_ITEM",
                            message=f"La relacion #{idx + 1} debe ser un objeto YAML.",
                            path=path,
                            node_id=source_id,
                        )
                    )
                    continue

                for req in self.schema["required_relation_fields"]:
                    if req not in rel:
                        issues.append(
                            ValidationIssue(
                                severity="ERROR",
                                code="MISSING_RELATION_FIELD",
                                message=f"Falta '{req}' en relacion #{idx + 1}.",
                                path=path,
                                node_id=source_id,
                            )
                        )

                rel_id = rel.get("id")
                if not isinstance(rel_id, str) or not REL_ID_RE.match(rel_id):
                    issues.append(
                        ValidationIssue(
                            severity="ERROR",
                            code="INVALID_RELATION_ID",
                            message=f"ID de relacion invalido: '{rel_id}'.",
                            path=path,
                            node_id=source_id,
                        )
                    )
                else:
                    rel_ids[rel_id].append(path)

                pred = rel.get("predicado")
                pred_cfg = self.schema["predicates"].get(pred)
                if pred_cfg is None:
                    issues.append(
                        ValidationIssue(
                            severity="ERROR",
                            code="INVALID_PREDICATE",
                            message=f"Predicado desconocido '{pred}' en relacion '{rel_id}'.",
                            path=path,
                            node_id=source_id,
                        )
                    )
                else:
                    allowed_origins = pred_cfg["origen"]
                    if "*" not in allowed_origins and source_tipo not in allowed_origins:
                        issues.append(
                            ValidationIssue(
                                severity="ERROR",
                                code="INVALID_RELATION_DOMAIN",
                                message=(
                                    f"El predicado '{pred}' no admite origen '{source_tipo}' "
                                    f"(permitidos: {allowed_origins})."
                                ),
                                path=path,
                                node_id=source_id,
                            )
                        )

                if rel.get("evidencia") not in self.schema["enums"]["evidencia"]:
                    issues.append(
                        ValidationIssue(
                            severity="ERROR",
                            code="INVALID_RELATION_EVIDENCE",
                            message=f"Evidencia invalida en relacion '{rel_id}': '{rel.get('evidencia')}'.",
                            path=path,
                            node_id=source_id,
                        )
                    )

                if rel.get("vigencia") not in self.schema["enums"]["vigencia"]:
                    issues.append(
                        ValidationIssue(
                            severity="ERROR",
                            code="INVALID_VIGENCIA",
                            message=f"Vigencia invalida en relacion '{rel_id}': '{rel.get('vigencia')}'.",
                            path=path,
                            node_id=source_id,
                        )
                    )

                for df in ("registrado_el",):
                    if df in rel and not is_valid_iso_date(rel.get(df)):
                        issues.append(
                            ValidationIssue(
                                severity="ERROR",
                                code="INVALID_RELATION_DATE",
                                message=f"Fecha invalida '{df}' en relacion '{rel_id}'.",
                                path=path,
                                node_id=source_id,
                            )
                        )
                for opt_df in ("ocurrio_el", "vigente_desde", "vigente_hasta"):
                    if rel.get(opt_df) is not None and not is_valid_iso_date(rel.get(opt_df)):
                        issues.append(
                            ValidationIssue(
                                severity="ERROR",
                                code="INVALID_RELATION_DATE",
                                message=f"Fecha invalida '{opt_df}' en relacion '{rel_id}'.",
                                path=path,
                                node_id=source_id,
                            )
                        )

                dest_id = rel.get("destino_id")
                wikilink_title = extract_wikilink_target(rel.get("destino"))
                if wikilink_title is None:
                    issues.append(
                        ValidationIssue(
                            severity="ERROR",
                            code="INVALID_WIKILINK",
                            message=(
                                f"El campo 'destino' en relacion '{rel_id}' debe ser un Wikilink "
                                f"valido entre comillas (ej. \"[[Titulo]]\"), se encontro '{rel.get('destino')}'."
                            ),
                            path=path,
                            node_id=source_id,
                        )
                    )

                target_docs = nodes_by_id.get(str(dest_id), [])
                if not target_docs:
                    issues.append(
                        ValidationIssue(
                            severity="ERROR",
                            code="BROKEN_REFERENCE",
                            message=(
                                f"Referencia rota en relacion '{rel_id}': destino_id '{dest_id}' "
                                f"({rel.get('destino')}) no existe en la boveda."
                            ),
                            path=path,
                            node_id=source_id,
                        )
                    )
                else:
                    target_doc = target_docs[0]
                    target_fm = target_doc.frontmatter
                    target_tipo = target_fm.get("tipo")
                    if pred_cfg is not None:
                        allowed_dests = pred_cfg["destino"]
                        if "*" not in allowed_dests and target_tipo not in allowed_dests:
                            issues.append(
                                ValidationIssue(
                                    severity="ERROR",
                                    code="INVALID_RELATION_RANGE",
                                    message=(
                                        f"El predicado '{pred}' no admite destino '{target_tipo}' "
                                        f"(permitidos: {allowed_dests})."
                                    ),
                                    path=path,
                                    node_id=source_id,
                                )
                            )
                    if wikilink_title is not None:
                        valid_names = {normalize_text(str(target_fm.get("titulo", "")))}
                        valid_names.update(
                            normalize_text(str(a)) for a in (target_fm.get("aliases") or [])
                        )
                        valid_names.add(normalize_text(target_doc.path.stem))
                        if normalize_text(wikilink_title) not in valid_names:
                            issues.append(
                                ValidationIssue(
                                    severity="ERROR",
                                    code="BROKEN_WIKILINK",
                                    message=(
                                        f"El Wikilink '[[{wikilink_title}]]' en '{rel_id}' no coincide "
                                        f"con el titulo/alias de '{dest_id}' ('{target_fm.get('titulo')}')."
                                    ),
                                    path=path,
                                    node_id=source_id,
                                )
                            )

                if pred == "depende_de" and isinstance(dest_id, str) and source_id:
                    dependency_edges.append((source_id, dest_id))
                elif pred == "habilita_a" and isinstance(dest_id, str) and source_id:
                    # Si A habilita_a B, entonces B depende operativamente de A
                    dependency_edges.append((dest_id, source_id))

        for rel_id, paths in rel_ids.items():
            if len(paths) > 1:
                issues.append(
                    ValidationIssue(
                        severity="ERROR",
                        code="DUPLICATE_RELATION_ID",
                        message=f"ID de relacion duplicado '{rel_id}' en {len(paths)} archivos.",
                        path=paths[0],
                    )
                )

        return dependency_edges

    @staticmethod
    def find_cycles(edges: list[tuple[str, str]]) -> list[list[str]]:
        """Detecta ciclos dirigidos mediante DFS determinista."""
        adj: dict[str, list[str]] = defaultdict(list)
        nodes: set[str] = set()
        for src, dst in edges:
            adj[src].append(dst)
            nodes.add(src)
            nodes.add(dst)

        state: dict[str, int] = {}  # 0=unvisited, 1=visiting, 2=done
        stack: list[str] = []
        cycles: list[list[str]] = []
        seen_signatures: set[tuple[str, ...]] = set()

        def dfs(node: str) -> None:
            state[node] = 1
            stack.append(node)
            for nxt in sorted(adj.get(node, [])):
                nxt_state = state.get(nxt, 0)
                if nxt_state == 0:
                    dfs(nxt)
                elif nxt_state == 1:
                    idx = stack.index(nxt)
                    cycle = stack[idx:] + [nxt]
                    sig = tuple(sorted(set(cycle[:-1])))
                    if sig not in seen_signatures:
                        seen_signatures.add(sig)
                        cycles.append(cycle)
            stack.pop()
            state[node] = 2

        for node in sorted(nodes):
            if state.get(node, 0) == 0:
                dfs(node)
        return cycles

    def validate_all(self) -> ValidationReport:
        """Ejecuta todas las comprobaciones de esquema, IDs, links, duplicados y ciclos."""
        report = ValidationReport()
        note_paths = iter_consolidated_notes(self.root)
        docs_by_path: dict[Path, NoteDocument] = {}
        nodes_by_id: dict[str, list[NoteDocument]] = defaultdict(list)
        title_tipo_index: dict[tuple[str, str], list[NoteDocument]] = defaultdict(list)

        for path in note_paths:
            report.notes_checked += 1
            try:
                doc = parse_markdown_note(path)
            except Exception as exc:
                report.issues.append(
                    ValidationIssue(
                        severity="ERROR",
                        code="YAML_PARSE_ERROR",
                        message=str(exc),
                        path=path,
                    )
                )
                continue

            docs_by_path[path] = doc
            self._validate_node_fields(doc, report.issues)
            node_id = doc.frontmatter.get("id")
            if isinstance(node_id, str):
                nodes_by_id[node_id].append(doc)
            titulo = doc.frontmatter.get("titulo")
            tipo = doc.frontmatter.get("tipo")
            if isinstance(titulo, str) and isinstance(tipo, str):
                title_tipo_index[(tipo, normalize_text(titulo))].append(doc)

        for node_id, docs in nodes_by_id.items():
            if len(docs) > 1:
                paths_str = ", ".join(str(d.path.relative_to(self.root)) for d in docs)
                report.issues.append(
                    ValidationIssue(
                        severity="ERROR",
                        code="DUPLICATE_NODE_ID",
                        message=f"ID de nodo repetido '{node_id}' en: {paths_str}",
                        path=docs[0].path,
                        node_id=node_id,
                    )
                )

        for (tipo, _norm_title), docs in title_tipo_index.items():
            if len(docs) > 1:
                ids_str = ", ".join(str(d.frontmatter.get("id")) for d in docs)
                report.issues.append(
                    ValidationIssue(
                        severity="WARNING",
                        code="POSSIBLE_DUPLICATE_ENTITY",
                        message=(
                            f"Posible duplicado o homonimo de tipo '{tipo}' con igual titulo "
                            f"'{docs[0].frontmatter.get('titulo')}': IDs [{ids_str}]."
                        ),
                        path=docs[0].path,
                    )
                )

        dep_edges = self._validate_relations(docs_by_path, nodes_by_id, report.issues)
        for cycle in self.find_cycles(dep_edges):
            report.issues.append(
                ValidationIssue(
                    severity="ERROR",
                    code="DEPENDENCY_CYCLE",
                    message=f"Ciclo operativo detectado en dependencias: {' -> '.join(cycle)}",
                )
            )

        return report
