"""Pruebas unitarias de la etapa B1 (estructura, validacion, IDs y resolucion)."""

from __future__ import annotations

import shutil
from pathlib import Path

from scripts.brain_cli import main as cli_main
from scripts.entity_resolver import EntityResolver
from scripts.id_manager import IdManager
from scripts.markdown_io import dump_markdown_note, parse_markdown_note
from scripts.schema_loader import get_workspace_root
from scripts.validator import VaultValidator


def _copy_vault_to_tmp(tmp_path: Path) -> Path:
    """Crea una copia aislada de Sistema/ y Conocimiento/ para pruebas destructivas."""
    src_root = get_workspace_root()
    dst_root = tmp_path / "vault"
    shutil.copytree(src_root / "Sistema", dst_root / "Sistema")
    shutil.copytree(src_root / "Conocimiento", dst_root / "Conocimiento")
    (dst_root / "Historia" / "Eventos").mkdir(parents=True, exist_ok=True)
    return dst_root


def test_workspace_fictional_examples_are_valid() -> None:
    root = get_workspace_root()
    report = VaultValidator(root).validate_all()
    assert report.notes_checked >= 4
    assert report.is_valid, [i.to_dict() for i in report.errors]


def test_detects_duplicate_node_id(tmp_path: Path) -> None:
    vault = _copy_vault_to_tmp(tmp_path)
    doc = parse_markdown_note(vault / "Conocimiento" / "Personas" / "Juan Garcia.md")
    dup_fm = dict(doc.frontmatter)
    dup_fm["titulo"] = "Juan Garcia Copia"
    dup_fm["relaciones"] = []
    (vault / "Conocimiento" / "Personas" / "Juan Garcia Copia.md").write_text(
        dump_markdown_note(dup_fm, "# Copia"),
        encoding="utf-8",
    )

    report = VaultValidator(vault).validate_all()
    codes = {issue.code for issue in report.errors}
    assert "DUPLICATE_NODE_ID" in codes


def test_detects_broken_reference_and_broken_wikilink(tmp_path: Path) -> None:
    vault = _copy_vault_to_tmp(tmp_path)
    juan_path = vault / "Conocimiento" / "Personas" / "Juan Garcia.md"
    doc = parse_markdown_note(juan_path)
    fm = dict(doc.frontmatter)
    fm["relaciones"] = [
        {
            "id": "rel-000001",
            "predicado": "tiene_capacidad",
            "destino_id": "con-999999",
            "destino": "[[Herreria Inexistente]]",
            "evidencia": "reportada",
            "fuente": "[[Test]]",
            "registrado_el": "2026-11-18",
            "ocurrio_el": None,
            "vigente_desde": None,
            "vigente_hasta": None,
            "vigencia": "desconocida",
        },
        {
            "id": "rel-000010",
            "predicado": "tiene_capacidad",
            "destino_id": "con-000001",
            "destino": "[[Nombre Equivocado]]",
            "evidencia": "reportada",
            "fuente": "[[Test]]",
            "registrado_el": "2026-11-18",
            "ocurrio_el": None,
            "vigente_desde": None,
            "vigente_hasta": None,
            "vigencia": "desconocida",
        },
    ]
    juan_path.write_text(dump_markdown_note(fm, doc.body), encoding="utf-8")

    report = VaultValidator(vault).validate_all()
    codes = {issue.code for issue in report.errors}
    assert "BROKEN_REFERENCE" in codes
    assert "BROKEN_WIKILINK" in codes


def test_detects_dependency_cycle(tmp_path: Path) -> None:
    vault = _copy_vault_to_tmp(tmp_path)
    doc_a = {
        "schema_version": "1.0",
        "id": "doc-000001",
        "tipo": "documento",
        "subtipo": "plano",
        "titulo": "Plano A",
        "aliases": [],
        "ambito": "ingenieria",
        "estado": "activo",
        "creado_el": "2026-11-18",
        "actualizado_el": "2026-11-18",
        "ocurrio_el": None,
        "registrado_el": "2026-11-18",
        "evidencia": "confirmada",
        "fuente": "[[Test]]",
        "confianza": "alta",
        "relaciones": [
            {
                "id": "rel-000020",
                "predicado": "depende_de",
                "destino_id": "doc-000002",
                "destino": "[[Plano B]]",
                "evidencia": "confirmada",
                "fuente": "[[Test]]",
                "registrado_el": "2026-11-18",
                "ocurrio_el": None,
                "vigente_desde": None,
                "vigente_hasta": None,
                "vigencia": "vigente",
            }
        ],
    }
    doc_b = {
        **doc_a,
        "id": "doc-000002",
        "titulo": "Plano B",
        "relaciones": [
            {
                "id": "rel-000021",
                "predicado": "depende_de",
                "destino_id": "doc-000001",
                "destino": "[[Plano A]]",
                "evidencia": "confirmada",
                "fuente": "[[Test]]",
                "registrado_el": "2026-11-18",
                "ocurrio_el": None,
                "vigente_desde": None,
                "vigente_hasta": None,
                "vigencia": "vigente",
            }
        ],
    }
    (vault / "Conocimiento" / "Documentos" / "Plano A.md").write_text(
        dump_markdown_note(doc_a, "# Plano A"),
        encoding="utf-8",
    )
    (vault / "Conocimiento" / "Documentos" / "Plano B.md").write_text(
        dump_markdown_note(doc_b, "# Plano B"),
        encoding="utf-8",
    )

    report = VaultValidator(vault).validate_all()
    assert any(issue.code == "DEPENDENCY_CYCLE" for issue in report.errors)


def test_id_stability_after_rename_and_rebuild(tmp_path: Path) -> None:
    vault = _copy_vault_to_tmp(tmp_path)
    old_path = vault / "Conocimiento" / "Personas" / "Juan Garcia.md"
    new_path = vault / "Conocimiento" / "Personas" / "Juan Garcia Renombrado.md"
    old_path.rename(new_path)

    mgr = IdManager(vault)
    counters = mgr.rebuild_registry()
    assert counters["per"] == 1
    assert counters["rel"] == 3
    assert mgr.peek_next_node_id("persona") == "per-000002"


def test_entity_resolver_handles_aliases_and_homonyms(tmp_path: Path) -> None:
    vault = _copy_vault_to_tmp(tmp_path)
    # Agregamos un segundo Juan Garcia en ambito profesional para probar no-fusion
    second_juan = {
        "schema_version": "1.0",
        "id": "per-000002",
        "tipo": "persona",
        "subtipo": "colaborador",
        "titulo": "Juan García",
        "aliases": ["Juan de Compras"],
        "ambito": "profesional",
        "estado": "activo",
        "creado_el": "2026-11-18",
        "actualizado_el": "2026-11-18",
        "ocurrio_el": None,
        "registrado_el": "2026-11-18",
        "evidencia": "confirmada",
        "fuente": "[[Test]]",
        "confianza": "alta",
        "relaciones": [],
    }
    (vault / "Conocimiento" / "Personas" / "Juan Garcia Compras.md").write_text(
        dump_markdown_note(second_juan, "# Juan de Compras"),
        encoding="utf-8",
    )

    resolver = EntityResolver(vault)
    res_alias = resolver.resolve("Juan el herrero")
    assert res_alias.status == "unique_match"
    assert res_alias.candidates[0].node_id == "per-000001"

    res_ambig = resolver.resolve("Juan Garcia", tipo="persona")
    assert res_ambig.status == "ambiguous"
    assert {c.node_id for c in res_ambig.candidates} == {"per-000001", "per-000002"}

    res_ctx = resolver.resolve("Juan Garcia", tipo="persona", contexto="profesional")
    assert res_ctx.status == "unique_match"
    assert res_ctx.candidates[0].node_id == "per-000002"


def test_cli_read_only_prevents_writes(tmp_path: Path) -> None:
    vault = _copy_vault_to_tmp(tmp_path)
    registry = vault / "Sistema" / "id_registry.json"
    if registry.exists():
        registry.unlink()

    assert cli_main(["--root", str(vault), "--read-only", "validate"]) == 0
    assert cli_main(["--root", str(vault), "--read-only", "new-id", "persona"]) == 0
    assert not registry.exists()
    assert cli_main(["--root", str(vault), "--read-only", "rebuild-ids"]) == 2


def test_parse_markdown_note_handles_utf8_bom(tmp_path: Path) -> None:
    vault = _copy_vault_to_tmp(tmp_path)
    juan_path = vault / "Conocimiento" / "Personas" / "Juan Garcia.md"
    raw = juan_path.read_text(encoding="utf-8")
    juan_path.write_bytes(b"\xef\xbb\xbf" + raw.encode("utf-8"))
    report = VaultValidator(vault).validate_all()
    assert report.is_valid, [i.to_dict() for i in report.errors]
