---
name: revisar-memoria
description: "Lista propuestas y preguntas pendientes en Memoria-Pendiente, prepara Dry-Run con diff y consolida solo cambios aprobados."
---

# Skill: Revisar Memoria

Usa esta Skill cuando el usuario quiera revisar borradores, aprobar o descartar propuestas, preparar un Dry-Run o consolidar recuerdos en `Conocimiento/` / `Historia/`.

## Procedimiento

1. **Listar propuestas provisionales (solo lectura):**
   ```powershell
   .\.venv\Scripts\python.exe -m scripts.brain_cli --read-only list-proposals
   ```
   Agrupá al informar por estado (`requiere_aclaracion`, `pendiente`, `aprobada`, `descartada`) y mencioná qué falta confirmar si hay preguntas en `Memoria-Pendiente/Preguntas/`.
2. **Aprobar o descartar propuestas concretas según indique el usuario:**
   ```powershell
   .\.venv\Scripts\python.exe -m scripts.brain_cli approve-proposal <prop-id>
   .\.venv\Scripts\python.exe -m scripts.brain_cli discard-proposal <prop-id> --reason "<motivo>"
   ```
3. **Preparar Dry-Run obligatorio antes de consolidar:**
   ```powershell
   .\.venv\Scripts\python.exe -m scripts.brain_cli prepare-commit <prop-id-1> <prop-id-2>
   ```
   Mostrá al usuario el `batch_id`, los archivos afectados, sus hashes previos y el diff completo. **No apliques todavía.**
4. **Consolidar solo tras aprobación explícita del lote exacto:**
   ```powershell
   .\.venv\Scripts\python.exe -m scripts.brain_cli apply-commit --batch <batch_id> --confirm
   .\.venv\Scripts\python.exe -m scripts.brain_cli --read-only validate
   .\.venv\Scripts\python.exe -m scripts.brain_cli rebuild-index
   ```
   Si el hash previo cambió en disco o hubo fallo parcial, reportalo inmediatamente sin ocultar el error.
