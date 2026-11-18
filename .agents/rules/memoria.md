---
trigger: model_decision
description: "Aplicar al extraer, revisar, aprobar o consolidar recuerdos y propuestas en Memoria-Pendiente."
---

# Política de Memoria y Staging

1. **Captura selectiva:** guardá solo entidades, capacidades, relaciones, decisiones, eventos, necesidades, aprendizajes o preguntas útiles. Descartá charla trivial y duplicados.
2. **Zona provisional única:** toda ingesta automática o de cierre de sesión escribe únicamente en `Memoria-Pendiente/Propuestas/` y `Memoria-Pendiente/Preguntas/` usando `brain_cli ingest`.
3. **Ambigüedad e identidad:** ante homónimos (ej. dos personas con el mismo nombre) o contradicciones con relaciones vigentes, dejá la propuesta en `requiere_aclaracion`; nunca fusiones entidades sin confirmación.
4. **Consolidación transaccional:** aprobá únicamente los IDs indicados por el usuario, generá el Dry-Run con `prepare-commit`, mostrá los archivos afectados y el diff completo, y ejecutá `apply-commit --batch <id> --confirm` solo después de su aprobación inequívoca.
5. **Sin captura mágica continua:** recordá que Antigravity no persiste chats automáticamente por defecto; para guardar el contexto útil de una charla usá la Skill `cerrar-sesion` o pedidos explícitos con `recordar`.
