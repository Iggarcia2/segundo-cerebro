---
name: recordar
description: "Extrae o registra un recuerdo, hecho, capacidad, decision o evento en Memoria-Pendiente sin escribir en memoria consolidada."
---

# Skill: Recordar

Usa esta Skill cuando el usuario pida guardar o recordar un dato, contacto, capacidad, decisión, evento o corrección temporal.

## Procedimiento

1. **Identificá fuente y fechas:**
   - Conservá la referencia trazable (`--fuente "[[Conversación YYYY-MM-DD]]"` o archivo origen).
   - Distinguí `ocurrio_el` (solo si se conoce explícitamente; si no, omitilo para que quede `null`) de `registrado_el`.
2. **Ejecutá la ingesta en staging (nunca directo en `Conocimiento/` o `Historia/`):**
   ```powershell
   .\.venv\Scripts\python.exe -m scripts.brain_cli ingest --text "<hecho o resumen>" --fuente "[[<fuente>]]"
   ```
   Agregá `--ocurrio-el YYYY-MM-DD`, `--ambito <ambito>` o `--contexto "<contexto>"` si aplica.
3. **Verificá qué se encoló:**
   ```powershell
   .\.venv\Scripts\python.exe -m scripts.brain_cli --read-only list-proposals
   ```
4. **Informá al usuario:**
   - IDs de propuestas o preguntas creadas (o si se omitió por duplicado).
   - Si alguna quedó en `requiere_aclaracion` (homónimo o contradicción), formulá 1–2 preguntas concretas sin fusionar identidades ni consolidar todavía.
