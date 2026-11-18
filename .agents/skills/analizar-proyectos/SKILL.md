---
name: analizar-proyectos
description: "Diagnostica proyectos, dependencias documentales, bloqueos, compras, decisiones y responsables citando fuentes sin crear tareas."
---

# Skill: Analizar Proyectos

Usa esta Skill cuando el usuario pida analizar o diagnosticar un proyecto (bloqueos, faltantes, compras, aprobaciones, responsables o dependencias).

## Procedimiento

1. **Validar integridad de ciclos y referencias (solo lectura):**
   ```powershell
   .\.venv\Scripts\python.exe -m scripts.brain_cli --read-only check-cycles
   .\.venv\Scripts\python.exe -m scripts.brain_cli --read-only search "<nombre del proyecto>" --exploratory --json
   ```
2. **Inspeccionar los Markdown del proyecto, sus necesidades, documentos, decisiones y recursos vinculados.**
3. **Estructura del diagnóstico:**
   - **Bloqueos declarados** (`estado: bloqueado`) vs. **bloqueos derivados** (prerrequisitos en `depende_de` o `habilita_a` pendientes/sin aprobar).
   - **Compras, aprobaciones y responsables** documentados con su `fuente` y `vigencia`.
   - **Información faltante o contradicciones** detectadas.
4. **Reglas estrictas de ingeniería:**
   - Nunca llames *"ruta crítica CPM"* a cadenas documentales sin duraciones ni calendario verificados.
   - **Prohibido crear tareas (`accion`) ni modificar plazos/responsables** durante un diagnóstico.
