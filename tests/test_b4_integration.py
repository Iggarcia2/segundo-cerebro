"""Pruebas de integracion B4: descubrimiento de Rules, Skills y ejecucion real de hooks."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

from scripts.schema_loader import get_workspace_root

EXPECTED_RULES = ("memoria.md", "seguridad.md", "temporalidad.md")
EXPECTED_SKILLS = (
    "recordar",
    "asociar",
    "revisar-memoria",
    "analizar-proyectos",
    "gestionar-acciones",
    "cerrar-sesion",
)


def _extract_frontmatter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    assert lines and lines[0].strip() == "---", f"Falta frontmatter en {path}"
    end_idx = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    data = yaml.safe_load("".join(lines[1:end_idx]))
    assert isinstance(data, dict)
    return data, "".join(lines[end_idx + 1 :])


def test_agents_md_has_no_frontmatter_and_is_within_budget() -> None:
    root = get_workspace_root()
    agents_md = root / "AGENTS.md"
    assert agents_md.exists()
    content = agents_md.read_text(encoding="utf-8")
    assert not content.lstrip().startswith("---")
    assert len(content.encode("utf-8")) < 24000


def test_modular_rules_frontmatter_and_discovery() -> None:
    root = get_workspace_root()
    rules_dir = root / ".agents" / "rules"
    for fname in EXPECTED_RULES:
        path = rules_dir / fname
        assert path.exists(), f"Falta regla {path}"
        fm, _body = _extract_frontmatter(path)
        assert fm.get("trigger") in ("always_on", "model_decision", "glob", "manual")
        assert isinstance(fm.get("description"), str) and len(fm["description"]) > 10


def test_skills_frontmatter_names_unique_and_valid() -> None:
    root = get_workspace_root()
    skills_dir = root / ".agents" / "skills"
    names: list[str] = []
    for skill_name in EXPECTED_SKILLS:
        skill_md = skills_dir / skill_name / "SKILL.md"
        assert skill_md.exists(), f"Falta SKILL.md en {skill_md}"
        fm, _body = _extract_frontmatter(skill_md)
        assert fm.get("name") == skill_name
        assert isinstance(fm.get("description"), str) and len(fm["description"]) > 15
        names.append(fm["name"])
    assert len(names) == len(set(names))


def test_hooks_json_and_real_subprocess_execution() -> None:
    root = get_workspace_root()
    hooks_json = root / ".agents" / "hooks.json"
    assert hooks_json.exists()
    cfg = json.loads(hooks_json.read_text(encoding="utf-8"))
    hook_cmd = cfg["memory-write-guard"]["PreToolUse"][0]["hooks"][0]["command"]

    def run_hook(payload: dict) -> dict:
        proc = subprocess.run(
            ["cmd", "/c", hook_cmd],
            cwd=str(root / ".agents"),
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=True,
        )
        return json.loads(proc.stdout)

    # 1. Escritura en Conocimiento/ debe forzar confirmacion
    res_protected = run_hook(
        {
            "toolCall": {
                "name": "write_file",
                "args": {"Path": str(root / "Conocimiento" / "Personas" / "Juan Garcia.md")},
            }
        }
    )
    assert res_protected["decision"] == "force_ask"

    # 2. Escritura en Memoria-Pendiente/ permitida dentro de delimitacion
    res_staging = run_hook(
        {
            "toolCall": {
                "name": "write_file",
                "args": {"Path": str(root / "Memoria-Pendiente" / "Propuestas" / "prop-000001.yaml")},
            }
        }
    )
    assert res_staging["decision"] == "allow"

    # 3. Comando apply-commit requiere confirmacion forzada
    res_apply = run_hook(
        {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": ".\\.venv\\Scripts\\python.exe -m scripts.brain_cli apply-commit --batch b1 --confirm"},
            }
        }
    )
    assert res_apply["decision"] == "force_ask"

    # 4. Comando de lectura normal no es auto-allow (respeta configuracion de Antigravity)
    res_search = run_hook(
        {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": ".\\.venv\\Scripts\\python.exe -m scripts.brain_cli --read-only search herreria"},
            }
        }
    )
    assert res_search["decision"] == "ask"

    # 5. FIX-01 y FIX-02: proteger AGENTS.md, .agents/, scripts/ y comandos destructivos
    res_agents = run_hook(
        {"toolCall": {"name": "write_file", "args": {"Path": str(root / "AGENTS.md")}}}
    )
    assert res_agents["decision"] == "force_ask"

    res_rules = run_hook(
        {"toolCall": {"name": "edit_file", "args": {"Path": str(root / ".agents" / "hooks.json")}}}
    )
    assert res_rules["decision"] == "force_ask"

    res_rm = run_hook(
        {"toolCall": {"name": "run_command", "args": {"CommandLine": "Remove-Item Conocimiento\\Personas\\Juan.md"}}}
    )
    assert res_rm["decision"] == "force_ask"

    res_py_c = run_hook(
        {"toolCall": {"name": "run_command", "args": {"CommandLine": "python -c \"open('x','w').write('y')\""}}}
    )
    assert res_py_c["decision"] == "force_ask"
