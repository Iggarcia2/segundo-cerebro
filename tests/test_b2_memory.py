"""Pruebas unitarias de la etapa B2 (staging, idempotencia, Dry-Run y consolidacion)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.brain_cli import main as cli_main
from scripts.committer import SafeCommitter
from scripts.markdown_io import parse_markdown_note
from scripts.schema_loader import get_workspace_root
from scripts.staging import StagingManager
from scripts.validator import VaultValidator


def _new_isolated_vault(tmp_path: Path) -> Path:
    src_root = get_workspace_root()
    dst_root = tmp_path / "vault_b2"
    shutil.copytree(src_root / "Sistema", dst_root / "Sistema")
    shutil.copytree(src_root / "Conocimiento", dst_root / "Conocimiento")
    (dst_root / "Historia" / "Eventos").mkdir(parents=True, exist_ok=True)
    (dst_root / "Memoria-Pendiente" / "Propuestas").mkdir(parents=True, exist_ok=True)
    (dst_root / "Memoria-Pendiente" / "Preguntas").mkdir(parents=True, exist_ok=True)
    (dst_root / "Memoria-Pendiente" / "Auditoria").mkdir(parents=True, exist_ok=True)
    return dst_root


def _snapshot_consolidated(vault: Path) -> dict[Path, str]:
    files: dict[Path, str] = {}
    for folder in ("Conocimiento", "Historia"):
        for p in sorted((vault / folder).rglob("*.md")):
            files[p] = p.read_text(encoding="utf-8")
    return files


def test_ingest_only_writes_staging_and_is_idempotent(tmp_path: Path) -> None:
    vault = _new_isolated_vault(tmp_path)
    before = _snapshot_consolidated(vault)

    staging = StagingManager(vault)
    text = (
        "Hola.\n"
        "Ana Perez sabe soldadura TIG.\n"
        "¿Cuando vence el presupuesto de pintura?\n"
        "Gracias."
    )
    first = staging.ingest_text(text, fuente="[[Charla Ficticia 10]]")
    assert len(first.created_proposals) == 1
    assert len(first.created_questions) == 1
    assert first.ignored_trivial == 2

    # Nunca modifica memoria consolidada sin aprobacion
    assert _snapshot_consolidated(vault) == before

    # Reprocesar el mismo texto no duplica propuestas ni preguntas
    second = staging.ingest_text(text, fuente="[[Charla Ficticia 10]]")
    assert second.created_proposals == []
    assert second.created_questions == []
    assert second.skipped_duplicates == 2


def test_control_three_memories_one_discarded_one_approved_one_pending(tmp_path: Path) -> None:
    vault = _new_isolated_vault(tmp_path)
    staging = StagingManager(vault)

    summary = staging.ingest_text(
        (
            "Carlos Gomez sabe carpinteria metalica.\n"
            "Elena Ruiz trabaja en Estudio Sur.\n"
            "Decision: usar acero galvanizado para exterior."
        ),
        fuente="[[Charla Ficticia 11]]",
    )
    assert len(summary.created_proposals) == 3
    p1, p2, p3 = summary.created_proposals

    # Descartar 1, aprobar 1, dejar 1 pendiente
    staging.discard_proposal(p1, reason="Dato de prueba descartado")
    staging.approve_proposal(p2)

    committer = SafeCommitter(vault)
    manifest = committer.prepare_commit([p2])
    assert len(manifest["changes"]) == 2  # Elena Ruiz + Estudio Sur

    # Sin --confirm debe rechazar aplicacion
    with pytest.raises(PermissionError):
        committer.apply_commit(manifest["batch_id"], confirm=False)

    committed = committer.apply_commit(manifest["batch_id"], confirm=True)
    assert committed["status"] == "committed"

    assert staging.get_proposal(p1)["estado"] == "descartada"
    assert staging.get_proposal(p2)["estado"] == "consolidada"
    assert staging.get_proposal(p3)["estado"] == "pendiente"

    assert (vault / "Conocimiento" / "Personas" / "Elena Ruiz.md").exists()
    assert (vault / "Conocimiento" / "Organizaciones" / "Estudio Sur.md").exists()
    assert not (vault / "Conocimiento" / "Personas" / "Carlos Gomez.md").exists()
    assert not (vault / "Conocimiento" / "Decisiones" / "usar acero galvanizado para exterior.md").exists()
    assert VaultValidator(vault).validate_all().is_valid


def test_temporal_correction_preserves_history(tmp_path: Path) -> None:
    vault = _new_isolated_vault(tmp_path)
    staging = StagingManager(vault)
    committer = SafeCommitter(vault)

    s1 = staging.ingest_text(
        "Maria Lopez trabaja en Taller Norte.",
        fuente="[[Charla Ficticia 12]]",
        ocurrio_el="2026-09-01",
    )
    staging.approve_proposal(s1.created_proposals[0])
    m1 = committer.prepare_commit(s1.created_proposals)
    committer.apply_commit(m1["batch_id"], confirm=True)

    s2 = staging.ingest_text(
        "Maria Lopez dejo Taller Norte y ahora trabaja en Taller Sur.",
        fuente="[[Charla Ficticia 13]]",
        ocurrio_el="2026-11-10",
    )
    staging.approve_proposal(s2.created_proposals[0])
    m2 = committer.prepare_commit(s2.created_proposals)
    committer.apply_commit(m2["batch_id"], confirm=True)

    maria_doc = parse_markdown_note(vault / "Conocimiento" / "Personas" / "Maria Lopez.md")
    rels = maria_doc.frontmatter["relaciones"]
    assert len(rels) == 2
    old_rel = next(r for r in rels if r["destino"] == "[[Taller Norte]]")
    new_rel = next(r for r in rels if r["destino"] == "[[Taller Sur]]")
    assert old_rel["vigencia"] == "historica"
    assert old_rel["vigente_hasta"] == "2026-11-10"
    assert new_rel["vigencia"] == "vigente"
    assert new_rel["vigente_desde"] == "2026-11-10"

    events = list((vault / "Historia" / "Eventos").glob("*.md"))
    assert len(events) == 1
    assert VaultValidator(vault).validate_all().is_valid


def test_homonym_ambiguity_marks_requires_clarification(tmp_path: Path) -> None:
    vault = _new_isolated_vault(tmp_path)
    staging = StagingManager(vault)
    committer = SafeCommitter(vault)

    # Creamos un segundo Juan Garcia distinto en ambito profesional
    p_id, _ = staging.queue_candidate(
        {
            "kind": "proposal",
            "op_type": "create_node",
            "target_tipo": "persona",
            "target_subtipo": "colaborador",
            "target_titulo": "Juan García",
            "aliases": ["Juan de Compras"],
            "ambito": "profesional",
            "fuente": "[[Alta Compras]]",
        }
    )
    assert p_id is not None
    # Ya existe un Juan Garcia en la boveda -> debe pedir aclaracion antes de fusionar
    assert staging.get_proposal(p_id)["estado"] == "requiere_aclaracion"

    # Aprobar sin confirmar manualmente que son iguales no ocurre por accidente; si probamos
    # una contradiccion sobre Maria Lopez tampoco se fusiona silenciosamente
    assert committer.staging.get_proposal(p_id)["aclaraciones_pendientes"]


def test_stale_dry_run_aborts_when_file_modified_after_prepare(tmp_path: Path) -> None:
    vault = _new_isolated_vault(tmp_path)
    staging = StagingManager(vault)
    committer = SafeCommitter(vault)

    s = staging.ingest_text("Juan García sabe torno paralelo.", fuente="[[Charla 14]]")
    prop_id = s.created_proposals[0]
    staging.approve_proposal(prop_id)
    manifest = committer.prepare_commit([prop_id])

    juan_path = vault / "Conocimiento" / "Personas" / "Juan Garcia.md"
    juan_path.write_text(
        juan_path.read_text(encoding="utf-8") + "\nModificado externamente.\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Dry-Run obsoleto"):
        committer.apply_commit(manifest["batch_id"], confirm=True)

    # La propuesta no paso a consolidada
    assert staging.get_proposal(prop_id)["estado"] == "aprobada"


def test_partial_write_failure_records_audit_log(tmp_path: Path) -> None:
    vault = _new_isolated_vault(tmp_path)
    staging = StagingManager(vault)
    committer = SafeCommitter(vault)

    s = staging.ingest_text("Laura Diaz sabe electricidad industrial.", fuente="[[Charla 15]]")
    prop_id = s.created_proposals[0]
    staging.approve_proposal(prop_id)
    manifest = committer.prepare_commit([prop_id])

    calls = {"count": 0}

    def flaky_writer(path: Path, content: str) -> None:
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("Disco simulado lleno")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    with pytest.raises(RuntimeError, match="Fallo parcial"):
        committer.apply_commit(manifest["batch_id"], confirm=True, writer_fn=flaky_writer)

    saved_manifest = json.loads(
        (vault / "Memoria-Pendiente" / "Auditoria" / f"{manifest['batch_id']}.json").read_text(
            encoding="utf-8"
        )
    )
    assert saved_manifest["status"] == "partial_failure"
    assert len(saved_manifest["written_files"]) == 1
    assert len(saved_manifest["failed_files"]) == 1


def test_action_requires_explicit_request_and_flag(tmp_path: Path) -> None:
    vault = _new_isolated_vault(tmp_path)
    staging = StagingManager(vault)
    committer = SafeCommitter(vault)

    prop_id, _ = staging.queue_candidate(
        {
            "kind": "proposal",
            "op_type": "create_node",
            "target_tipo": "accion",
            "target_subtipo": "tarea",
            "target_titulo": "Pedir presupuesto a Juan",
            "fuente": "[[Prueba]]",
            "solicitada_por_usuario": False,
        }
    )
    assert prop_id is not None
    staging.approve_proposal(prop_id)
    with pytest.raises(PermissionError):
        committer.prepare_commit([prop_id], allow_actions=True)


def test_cli_end_to_end_b2_workflow(tmp_path: Path) -> None:
    vault = _new_isolated_vault(tmp_path)
    assert (
        cli_main(
            [
                "--root",
                str(vault),
                "ingest",
                "--text",
                "Pedro Gomez sabe plomeria.",
                "--fuente",
                "[[CLI Test]]",
            ]
        )
        == 0
    )
    assert cli_main(["--root", str(vault), "--read-only", "list-proposals"]) == 0
    assert cli_main(["--root", str(vault), "--read-only", "ingest", "--text", "X", "--fuente", "[[Y]]"]) == 2
