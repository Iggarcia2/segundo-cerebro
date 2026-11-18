"""Motor de busqueda global, expansion de grafo y oportunidades contextuales."""

from __future__ import annotations

import json
import re
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.entity_resolver import normalize_text
from scripts.indexer import VaultIndex
from scripts.schema_loader import get_workspace_root

SPANISH_STOPWORDS = {
    "a",
    "al",
    "algo",
    "alguien",
    "ante",
    "ayudar",
    "busco",
    "buscar",
    "busca",
    "con",
    "como",
    "cual",
    "de",
    "del",
    "desde",
    "donde",
    "el",
    "ella",
    "en",
    "entre",
    "es",
    "esta",
    "este",
    "esto",
    "falta",
    "hay",
    "la",
    "las",
    "le",
    "lo",
    "los",
    "me",
    "mi",
    "necesito",
    "necesita",
    "necesitamos",
    "o",
    "para",
    "pero",
    "por",
    "proyecto",
    "puede",
    "que",
    "quien",
    "se",
    "si",
    "sin",
    "sobre",
    "su",
    "sus",
    "tengo",
    "tiene",
    "un",
    "una",
    "unos",
    "unas",
    "y",
}


def extract_query_terms(query: str) -> list[str]:
    """Extrae terminos normalizados significativos de una consulta en lenguaje natural."""
    norm = normalize_text(query)
    raw_tokens = re.findall(r"[a-z0-9_]+", norm)
    terms: list[str] = []
    seen: set[str] = set()
    for tok in raw_tokens:
        if len(tok) < 3 or tok in SPANISH_STOPWORDS:
            continue
        if tok not in seen:
            seen.add(tok)
            terms.append(tok)
    return terms


@dataclass
class SearchReport:
    """Resultado estructurado separando hechos declarados, inferencias y oportunidades."""

    query: str
    mode: str  # normal | exploratory
    terms: list[str]
    intent: str
    declared_facts: list[dict[str, Any]] = field(default_factory=list)
    inferences: list[dict[str, Any]] = field(default_factory=list)
    suggested_opportunities: list[dict[str, Any]] = field(default_factory=list)
    queries_executed: list[str] = field(default_factory=list)
    nodes_visited: int = 0
    missing_information: list[str] = field(default_factory=list)
    actions_created: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "mode": self.mode,
            "terms": self.terms,
            "intent": self.intent,
            "declared_facts": self.declared_facts,
            "inferences": self.inferences,
            "suggested_opportunities": self.suggested_opportunities,
            "queries_executed": self.queries_executed,
            "nodes_visited": self.nodes_visited,
            "missing_information": self.missing_information,
            "actions_created": self.actions_created,
        }


class AssociativeSearchEngine:
    """Motor progresivo lexical + metadatos + grafo dirigido e inverso."""

    def __init__(self, root: Path | None = None, *, index_path: Path | None = None) -> None:
        self.root = get_workspace_root(root)
        self.index = VaultIndex(self.root, db_path=index_path)

    @staticmethod
    def _detect_intent(query: str) -> str:
        low = normalize_text(query)
        if any(w in low for w in ("quien", "contacto", "especialista", "fabricar", "hacer", "capacidad", "ayudar")):
            return "locate_capability_or_person"
        if any(w in low for w in ("bloqueo", "estado", "dependencia", "riesgo", "diagnostico")):
            return "project_diagnosis"
        if any(w in low for w in ("cuando", "cambio", "historia", "decision")):
            return "temporal_or_decision"
        return "general_associative"

    @staticmethod
    def _vigencia_warning(vigencia: str) -> str | None:
        if vigencia == "desconocida":
            return "Vigencia desconocida: verificar actualidad antes de asumir disponibilidad."
        if vigencia == "historica":
            return "Relacion historica (no vigente actualmente)."
        if vigencia == "disputada":
            return "Vigencia disputada: existen datos contradictorios."
        return None

    def _lexical_seed_nodes(
        self,
        conn,
        terms: list[str],
        *,
        tipo: str | None = None,
        ambito: str | None = None,
    ) -> tuple[list[tuple[dict[str, Any], float, list[str]]], list[str]]:
        """Busca nodos semilla por titulo, alias, metadatos y texto completo."""
        queries_executed: list[str] = []
        rows = conn.execute("SELECT * FROM nodes").fetchall()
        queries_executed.append("SELECT * FROM nodes (indice lexical y metadatos transversal)")

        fts_hits: set[str] = set()
        if terms:
            try:
                fts_expr = " OR ".join(f"{t}*" for t in terms)
                fts_rows = conn.execute(
                    "SELECT id FROM nodes_fts WHERE nodes_fts MATCH ?",
                    (fts_expr,),
                ).fetchall()
                fts_hits = {r["id"] for r in fts_rows}
                queries_executed.append(f"FTS5 MATCH ({fts_expr})")
            except Exception:
                pass

        scored: list[tuple[dict[str, Any], float, list[str]]] = []
        for r in rows:
            node = dict(r)
            if tipo and node["tipo"] != tipo:
                continue
            if ambito and node["ambito"] != ambito:
                continue

            aliases = json.loads(node["aliases_json"])
            tags = json.loads(node["tags_json"])
            title_norm = node["titulo_norm"]
            aliases_norm = node["aliases_norm"]
            body_norm = node["body_norm"]
            tags_norm = normalize_text(" ".join(tags))

            score = 0.0
            reasons: list[str] = []
            matched_terms: list[str] = []

            for term in terms:
                if term in title_norm.split():
                    score += 3.0
                    matched_terms.append(term)
                    reasons.append(f"termino exacto '{term}' en titulo")
                elif term in title_norm:
                    score += 2.2
                    matched_terms.append(term)
                    reasons.append(f"coincidencia '{term}' en titulo")
                elif term in aliases_norm:
                    score += 2.5
                    matched_terms.append(term)
                    reasons.append(f"coincidencia '{term}' en alias")
                elif term in tags_norm:
                    score += 1.4
                    matched_terms.append(term)
                    reasons.append(f"coincidencia '{term}' en tags")
                elif term in body_norm:
                    score += 0.9
                    matched_terms.append(term)
                    reasons.append(f"coincidencia '{term}' en texto completo")

            if node["id"] in fts_hits and score > 0:
                score += 0.4

            if len(set(matched_terms)) >= 2:
                score += 0.8

            if score > 0:
                node["aliases"] = aliases
                node["matched_terms"] = sorted(set(matched_terms))
                scored.append((node, round(score, 3), reasons))

        scored.sort(key=lambda item: (-item[1], item[0]["id"]))
        return scored, queries_executed

    def search(
        self,
        query: str,
        *,
        exploratory: bool = False,
        tipo: str | None = None,
        ambito: str | None = None,
        max_depth: int | None = None,
        max_nodes: int | None = None,
        timeout_ms: int = 1500,
    ) -> SearchReport:
        """Ejecuta recuperacion progresiva respetando limites y separando certeza."""
        start_time = time.monotonic()
        mode = "exploratory" if exploratory else "normal"
        depth_limit = max_depth if max_depth is not None else (3 if exploratory else 2)
        node_limit = max_nodes if max_nodes is not None else (150 if exploratory else 50)
        max_suggestions = 8 if exploratory else 2

        terms = extract_query_terms(query)
        intent = self._detect_intent(query)
        report = SearchReport(
            query=query,
            mode=mode,
            terms=terms,
            intent=intent,
        )

        conn = self.index.open_for_read()
        try:
            all_nodes = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM nodes").fetchall()}
            all_edges = [dict(r) for r in conn.execute("SELECT * FROM edges").fetchall()]

            out_adj: dict[str, list[dict[str, Any]]] = {}
            in_adj: dict[str, list[dict[str, Any]]] = {}
            for edge in all_edges:
                out_adj.setdefault(edge["src_id"], []).append(edge)
                in_adj.setdefault(edge["dst_id"], []).append(edge)

            seeds, q_logs = self._lexical_seed_nodes(conn, terms, tipo=tipo, ambito=ambito)
            report.queries_executed.extend(q_logs)

            if not seeds:
                report.missing_information.append(
                    f"No se encontraron nodos que coincidan con los terminos {terms or [query]}."
                )
                return report

            top_seeds = seeds[: (12 if exploratory else 6)]
            for node, score, reasons in top_seeds:
                declared_rels = []
                for edge in out_adj.get(node["id"], []):
                    warn = self._vigencia_warning(edge["vigencia"])
                    declared_rels.append(
                        {
                            "rel_id": edge["rel_id"],
                            "predicado": edge["predicado"],
                            "destino_id": edge["dst_id"],
                            "destino": edge["dst_titulo"],
                            "evidencia": edge["evidencia"],
                            "fuente": edge["fuente"],
                            "vigencia": edge["vigencia"],
                            "advertencia": warn,
                        }
                    )
                report.declared_facts.append(
                    {
                        "id": node["id"],
                        "tipo": node["tipo"],
                        "titulo": node["titulo"],
                        "ambito": node["ambito"],
                        "estado": node["estado"],
                        "path": node["path"],
                        "fuente": node["fuente"],
                        "evidencia": node["evidencia"],
                        "score_lexical": score,
                        "motivos_coincidencia": reasons,
                        "relaciones_salientes": declared_rels,
                    }
                )

            visited_order: list[str] = []
            visited_set: set[str] = set()
            seen_states: set[tuple[str, str | None, int]] = set()
            queue: deque[tuple[str, int, list[dict[str, Any]]]] = deque()
            seed_scores = {node["id"]: score for node, score, _ in top_seeds}

            for node, _score, _reasons in top_seeds:
                nid = node["id"]
                if nid not in visited_set:
                    visited_set.add(nid)
                    visited_order.append(nid)
                    seen_states.add((nid, None, 0))
                    queue.append((nid, 0, []))

            inferred_paths: list[dict[str, Any]] = []
            opportunity_candidates: list[dict[str, Any]] = []
            seen_opportunities: set[tuple[str, str]] = set()
            seen_inferences: set[tuple[str, ...]] = set()
            expansions = 0

            while queue:
                elapsed_ms = (time.monotonic() - start_time) * 1000
                if elapsed_ms >= timeout_ms or expansions >= node_limit * 4:
                    break

                cur_id, depth, path_steps = queue.popleft()
                expansions += 1
                if depth >= depth_limit:
                    continue

                path_node_ids = {cur_id} | {s["from_id"] for s in path_steps} | {s["to_id"] for s in path_steps}

                neighbors: list[tuple[str, dict[str, Any], str]] = []
                for edge in out_adj.get(cur_id, []):
                    neighbors.append((edge["dst_id"], edge, "directa"))
                for edge in in_adj.get(cur_id, []):
                    neighbors.append((edge["src_id"], edge, "inversa"))

                for nxt_id, edge, direction in neighbors:
                    if nxt_id not in all_nodes or nxt_id in path_node_ids:
                        continue

                    step = {
                        "from_id": cur_id,
                        "from_titulo": all_nodes[cur_id]["titulo"],
                        "direction": direction,
                        "predicado": edge["predicado"] if direction == "directa" else edge["inversa"],
                        "predicado_original": edge["predicado"],
                        "to_id": nxt_id,
                        "to_titulo": all_nodes[nxt_id]["titulo"],
                        "evidencia": edge["evidencia"],
                        "fuente": edge["fuente"],
                        "vigencia": edge["vigencia"],
                    }
                    new_path = path_steps + [step]

                    if len(new_path) >= 2:
                        sig = tuple(
                            f"{s['from_id']}-{s['predicado']}-{s['to_id']}" for s in new_path
                        )
                        if sig not in seen_inferences:
                            seen_inferences.add(sig)
                            warnings = [
                                w
                                for w in (self._vigencia_warning(s["vigencia"]) for s in new_path)
                                if w is not None
                            ]
                            inferred_paths.append(
                                {
                                    "origen_id": new_path[0]["from_id"],
                                    "origen_titulo": new_path[0]["from_titulo"],
                                    "destino_id": nxt_id,
                                    "destino_titulo": all_nodes[nxt_id]["titulo"],
                                    "saltos": len(new_path),
                                    "camino": new_path,
                                    "fuentes": sorted({s["fuente"] for s in new_path}),
                                    "advertencias_vigencia": sorted(set(warnings)),
                                }
                            )

                    nxt_node = all_nodes[nxt_id]
                    if nxt_node["tipo"] in ("persona", "organizacion", "recurso"):
                        preds_used = [s["predicado_original"] for s in new_path]
                        has_functional_link = any(
                            p in ("tiene_capacidad", "satisface", "requiere", "responsable_de", "participa_en")
                            for p in preds_used
                        )
                        if has_functional_link or exploratory:
                            root_id = new_path[0]["from_id"]
                            opp_key = (nxt_id, root_id)
                            if opp_key not in seen_opportunities:
                                seen_opportunities.add(opp_key)
                                base_seed_score = seed_scores.get(root_id, 1.0)
                                functional_bonus = (
                                    2.0
                                    if "tiene_capacidad" in preds_used or "satisface" in preds_used
                                    else 0.5
                                )
                                irrelevance_penalty = 0.0
                                if all(p == "relacionado_con" for p in preds_used):
                                    irrelevance_penalty = 2.5
                                if edge["vigencia"] == "historica":
                                    irrelevance_penalty += 1.5

                                rel_score = round(
                                    base_seed_score
                                    + functional_bonus
                                    - 0.35 * len(new_path)
                                    - irrelevance_penalty,
                                    3,
                                )
                                warnings = [
                                    w
                                    for w in (self._vigencia_warning(s["vigencia"]) for s in new_path)
                                    if w is not None
                                ]
                                path_desc = " -> ".join(
                                    [new_path[0]["from_titulo"]]
                                    + [f"({s['predicado']}) {s['to_titulo']}" for s in new_path]
                                )
                                opportunity_candidates.append(
                                    {
                                        "candidato_id": nxt_id,
                                        "candidato_tipo": nxt_node["tipo"],
                                        "candidato_titulo": nxt_node["titulo"],
                                        "candidato_ambito": nxt_node["ambito"],
                                        "candidato_path": nxt_node["path"],
                                        "desde_nodo_id": root_id,
                                        "desde_nodo_titulo": all_nodes[root_id]["titulo"],
                                        "pertinencia_score": rel_score,
                                        "explicacion": (
                                            f"Conectado por camino de {len(new_path)} salto(s): {path_desc}. "
                                            "No se asume disponibilidad ni experiencia fuera de las fuentes citadas."
                                        ),
                                        "camino": new_path,
                                        "fuentes": sorted({s["fuente"] for s in new_path}),
                                        "advertencias": sorted(set(warnings)),
                                        "nivel_certeza": "oportunidad_sugerida",
                                    }
                                )

                    if nxt_id not in visited_set and len(visited_order) < node_limit:
                        visited_set.add(nxt_id)
                        visited_order.append(nxt_id)

                    state_key = (nxt_id, cur_id, depth + 1)
                    if state_key not in seen_states and len(visited_order) <= node_limit:
                        seen_states.add(state_key)
                        queue.append((nxt_id, depth + 1, new_path))

            for node, base_score, _ in top_seeds:
                nid = node["id"]
                for edge in in_adj.get(nid, []):
                    src_id = edge["src_id"]
                    if src_id not in all_nodes:
                        continue
                    src_node = all_nodes[src_id]
                    if src_node["tipo"] in ("persona", "organizacion", "recurso") and edge["predicado"] in (
                        "tiene_capacidad",
                        "satisface",
                        "responsable_de",
                    ):
                        opp_key = (src_id, nid)
                        if opp_key not in seen_opportunities:
                            seen_opportunities.add(opp_key)
                            warn = self._vigencia_warning(edge["vigencia"])
                            penalty = 1.5 if edge["vigencia"] == "historica" else 0.0
                            opportunity_candidates.append(
                                {
                                    "candidato_id": src_id,
                                    "candidato_tipo": src_node["tipo"],
                                    "candidato_titulo": src_node["titulo"],
                                    "candidato_ambito": src_node["ambito"],
                                    "candidato_path": src_node["path"],
                                    "desde_nodo_id": nid,
                                    "desde_nodo_titulo": node["titulo"],
                                    "pertinencia_score": round(base_score + 1.8 - penalty, 3),
                                    "explicacion": (
                                        f"{src_node['titulo']} tiene relacion '{edge['predicado']}' con "
                                        f"{node['titulo']}. No implica disponibilidad automatica."
                                    ),
                                    "camino": [
                                        {
                                            "from_id": nid,
                                            "from_titulo": node["titulo"],
                                            "direction": "inversa",
                                            "predicado": edge["inversa"],
                                            "predicado_original": edge["predicado"],
                                            "to_id": src_id,
                                            "to_titulo": src_node["titulo"],
                                            "evidencia": edge["evidencia"],
                                            "fuente": edge["fuente"],
                                            "vigencia": edge["vigencia"],
                                        }
                                    ],
                                    "fuentes": [edge["fuente"]],
                                    "advertencias": [warn] if warn else [],
                                    "nivel_certeza": "oportunidad_sugerida",
                                }
                            )

            report.nodes_visited = len(visited_order)
            report.queries_executed.append(
                f"BFS grafo dirigido+inverso (profundidad<={depth_limit}, limite_nodos={node_limit}, visitados={len(visited_order)})"
            )

            min_threshold = 0.0 if exploratory else 1.5
            filtered_opps = [
                opp for opp in opportunity_candidates if opp["pertinencia_score"] >= min_threshold
            ]
            filtered_opps.sort(key=lambda o: (-o["pertinencia_score"], o["candidato_id"]))
            dedup_opps: list[dict[str, Any]] = []
            seen_cand_ids: set[str] = set()
            for opp in filtered_opps:
                if opp["candidato_id"] not in seen_cand_ids:
                    seen_cand_ids.add(opp["candidato_id"])
                    dedup_opps.append(opp)

            report.inferences = inferred_paths[: (20 if exploratory else 8)]
            report.suggested_opportunities = dedup_opps[:max_suggestions]

            for opp in report.suggested_opportunities:
                if opp["advertencias"]:
                    report.missing_information.append(
                        f"Confirmar vigencia/disponibilidad de '{opp['candidato_titulo']}' ({opp['candidato_id']})."
                    )

            titles_seen: dict[str, list[str]] = {}
            for fact in report.declared_facts:
                t_norm = normalize_text(fact["titulo"])
                titles_seen.setdefault(t_norm, []).append(fact["id"])
            for _t_norm, ids in titles_seen.items():
                if len(ids) > 1:
                    report.missing_information.append(
                        f"Coinciden multiples entidades distintas con nombre similar ({', '.join(ids)}); mantenidas separadas."
                    )

            return report
        finally:
            conn.close()
