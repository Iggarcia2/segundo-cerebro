"""Pruebas unitarias de la etapa B3 (indice, grafo y demostraciones asociativas)."""

from __future__ import annotations

import shutil
from pathlib import Path

from scripts.brain_cli import main as cli_main
from scripts.indexer import VaultIndex
from scripts.markdown_io import dump_markdown_note
from scripts.schema_loader import get_workspace_root
from scripts.search_engine import AssociativeSearchEngine


def _setup_b3_vault(tmp_path: Path) -> Path:
    src_root = get_workspace_root()
    dst_root = tmp_path / "vault_b3"
    shutil.copytree(src_root / "Sistema", dst_root / "Sistema")
    shutil.copytree(src_root / "Conocimiento", dst_root / "Conocimiento")
    (dst_root / "Historia" / "Eventos").mkdir(parents=True, exist_ok=True)
    (dst_root / "Indices").mkdir(parents=True, exist_ok=True)
    return dst_root


def _write_note(vault: Path, rel_path: str, fm: dict, body: str) -> None:
    target = vault / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dump_markdown_note(fm, body), encoding="utf-8")


def test_demo1_and_demo3_juan_garcia_herreria_with_vigencia_warning(tmp_path: Path) -> None:
    vault = _setup_b3_vault(tmp_path)
    VaultIndex(vault).rebuild()

    engine = AssociativeSearchEngine(vault)
    report = engine.search(
        "necesito fabricar una estructura metalica para el proyecto Ampliacion Taller Sur"
    )

    assert report.actions_created == 0
    assert report.declared_facts
    assert report.inferences

    # Sugiere a Juan Garcia via Herreria -> Estructura soporte puente grua
    opp_ids = [o["candidato_id"] for o in report.suggested_opportunities]
    assert "per-000001" in opp_ids
    juan_opp = next(o for o in report.suggested_opportunities if o["candidato_id"] == "per-000001")
    assert "[[Conversación ficticia 01]]" in juan_opp["fuentes"]
    assert any("Vigencia desconocida" in w for w in juan_opp["advertencias"])
    assert juan_opp["nivel_certeza"] == "oportunidad_sugerida"
    assert report.missing_information


def test_demo2_same_name_different_scopes_never_merged(tmp_path: Path) -> None:
    vault = _setup_b3_vault(tmp_path)
    _write_note(
        vault,
        "Conocimiento/Personas/Juan Garcia Compras.md",
        {
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
            "fuente": "[[Legajo Compras]]",
            "confianza": "alta",
            "tags": ["ficticio"],
            "relaciones": [],
        },
        "# Juan Garcia (Compras)\nContacto administrativo profesional.",
    )
    VaultIndex(vault).rebuild()

    report = AssociativeSearchEngine(vault).search("Juan Garcia")
    fact_ids = [f["id"] for f in report.declared_facts]
    assert "per-000001" in fact_ids
    assert "per-000002" in fact_ids
    assert any("multiples entidades distintas" in msg for msg in report.missing_information)


def test_demo4_irrelevant_relation_not_suggested_in_normal_mode(tmp_path: Path) -> None:
    vault = _setup_b3_vault(tmp_path)
    # Carlos solo tiene relacionado_con generico hacia Ampliacion Taller Sur, sin nexo funcional
    _write_note(
        vault,
        "Conocimiento/Personas/Carlos Vecino.md",
        {
            "schema_version": "1.0",
            "id": "per-000003",
            "tipo": "persona",
            "subtipo": "contacto",
            "titulo": "Carlos Vecino",
            "aliases": [],
            "ambito": "personal",
            "estado": "activo",
            "creado_el": "2026-11-18",
            "actualizado_el": "2026-11-18",
            "ocurrio_el": None,
            "registrado_el": "2026-11-18",
            "evidencia": "reportada",
            "fuente": "[[Charla Cafe]]",
            "confianza": "media",
            "tags": ["ficticio"],
            "relaciones": [
                {
                    "id": "rel-000010",
                    "predicado": "relacionado_con",
                    "destino_id": "pro-000001",
                    "destino": "[[Ampliación Taller Sur]]",
                    "evidencia": "reportada",
                    "fuente": "[[Charla Cafe]]",
                    "registrado_el": "2026-11-18",
                    "ocurrio_el": None,
                    "vigente_desde": None,
                    "vigente_hasta": None,
                    "vigencia": "desconocida",
                }
            ],
        },
        "# Carlos Vecino\nMencionado de pasada sin relacion tecnica con estructura ni herreria.",
    )
    VaultIndex(vault).rebuild()

    engine = AssociativeSearchEngine(vault)
    normal = engine.search(
        "necesito fabricar una estructura metalica para Ampliacion Taller Sur",
        exploratory=False,
    )
    normal_ids = [o["candidato_id"] for o in normal.suggested_opportunities]
    assert "per-000001" in normal_ids
    assert "per-000003" not in normal_ids

    exploratory = engine.search(
        "necesito fabricar una estructura metalica para Ampliacion Taller Sur",
        exploratory=True,
    )
    assert len(exploratory.suggested_opportunities) >= len(normal.suggested_opportunities)


def test_demo5_industrial_project_recovers_cross_scope_knowledge(tmp_path: Path) -> None:
    vault = _setup_b3_vault(tmp_path)
    _write_note(
        vault,
        "Conocimiento/Conocimientos/Diseno CAD 3D.md",
        {
            "schema_version": "1.0",
            "id": "con-000002",
            "tipo": "conocimiento",
            "subtipo": "habilidad",
            "titulo": "Diseño CAD 3D",
            "aliases": ["modelado 3d"],
            "ambito": "transversal",
            "estado": "activo",
            "creado_el": "2026-11-18",
            "actualizado_el": "2026-11-18",
            "ocurrio_el": None,
            "registrado_el": "2026-11-18",
            "evidencia": "confirmada",
            "fuente": "[[Nota Personal]]",
            "confianza": "alta",
            "tags": ["ficticio"],
            "relaciones": [],
        },
        "# Diseño CAD 3D\nModelado parametrico de piezas.",
    )
    _write_note(
        vault,
        "Conocimiento/Personas/Ana Gomez.md",
        {
            "schema_version": "1.0",
            "id": "per-000004",
            "tipo": "persona",
            "subtipo": "especialista",
            "titulo": "Ana Gómez",
            "aliases": [],
            "ambito": "personal",
            "estado": "activo",
            "creado_el": "2026-11-18",
            "actualizado_el": "2026-11-18",
            "ocurrio_el": None,
            "registrado_el": "2026-11-18",
            "evidencia": "confirmada",
            "fuente": "[[Charla Club]]",
            "confianza": "alta",
            "tags": ["ficticio"],
            "relaciones": [
                {
                    "id": "rel-000011",
                    "predicado": "tiene_capacidad",
                    "destino_id": "con-000002",
                    "destino": "[[Diseño CAD 3D]]",
                    "evidencia": "confirmada",
                    "fuente": "[[Charla Club]]",
                    "registrado_el": "2026-11-18",
                    "ocurrio_el": None,
                    "vigente_desde": "2026-10-01",
                    "vigente_hasta": None,
                    "vigencia": "vigente",
                }
            ],
        },
        "# Ana Gomez\nConocida en ambito personal.",
    )
    _write_note(
        vault,
        "Conocimiento/Necesidades/Modelado tolva inoxidable.md",
        {
            "schema_version": "1.0",
            "id": "nec-000002",
            "tipo": "necesidad",
            "subtipo": "tecnica",
            "titulo": "Modelado tolva inoxidable",
            "aliases": [],
            "ambito": "ingenieria",
            "estado": "pendiente",
            "creado_el": "2026-11-18",
            "actualizado_el": "2026-11-18",
            "ocurrio_el": None,
            "registrado_el": "2026-11-18",
            "evidencia": "confirmada",
            "fuente": "[[Especificación Industrial]]",
            "confianza": "alta",
            "tags": ["ficticio", "industrial"],
            "relaciones": [
                {
                    "id": "rel-000012",
                    "predicado": "requiere",
                    "destino_id": "con-000002",
                    "destino": "[[Diseño CAD 3D]]",
                    "evidencia": "confirmada",
                    "fuente": "[[Especificación Industrial]]",
                    "registrado_el": "2026-11-18",
                    "ocurrio_el": None,
                    "vigente_desde": "2026-11-18",
                    "vigente_hasta": None,
                    "vigencia": "vigente",
                }
            ],
        },
        "# Modelado tolva inoxidable\nRequerimiento de proyecto industrial.",
    )
    VaultIndex(vault).rebuild()

    report = AssociativeSearchEngine(vault).search(
        "En proyecto industrial tenemos necesidad de modelado tolva inoxidable, quien sabe?"
    )
    opp_ids = [o["candidato_id"] for o in report.suggested_opportunities]
    assert "per-000004" in opp_ids
    ana_opp = next(o for o in report.suggested_opportunities if o["candidato_id"] == "per-000004")
    assert ana_opp["candidato_ambito"] == "personal"
    assert "[[Charla Club]]" in ana_opp["fuentes"]
    assert report.actions_created == 0


def test_cli_rebuild_index_and_search_read_only(tmp_path: Path) -> None:
    vault = _setup_b3_vault(tmp_path)
    assert cli_main(["--root", str(vault), "--read-only", "rebuild-index"]) == 2
    assert cli_main(["--root", str(vault), "rebuild-index"]) == 0
    assert (vault / "Indices" / "brain_index.sqlite").exists()
    assert cli_main(["--root", str(vault), "--read-only", "search", "herreria"]) == 0
