---
titulo: "Manual de Uso Operativo — Segundo Cerebro V1.0"
version: "1.0.0"
fecha: "2026-11-18"
---

# Manual de Uso Operativo

Guía práctica para trabajar diariamente con **Google Antigravity**, **Obsidian** y **Git / GitHub** sobre este workspace sin perder integridad ni privacidad.

---

## 1. Inicio de sesión y sincronización manual (Git)

Antes de editar notas en Obsidian o iniciar una sesión de trabajo:

```powershell
& "C:\Program Files\Git\cmd\git.exe" status
& "C:\Program Files\Git\cmd\git.exe" pull --rebase origin main
.\.venv\Scripts\python.exe -m scripts.brain_cli --read-only validate
```

*(Si editaste notas desde otro lugar o hiciste `pull`, reconstruí el índice local).*

```powershell
.\.venv\Scripts\python.exe -m scripts.brain_cli rebuild-index
```

---

## 2. Operaciones cotidianas en Antigravity

| Qué querés hacer | Cómo pedirlo en el chat | Qué ocurre por detrás |
| :--- | :--- | :--- |
| **Buscar personas, capacidades o conexiones** | *"Necesito fabricar X: buscá contactos y recursos relacionados, verificá actualidad y citá fuentes."* | Activa `asociar` (`brain_cli --read-only search`). Separa hechos declarados, inferencias y sugerencias. |
| **Guardar un hecho puntual** | *"Recordá que X sabe Y / cambió de empresa en YYYY-MM-DD."* | Activa `recordar` (`brain_cli ingest`). Solo escribe en `Memoria-Pendiente/Propuestas/`. |
| **Cerrar una conversación** | *"Cerrá esta sesión: extraé lo útil sin duplicar."* | Activa `cerrar-sesion`. Antigravity no captura chats automáticamente en V1. |
| **Revisar borradores** | *"Mostrame las propuestas pendientes y qué falta aclarar."* | Activa `revisar-memoria` (`list-proposals`). |
| **Consolidar memoria** | *"Aprobá `prop-000001` y prepará Dry-Run; no escribas hasta que apruebe el diff."* | `approve-proposal` → `prepare-commit` → confirmación explícita → `apply-commit --confirm`. |
| **Diagnosticar un proyecto** | *"Analizá el proyecto X: bloqueos, compras, decisiones y responsables con fuentes."* | Activa `analizar-proyectos` (`check-cycles` + `search`). Nunca crea tareas automáticamente. |
| **Crear tareas explícitamente** | *"Proponé tareas para resolver X con responsables por definir. Mostrá Dry-Run."* | Activa `gestionar-acciones` (`--allow-actions` + `solicitada_por_usuario: true`). |

---

## 3. Trabajo en Obsidian

1. Abrí **Obsidian** → *Open folder as vault* → seleccioná `c:\Users\garci\Desktop\Antigravity\Segundo cerebro`.
2. Podés renombrar o mover notas dentro de `Conocimiento/` o `Historia/` sin romper relaciones gracias al campo `id` estable, pero evitá modificar `id` o `schema_version` a mano.
3. Si editás YAML manualmente en Obsidian, ejecutá siempre:
   ```powershell
   .\.venv\Scripts\python.exe -m scripts.brain_cli --read-only validate
   .\.venv\Scripts\python.exe -m scripts.brain_cli rebuild-index
   ```
4. Empezá con **sincronización Git manual** (revisar `git diff` antes de `commit`/`push`). No actives sincronización automática de *Obsidian Git* hasta confirmar que tu flujo no genera ediciones simultáneas conflictivas.

---

## 4. Cierre y publicación en GitHub privado

```powershell
.\.venv\Scripts\python.exe -m scripts.brain_cli --read-only validate
& "C:\Program Files\Git\cmd\git.exe" status
& "C:\Program Files\Git\cmd\git.exe" diff
& "C:\Program Files\Git\cmd\git.exe" add Conocimiento Historia Sistema docs scripts tests .agents AGENTS.md .gitignore
& "C:\Program Files\Git\cmd\git.exe" commit -m "Resumen claro de cambios revisados"
& "C:\Program Files\Git\cmd\git.exe" push origin main
```

> [!IMPORTANT]
> `Memoria-Pendiente/` e `Indices/` están excluidos por `.gitignore` (`DEC-T05`). Los borradores sin curar permanecen exclusivamente en esta PC hasta su consolidación.

---

## 5. Resolución manual de conflictos Git

Si `git pull` o `git merge` reporta conflicto en un archivo `.md`:
1. **No sobrescribas a ciegas:** abrí el archivo conflictivo y buscá los marcadores `<<<<<<<`, `=======`, `>>>>>>>`.
2. Conservá **todas** las relaciones históricas de ambos lados sin duplicar `id` de relación (`rel-XXXXXX`) ni de nodo (`per-XXXXXX`).
3. Guardá el archivo, ejecutá `git add <archivo>`, `git commit` (o `git rebase --continue`) y validá inmediatamente:
   ```powershell
   .\.venv\Scripts\python.exe -m scripts.brain_cli --read-only validate
   .\.venv\Scripts\python.exe -m scripts.brain_cli rebuild-ids
   .\.venv\Scripts\python.exe -m scripts.brain_cli rebuild-index
   ```
