---
name: cerrar-sesion
description: "Extrae recuerdos utiles, decisiones, eventos y preguntas al finalizar una sesion y los guarda solo en Memoria-Pendiente."
---

# Skill: Cerrar Sesión

Usa esta Skill cuando el usuario pida cerrar o guardar la sesión actual (ej. `"cerrá esta sesión"`, `"guardá lo útil de hoy"`).

> [!NOTE]
> Antigravity no captura conversaciones automáticamente en memoria persistente por defecto. Esta Skill es el mecanismo explícito comprobado en V1 para extraer el contexto accesible de la conversación actual.

## Procedimiento

1. **Revisar la conversación actual** e identificar únicamente información con valor duradero:
   - Personas, organizaciones, capacidades, relaciones, cambios temporales.
   - Decisiones tomadas con su criterio, eventos relevantes, aprendizajes y necesidades (sin convertir necesidades en `accion`).
   - Preguntas menores pendientes de aclarar.
   - Descartar charla trivial, pruebas descartadas y datos sensibles que el usuario no quiera almacenar.
2. **Ejecutar ingesta idempotente en `Memoria-Pendiente/`:**
   ```powershell
   .\.venv\Scripts\python.exe -m scripts.brain_cli ingest --text "<resumen estructurado de hechos>" --fuente "[[Sesión YYYY-MM-DD]]"
   ```
   Verificá que `Conocimiento/` e `Historia/` no hayan sufrido cambios.
3. **Listar propuestas generadas y reportar:**
   ```powershell
   .\.venv\Scripts\python.exe -m scripts.brain_cli --read-only list-proposals
   ```
   Mostrá qué propuestas nuevas quedaron en `pendiente` o `requiere_aclaracion`, qué preguntas fueron a `Preguntas/`, y cuántos duplicados se omitieron.
