"""CLI local del Segundo Cerebro (validacion, staging, commit y resolucion)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.committer import SafeCommitter
from scripts.entity_resolver import EntityResolver
from scripts.id_manager import IdManager
from scripts.indexer import VaultIndex
from scripts.schema_loader import get_workspace_root
from scripts.search_engine import AssociativeSearchEngine
from scripts.staging import StagingManager
from scripts.validator import VaultValidator


def _print_validation_text(report) -> None:
    print(f"Notas verificadas: {report.notes_checked}")
    print(f"Errores: {len(report.errors)} | Advertencias: {len(report.warnings)}")
    for issue in report.issues:
        loc = f" [{issue.path}]" if issue.path else ""
        nid = f" ({issue.node_id})" if issue.node_id else ""
        print(f"  - {issue.severity} {issue.code}{nid}{loc}: {issue.message}")


def _require_writable(args: argparse.Namespace) -> None:
    if args.read_only:
        raise PermissionError(
            f"El subcomando '{args.command}' requiere escritura y fue bloqueado por --read-only."
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="brain_cli",
        description="CLI local del Segundo Cerebro V1.0 (validacion, memoria y resolucion).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Ruta raiz de la boveda (por defecto autodetecta el workspace).",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Garantiza ejecucion estrictamente de solo lectura sin escribir en disco.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emite la salida en formato JSON.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "validate",
        help="Valida esquema YAML, IDs unicos, Wikilinks, duplicados y ciclos (solo lectura).",
    )
    sub.add_parser(
        "check-cycles",
        help="Comprueba ciclos operativos en relaciones depende_de / habilita_a (solo lectura).",
    )

    p_resolve = sub.add_parser(
        "resolve",
        help="Resuelve una entidad por ID, titulo, alias, tipo, proyecto y contexto.",
    )
    p_resolve.add_argument("query", help="Texto o ID a resolver.")
    p_resolve.add_argument("--tipo", default=None, help="Filtrar por clase de nodo.")
    p_resolve.add_argument("--proyecto", default=None, help="Contexto de proyecto.")
    p_resolve.add_argument("--contexto", default=None, help="Contexto adicional.")

    p_id = sub.add_parser(
        "new-id",
        help="Muestra o asigna el proximo ID estable para una clase de nodo.",
    )
    p_id.add_argument("tipo", help="Clase de nodo (ej. persona, proyecto, conocimiento).")

    sub.add_parser(
        "rebuild-ids",
        help="Reconstruye Sistema/id_registry.json desde las notas existentes.",
    )

    p_ingest = sub.add_parser(
        "ingest",
        help="Extrae candidatos desde texto hacia Memoria-Pendiente/ (nunca consolida directo).",
    )
    p_ingest.add_argument("--text", required=True, help="Texto o resumen de sesion a analizar.")
    p_ingest.add_argument("--fuente", required=True, help="Fuente trazable (ej. '[[Sesion 01]]').")
    p_ingest.add_argument("--ambito", default="transversal", help="Ambito inicial.")
    p_ingest.add_argument("--ocurrio-el", default=None, help="Fecha ISO del hecho si se conoce.")
    p_ingest.add_argument("--contexto", default=None, help="Contexto adicional para desambiguacion.")

    p_list = sub.add_parser(
        "list-proposals",
        help="Lista propuestas provisionales en Memoria-Pendiente/Propuestas (solo lectura).",
    )
    p_list.add_argument("--estado", default=None, help="Filtrar por estado.")

    p_app = sub.add_parser(
        "approve-proposal",
        help="Marca una propuesta especifica como 'aprobada'.",
    )
    p_app.add_argument("prop_id", help="ID de la propuesta (ej. prop-000001).")

    p_disc = sub.add_parser(
        "discard-proposal",
        help="Marca una propuesta especifica como 'descartada'.",
    )
    p_disc.add_argument("prop_id", help="ID de la propuesta (ej. prop-000001).")
    p_disc.add_argument("--reason", default=None, help="Motivo opcional del descarte.")

    p_prep = sub.add_parser(
        "prepare-commit",
        help="Genera Dry-Run con diff y hash SHA-256 previo para propuestas aprobadas.",
    )
    p_prep.add_argument("prop_ids", nargs="+", help="IDs exactos de propuestas aprobadas.")
    p_prep.add_argument(
        "--allow-actions",
        action="store_true",
        help="Permite incluir nodos 'accion' solicitados explicitamente por el usuario.",
    )

    p_apply = sub.add_parser(
        "apply-commit",
        help="Aplica un lote Dry-Run validado exigiendo --confirm.",
    )
    p_apply.add_argument("--batch", required=True, help="ID del lote Dry-Run (ej. batch-20261118-001).")
    p_apply.add_argument(
        "--confirm",
        action="store_true",
        help="Confirmacion explicita requerida para escribir en Conocimiento/ o Historia/.",
    )

    sub.add_parser(
        "rebuild-index",
        help="Reconstruye Indices/brain_index.sqlite desde los archivos Markdown.",
    )

    p_search = sub.add_parser(
        "search",
        help="Busca hechos, inferencias y oportunidades contextuales en toda la boveda (solo lectura).",
    )
    p_search.add_argument("query", help="Consulta en lenguaje natural.")
    p_search.add_argument("--exploratory", action="store_true", help="Activa modo exploratorio.")
    p_search.add_argument("--tipo", default=None, help="Filtrar semillas por tipo de nodo.")
    p_search.add_argument("--ambito", default=None, help="Filtrar semillas por ambito.")
    p_search.add_argument("--max-depth", type=int, default=None, help="Profundidad maxima de grafo.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = get_workspace_root(args.root)

    try:
        if args.command == "validate":
            report = VaultValidator(root).validate_all()
            if args.json:
                print(
                    json.dumps(
                        {
                            "notes_checked": report.notes_checked,
                            "valid": report.is_valid,
                            "errors": [i.to_dict() for i in report.errors],
                            "warnings": [i.to_dict() for i in report.warnings],
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            else:
                _print_validation_text(report)
            return 0 if report.is_valid else 1

        if args.command == "check-cycles":
            report = VaultValidator(root).validate_all()
            cycles = [i for i in report.issues if i.code == "DEPENDENCY_CYCLE"]
            if args.json:
                print(json.dumps([c.to_dict() for c in cycles], indent=2, ensure_ascii=False))
            else:
                if not cycles:
                    print("Sin ciclos operativos detectados.")
                for c in cycles:
                    print(f"  - {c.severity} {c.code}: {c.message}")
            return 0 if not cycles else 1

        if args.command == "resolve":
            res = EntityResolver(root).resolve(
                args.query,
                tipo=args.tipo,
                proyecto=args.proyecto,
                contexto=args.contexto,
            )
            payload = {
                "query": res.query,
                "status": res.status,
                "candidates": [
                    {
                        "id": c.node_id,
                        "tipo": c.tipo,
                        "subtipo": c.subtipo,
                        "titulo": c.titulo,
                        "aliases": c.aliases,
                        "ambito": c.ambito,
                        "path": str(c.path),
                        "score": c.score,
                        "reasons": c.reasons,
                    }
                    for c in res.candidates
                ],
            }
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print(f"Consulta: '{res.query}' -> estado: {res.status}")
                for c in res.candidates:
                    print(
                        f"  - {c.node_id} [{c.tipo}] {c.titulo} "
                        f"(score={c.score}) :: {', '.join(c.reasons)}"
                    )
            return 0 if res.status != "not_found" else 2

        if args.command == "new-id":
            mgr = IdManager(root)
            if args.read_only:
                next_id = mgr.peek_next_node_id(args.tipo)
                mode = "read-only (simulado)"
            else:
                next_id = mgr.allocate_node_id(args.tipo, persist=True)
                mode = "asignado"
            if args.json:
                print(json.dumps({"tipo": args.tipo, "id": next_id, "mode": mode}, ensure_ascii=False))
            else:
                print(f"{next_id} ({mode})")
            return 0

        if args.command == "rebuild-ids":
            _require_writable(args)
            counters = IdManager(root).rebuild_registry()
            if args.json:
                print(json.dumps(counters, indent=2, ensure_ascii=False))
            else:
                print(f"Registro reconstruido: {counters}")
            return 0

        if args.command == "ingest":
            _require_writable(args)
            summary = StagingManager(root).ingest_text(
                args.text,
                fuente=args.fuente,
                ocurrio_el=args.ocurrio_el,
                ambito=args.ambito,
                contexto=args.contexto,
            )
            payload = {
                "created_proposals": summary.created_proposals,
                "created_questions": summary.created_questions,
                "skipped_duplicates": summary.skipped_duplicates,
                "ignored_trivial": summary.ignored_trivial,
            }
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print(
                    f"Propuestas: {summary.created_proposals} | "
                    f"Preguntas: {summary.created_questions} | "
                    f"Duplicados omitidos: {summary.skipped_duplicates} | "
                    f"Triviales ignorados: {summary.ignored_trivial}"
                )
            return 0

        if args.command == "list-proposals":
            items = StagingManager(root).list_proposals(estado=args.estado)
            if args.json:
                print(json.dumps(items, indent=2, ensure_ascii=False))
            else:
                print(f"Propuestas encontradas: {len(items)}")
                for item in items:
                    print(
                        f"  - {item['id']} [{item['estado']}] "
                        f"{item.get('op_type')}: {item.get('target_titulo')} "
                        f"-> {item.get('predicado') or '-'} {item.get('destino_titulo') or ''}"
                    )
            return 0

        if args.command == "approve-proposal":
            _require_writable(args)
            prop = StagingManager(root).approve_proposal(args.prop_id)
            if args.json:
                print(json.dumps(prop, indent=2, ensure_ascii=False))
            else:
                print(f"Propuesta aprobada: {prop['id']} [{prop['estado']}]")
            return 0

        if args.command == "discard-proposal":
            _require_writable(args)
            prop = StagingManager(root).discard_proposal(args.prop_id, reason=args.reason)
            if args.json:
                print(json.dumps(prop, indent=2, ensure_ascii=False))
            else:
                print(f"Propuesta descartada: {prop['id']} [{prop['estado']}]")
            return 0

        if args.command == "prepare-commit":
            _require_writable(args)
            manifest = SafeCommitter(root).prepare_commit(
                args.prop_ids,
                allow_actions=args.allow_actions,
            )
            if args.json:
                print(json.dumps(manifest, indent=2, ensure_ascii=False))
            else:
                print(f"Dry-Run preparado: {manifest['batch_id']} ({len(manifest['changes'])} archivos)")
                for ch in manifest["changes"]:
                    print(f"  * {ch['action'].upper()} {ch['relative_path']} (prev={ch['prev_sha256'][:12]})")
                    if ch["diff"]:
                        print(ch["diff"])
            return 0

        if args.command == "apply-commit":
            _require_writable(args)
            manifest = SafeCommitter(root).apply_commit(args.batch, confirm=args.confirm)
            if args.json:
                print(json.dumps(manifest, indent=2, ensure_ascii=False))
            else:
                print(f"Lote aplicado: {manifest['batch_id']} -> archivos: {manifest.get('written_files', [])}")
            return 0

        if args.command == "rebuild-index":
            _require_writable(args)
            stats = VaultIndex(root).rebuild()
            if args.json:
                print(json.dumps(stats, indent=2, ensure_ascii=False))
            else:
                print(
                    f"Indice reconstruido: {stats['nodes_indexed']} nodos, "
                    f"{stats['edges_indexed']} aristas (FTS5={stats['has_fts5']})"
                )
            return 0

        if args.command == "search":
            report = AssociativeSearchEngine(root).search(
                args.query,
                exploratory=args.exploratory,
                tipo=args.tipo,
                ambito=args.ambito,
                max_depth=args.max_depth,
            )
            if args.json:
                print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
            else:
                print(f"Consulta [{report.mode} | {report.intent}]: {report.query}")
                print(f"Hechos declarados: {len(report.declared_facts)}")
                for f in report.declared_facts:
                    print(f"  - {f['id']} [{f['tipo']}] {f['titulo']} (fuente={f['fuente']}, path={f['path']})")
                print(f"Inferencias: {len(report.inferences)}")
                for inf in report.inferences:
                    print(f"  - {inf['origen_titulo']} -> {inf['destino_titulo']} ({inf['saltos']} saltos)")
                print(f"Oportunidades sugeridas: {len(report.suggested_opportunities)}")
                for opp in report.suggested_opportunities:
                    warn = f" | AVISO: {', '.join(opp['advertencias'])}" if opp["advertencias"] else ""
                    print(
                        f"  * {opp['candidato_id']} {opp['candidato_titulo']} "
                        f"(score={opp['pertinencia_score']}, fuentes={opp['fuentes']}{warn})"
                    )
                    print(f"    {opp['explicacion']}")
                if report.missing_information:
                    print(f"Informacion faltante / avisos: {report.missing_information}")
            return 0
    except PermissionError as exc:
        print(f"Bloqueado por politica de permisos: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
