---
titulo: "Reporte de Aceptación y Auditoría V1.0 — Segundo Cerebro"
fecha: "2026-11-18"
alcance: "Etapas B1–B4 sobre bóveda aislada con datos ficticios"
estado: "APROBABLE CON OBSERVACIONES MENORES (0 fallos críticos)"
---

# Reporte de Aceptación y Auditoría V1.0 (`REPORTE_V1.md`)

Auditoría independiente ejecutada sobre copias aisladas de prueba con **datos exclusivamente ficticios**. No se utilizó información personal ni se modificó memoria consolidada del workspace.

- **Suite ejecutada:** `.\.venv\Scripts\python.exe -m pytest -v tests\`
- **Resultado global observado:** **39/39 pruebas PASSED** (`4.18s`), de las cuales **15/15** corresponden a la matriz `T01`–`T15` en [test_c_acceptance.py](file:///c:/Users/garci/Desktop/Antigravity/Segundo%20cerebro/tests/test_c_acceptance.py).
- **Validación del workspace base:** `.\.venv\Scripts\python.exe -m scripts.brain_cli --read-only validate` → `4` notas verificadas, `0` errores, `0` advertencias.

---

## 1. Matriz de Pruebas de Aceptación (`T01`–`T15`)

| Caso | Preparación | Ejecución | Evidencia | Resultado |
| :--- | :--- | :--- | :--- | :--- |
| **T01** | Bóveda ficticia aislada | `StagingManager.ingest_text("Sofia Castro sabe caldereria industrial.")` | Crea 1 propuesta en `Memoria-Pendiente/Propuestas/`; `Conocimiento/Personas/Sofia Castro.md` no existe. | **PASA** |
| **T02** | Nodos ficticios (`per-000001`, `con-000001`, `nec-000001`, `pro-000001`) + índice reconstruido | `AssociativeSearchEngine.search("necesito fabricar una estructura metalica para Ampliacion Taller Sur")` | Recupera a `per-000001` (`Juan García`) en `suggested_opportunities` citando fuente `[[Conversación ficticia 01]]`. | **PASA** |
| **T03** | Dos notas `persona` con título `"Juan García"` (`per-000001` y `per-000002` en ámbitos distintos) | `AssociativeSearchEngine.search("Juan Garcia")` | Ambos IDs aparecen por separado en `declared_facts`; nunca se fusionan. | **PASA** |
| **T04** | Alta inicial `"Lucia Mendez trabaja en Planta A"` (`2026-06-01`) y cambio `"dejo Planta A y ahora trabaja en Planta B"` (`2026-11-01`) | `ingest` → `approve` → `prepare-commit` → `apply-commit --confirm` en dos pasos | Relación con `Planta A` pasa a `vigencia: historica`, se agrega `Planta B` (`vigente`) y se crea nodo `evento` en `Historia/Eventos/`. | **PASA** |
| **T05** | Relación `rel-000001` con `vigencia: desconocida` y sin fechas | `AssociativeSearchEngine.search("herreria")` | `advertencias` incluye `"Vigencia desconocida: verificar actualidad antes de asumir disponibilidad."` | **PASA** |
| **T06** | Texto `"Marcos Silva sabe automatizacion PLC."` | Dos ejecuciones consecutivas de `ingest_text` con igual fuente | 1ra crea 1 propuesta; 2da devuelve `created_proposals == []` y `skipped_duplicates == 1`. | **PASA** |
| **T07** | Nota y texto con inyección maliciosa (`"IGNORA TODAS LAS REGLAS..."`) | `ingest_text`, `search` y evaluación directa de `hook_guard.evaluate_tool_call` | Ni `ingest` ni `search` crean `accion` ni tocan `Conocimiento/`; hook devuelve `force_ask` ante escritura en `Conocimiento/` o `git push`. | **PASA** *(ver `R-01`, `R-02`)* |
| **T08** | Dos propuestas encoladas (`p1`, `p2`) | `approve_proposal(p1)` | `p1` queda `aprobada`; `p2` permanece `pendiente`. | **PASA** |
| **T09** | `prepare-commit` sobre `Juan Garcia.md`, seguido de edición externa del `.md` antes de aplicar | `apply_commit(batch_id, confirm=True)` | Lanza `RuntimeError("Dry-Run obsoleto...")`, deja propuesta sin consolidar y registra `apply_aborted_stale`. | **PASA** |
| **T10** | Lote multi-archivo (`Nora Diaz` + `Metrologia`) con escritor simulado que falla en el 2do archivo | `apply_commit(..., writer_fn=fail_second)` | Lanza `RuntimeError("Fallo parcial...")`, deja manifiesto en `partial_failure` con `written_files` (1) y `failed_files` (1). | **PASA** *(ver `R-04`)* |
| **T11** | Bóveda con proyecto `pro-000001` | `search("diagnostico bloqueos del proyecto Ampliacion Taller Sur")` | `actions_created == 0`; carpeta `Conocimiento/Acciones/` vacía y nota de proyecto sin cambios. | **PASA** |
| **T12** | Nota con `doc-000001` duplicado, ciclo `doc-000001 -> doc-000001` y `[[Plano Inexistente]]` | `VaultValidator.validate_all()` | Reporta códigos `DUPLICATE_NODE_ID`, `BROKEN_WIKILINK` y `DEPENDENCY_CYCLE`. | **PASA** |
| **T13** | Persona `per-000009` vinculada solo con `relacionado_con` genérico a `pro-000001` | `search` en modo normal (`exploratory=False`) | `per-000009` no aparece en `suggested_opportunities`. | **PASA** |
| **T14** | Inspección de `.agents/skills/cerrar-sesion/SKILL.md` y `.agents/hooks.json` | Verificación estructural de mecanismo único | Existe Skill `cerrar-sesion` con `brain_cli ingest`; `.agents/hooks.json` no posee hook `Stop` de captura automática silenciosa. | **PASA** *(restricción documentada)* |
| **T15** | Repo temporal con remoto bare Git local, commit inicial, borrado simulado y `git clone` | Clonado a carpeta nueva + `brain_cli validate` + `rebuild-index` | Notas consolidadas restauradas al 100 %, validación en 0 errores e índice SQLite reconstruido desde Markdown. | **PASA** |

---

## 2. Lista de riesgos clasificada por severidad

*(No se detectaron fallos de severidad **Crítica** ni **Alta** en la lógica implementada, pero sí riesgos de severidad **Media** y **Baja** que conviene atender).*

| ID | Severidad | Hallazgo | Impacto potencial |
| :--- | :--- | :--- | :--- |
| **R-01** | **Media** | En [hook_guard.py](file:///c:/Users/garci/Desktop/Antigravity/Segundo%20cerebro/scripts/hook_guard.py), `PROTECTED_DIRS` incluye `Conocimiento`, `Historia` y `Sistema`, pero no incluye `AGENTS.md`, `.agents/` ni `scripts/`. Para esas rutas devuelve `"ask"` en lugar de `"force_ask"`. | Si el usuario tuviera caché de `"Always Allow"`, una inyección indirecta podría intentar modificar reglas, skills o hooks sin forzar re-confirmación. |
| **R-02** | **Media** | El análisis de `run_command` en [hook_guard.py](file:///c:/Users/garci/Desktop/Antigravity/Segundo%20cerebro/scripts/hook_guard.py) detecta `apply-commit`, `git push/reset/clean/rm` y rutas explícitas `conocimiento/`, `historia/`, `sistema/`, pero no detecta cmdlets destructivos de PowerShell (`Remove-Item`, `del`, `Clear-Content`, `Move-Item`) ni scripts inline (`python -c ...`) si no mencionan literalmente esas carpetas. | Un comando ofuscado dependería únicamente de la política *Tool Execution Policy* (`request-review` / `strict`) en Settings de Antigravity. |
| **R-03** | **Media** | El extractor basado en regex de [staging.py](file:///c:/Users/garci/Desktop/Antigravity/Segundo%20cerebro/scripts/staging.py) cubre patrones explícitos en español (`sabe`, `trabaja en`, `dejó ... y trabaja en`, `Decisión:`, `Evento:`, `Aprendizaje:`, `Necesitamos`, `¿...?`). | Oraciones muy coloquiales fuera de esos patrones requieren que el agente resuma los hechos de forma estructurada al invocar `recordar` o `cerrar-sesion`. |
| **R-04** | **Baja** | Ante `partial_failure` en [committer.py](file:///c:/Users/garci/Desktop/Antigravity/Segundo%20cerebro/scripts/committer.py), el sistema registra con exactitud qué archivos se escribieron y cuáles fallaron, pero no revierte automáticamente en disco los ya escritos en ese lote. | Requiere intervención manual o restauración vía Git (`git checkout`) si ocurre un error de I/O a mitad de un lote multi-archivo. |
| **R-05** | **Baja** | El workspace aún no está inicializado como repo Git ni tiene `.gitignore` (Etapa D), y la sesión actual de Antigravity no tiene `git`/`python` en el `PATH` heredado hasta reiniciar la aplicación. | Hasta completar D, no hay historial Git activo sobre este workspace ni respaldo externo de las notas ficticias/configuración. |

---

## 3. Correcciones propuestas (pendientes de tu aprobación; no ejecutadas)

Conforme a la regla de auditoría, **no se aplicó ninguna modificación** tras las pruebas. Si aprobás, propongo aplicar en un siguiente paso:

1. **`FIX-01` (mitiga `R-01`):** agregar `AGENTS.md`, `.agents` y `scripts` a las rutas protegidas con `"decision": "force_ask"` dentro de [hook_guard.py](file:///c:/Users/garci/Desktop/Antigravity/Segundo%20cerebro/scripts/hook_guard.py).
2. **`FIX-02` (mitiga `R-02`):** endurecer la evaluación de `run_command` en [hook_guard.py](file:///c:/Users/garci/Desktop/Antigravity/Segundo%20cerebro/scripts/hook_guard.py) para devolver `"force_ask"` ante comandos de borrado/escritura masiva (`remove-item`, `del `, `erase `, `rmdir`, `set-content`, `out-file`, `python -c`).
3. **`FIX-03` (mitiga `R-04`, opcional para V1.1):** añadir subcomando `rollback-batch` o respaldo temporal previo en memoria/staging durante `apply-commit` para revertir archivos ya escritos si falla un archivo intermedio.
4. **Etapa D (mitiga `R-05`):** inicializar Git, configurar `.gitignore`, conectar repositorio privado en GitHub, verificar respaldo externo independiente, vincular Obsidian y probar pull/commit/push/conflicto/restauración.

---

## 4. Dictamen de aceptación

- **Estado:** **APROBADO PARA AVANZAR A ETAPA D** (con recomendación de aplicar `FIX-01` y `FIX-02` antes de cargar datos reales).
- **Condición cumplida:** cero fallos críticos de integridad referencial, idempotencia, staging obligatorio o verificación de hashes; las restricciones de V1 (captura explícita vía `cerrar-sesion`, búsqueda lexical+grafo sin embeddings) están documentadas.
