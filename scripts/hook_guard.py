"""Hook PreToolUse para reforzar separacion tecnica entre Memoria-Pendiente y memoria consolidada."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.schema_loader import get_workspace_root

PROTECTED_DIRS = ("Conocimiento", "Historia", "Sistema", ".agents", "scripts")
PROTECTED_FILES = ("AGENTS.md",)
AUTO_STAGING_DIRS = ("Memoria-Pendiente", "Indices")


def evaluate_tool_call(payload: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    """Evalua una llamada a herramienta y devuelve decision PreToolUse conforme a DEC-T01."""
    ws = get_workspace_root(root)
    tool_call = payload.get("toolCall") or {}
    tool_name = str(tool_call.get("name", ""))
    args = tool_call.get("args") or {}

    if tool_name in ("write_file", "edit_file"):
        raw_path = args.get("Path") or args.get("TargetFile") or args.get("path") or ""
        if not raw_path:
            return {
                "decision": "force_ask",
                "reason": "No se pudo verificar la ruta destino de escritura.",
            }
        target = Path(str(raw_path))
        if not target.is_absolute():
            target = (ws / target).resolve()
        else:
            target = target.resolve()

        if not target.is_relative_to(ws):
            return {
                "decision": "force_ask",
                "reason": f"Ruta fuera del workspace autorizado: {target}",
            }

        for protected in PROTECTED_DIRS:
            if target.is_relative_to((ws / protected).resolve()):
                return {
                    "decision": "force_ask",
                    "reason": (
                        f"Politica DEC-T01/FIX-01: modificacion directa en '{protected}/' requiere "
                        "Dry-Run y confirmacion explicita del usuario."
                    ),
                }

        for protected_file in PROTECTED_FILES:
            if target == (ws / protected_file).resolve():
                return {
                    "decision": "force_ask",
                    "reason": (
                        f"Politica FIX-01: modificacion directa de '{protected_file}' requiere "
                        "confirmacion explicita del usuario."
                    ),
                }

        for allowed in AUTO_STAGING_DIRS:
            if target.is_relative_to((ws / allowed).resolve()):
                return {"decision": "allow"}

        return {
            "decision": "ask",
            "reason": "Escritura en archivo operativo/documentacion fuera de Memoria-Pendiente/.",
        }

    if tool_name == "run_command":
        cmd = str(args.get("CommandLine", ""))
        cmd_low = cmd.lower()
        if "apply-commit" in cmd_low or re.search(
            r"(conocimiento|historia|sistema|\.agents)[\\/]|agents\.md", cmd_low
        ):
            return {
                "decision": "force_ask",
                "reason": (
                    "Politica DEC-T01: comando que consolida o referencia zonas protegidas "
                    "requiere confirmacion explicita."
                ),
            }
        if re.search(
            r"\b(remove-item|del|erase|rmdir|ri|rd|set-content|add-content|out-file|move-item|rename-item)\b",
            cmd_low,
        ) or re.search(r"\bpython(?:3|\.exe)?\s+-c\b", cmd_low):
            return {
                "decision": "force_ask",
                "reason": (
                    "Politica FIX-02: comando destructivo, de escritura directa o inline "
                    "requiere confirmacion explicita."
                ),
            }
        if re.search(r"\bgit\s+(push|reset\s+--hard|clean\s+-f|rm)\b", cmd_low):
            return {
                "decision": "force_ask",
                "reason": "Operacion Git externa o destructiva requiere autorizacion especifica.",
            }
        return {"decision": "ask"}

    return {"decision": "ask"}


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps({"decision": "ask"}))
        return 0
    try:
        payload = json.loads(raw)
        result = evaluate_tool_call(payload)
    except Exception as exc:
        result = {
            "decision": "force_ask",
            "reason": f"Error evaluando hook de seguridad: {exc}",
        }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
