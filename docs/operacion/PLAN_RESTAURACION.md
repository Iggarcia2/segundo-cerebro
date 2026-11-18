---
titulo: "Plan de Respaldo y Restauración — Segundo Cerebro V1.0"
version: "1.0.0"
fecha: "2026-11-18"
---

# Plan de Respaldo y Restauración

> [!WARNING]
> **GitHub privado NO sustituye un respaldo independiente.** Un borrado sincronizado por error, compromiso de cuenta o pérdida de acceso afectaría tanto al repo local como al remoto. Adicionalmente, `Memoria-Pendiente/` no se sube a GitHub en V1 (`DEC-T05`).

---

## 1. Estrategia de respaldo en 3 capas

| Capa | Qué cubre | Frecuencia recomendada | Dónde vive |
| :--- | :--- | :--- | :--- |
| **1. Git / GitHub privado** | `Conocimiento/`, `Historia/`, `Sistema/`, `docs/`, `scripts/`, `tests/`, `.agents/`, `AGENTS.md` | En cada sesión con cambios revisados | GitHub privado + copia local `.git` |
| **2. Copia independiente externa (OBLIGATORIA antes de datos reales)** | Todo el workspace **incluyendo `Memoria-Pendiente/`** (excluyendo `.venv/` e `Indices/`) | Semanal (y antes de migraciones grandes) | Disco externo cifrado (BitLocker/VeraCrypt) o archivo comprimido cifrado en unidad separada |
| **3. Regeneración determinista** | `Indices/brain_index.sqlite` y `Sistema/id_registry.json` | Bajo demanda tras restaurar | Reconstruibles al 100 % desde Markdown |

### Ejemplo de respaldo local comprimido independiente (PowerShell)
Guardalo **fuera** de la carpeta del workspace (por ejemplo en `D:\Backups\SegundoCerebro\` o un disco externo):

```powershell
$fecha = Get-Date -Format "yyyyMMdd-HHmm"
$destino = "$env:USERPROFILE\Desktop\Backup-SegundoCerebro-$fecha.zip"
Compress-Archive -Path Conocimiento, Historia, Memoria-Pendiente, Sistema, docs, scripts, tests, .agents, AGENTS.md, .gitignore -DestinationPath $destino
```
*(Si contiene datos reales personales, cifrá el archivo o guardalo en un volumen cifrado).*

---

## 2. Procedimiento de restauración completa desde GitHub privado

1. Clonar en una carpeta limpia:
   ```powershell
   & "C:\Program Files\Git\cmd\git.exe" clone https://github.com/<usuario>/<repo-privado>.git "Segundo cerebro"
   cd "Segundo cerebro"
   ```
2. Crear entorno virtual e instalar dependencias mínimas:
   ```powershell
   & "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv
   .\.venv\Scripts\python.exe -m pip install pyyaml pytest
   ```
3. Verificar integridad, reconstruir contadores e índice SQLite:
   ```powershell
   .\.venv\Scripts\python.exe -m scripts.brain_cli --read-only validate
   .\.venv\Scripts\python.exe -m scripts.brain_cli rebuild-ids
   .\.venv\Scripts\python.exe -m scripts.brain_cli rebuild-index
   .\.venv\Scripts\python.exe -m pytest -v tests\
   ```
4. *(Si restaurás desde el ZIP de respaldo independiente)*: copiá también `Memoria-Pendiente/` si tenías propuestas o preguntas sin consolidar.

---

## 3. Recuperación ante edición errónea o corrupción en una nota

- **Si aún no hiciste commit:**
  ```powershell
  & "C:\Program Files\Git\cmd\git.exe" diff -- "Conocimiento/..."
  & "C:\Program Files\Git\cmd\git.exe" checkout -- "Conocimiento/..."
  ```
- **Si ya hiciste commit:**
  ```powershell
  & "C:\Program Files\Git\cmd\git.exe" log --oneline -n 10
  & "C:\Program Files\Git\cmd\git.exe" revert <hash-commit>
  ```
- Luego revalidá siempre con `brain_cli --read-only validate` y `rebuild-index`.
