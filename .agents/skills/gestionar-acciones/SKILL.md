---
name: gestionar-acciones
description: "Propone y consolida nodos de tipo accion unicamente cuando el usuario solicita tareas, plazos o responsables de forma explicita."
---

# Skill: Gestionar Acciones

Usa esta Skill **únicamente** cuando el usuario pida explícitamente crear tareas, definir responsables o modificar plazos (nunca de forma automática tras detectar una necesidad).

## Procedimiento

1. **Verificar solicitud explícita:** confirmá que el usuario pidió crear o actualizar la tarea, plazo o responsable.
2. **Resolver responsables y dependencias con fuentes:**
   ```powershell
   .\.venv\Scripts\python.exe -m scripts.brain_cli --read-only resolve "<responsable>" --tipo persona
   .\.venv\Scripts\python.exe -m scripts.brain_cli --read-only check-cycles
   ```
   Si falta confirmar quién es responsable, dejalo explícito como *"por definir"* en lugar de asignarlo sin permiso.
3. **Preparar propuesta en `Memoria-Pendiente/Propuestas/`** con `target_tipo: accion`, `solicitada_por_usuario: true`, aprobación explícita y Dry-Run mediante:
   ```powershell
   .\.venv\Scripts\python.exe -m scripts.brain_cli prepare-commit <prop-id> --allow-actions
   ```
4. **Aplicar solo tras aprobación del diff exacto** con `apply-commit --batch <batch_id> --confirm` y revalidar con `validate`.
