---
name: asociar
description: "Busca conexiones verificadas, capacidades y oportunidades contextuales en toda la boveda separando hechos, inferencias y sugerencias."
---

# Skill: Asociar

Usa esta Skill cuando el usuario pregunte quién sabe hacer algo, busque recursos/contactos entre ámbitos distintos, o pida explorar conexiones en toda la memoria.

## Procedimiento

1. **Búsqueda en modo normal (1–2 sugerencias de alta pertinencia):**
   ```powershell
   .\.venv\Scripts\python.exe -m scripts.brain_cli --read-only search "<consulta>" --json
   ```
2. **Modo exploratorio (si el usuario pide explorar libremente o ampliar conexiones):**
   ```powershell
   .\.venv\Scripts\python.exe -m scripts.brain_cli --read-only search "<consulta>" --exploratory --json
   ```
3. **Presentación obligatoria de resultados:**
   - **Hechos declarados:** citá nota, `id`, `fuente` y `evidencia`.
   - **Inferencias:** explicá el camino de grafo entre nodos sin presentarlo como hecho directo.
   - **Oportunidades sugeridas:** explicá por qué aplica; si `vigencia` es `desconocida` o `historica`, advertí que debe verificarse actualidad/disponibilidad.
   - **Límites:** nunca inventes experiencia no escrita ni crees notas `accion` por iniciativa propia.
4. Si el índice en disco estuviera desactualizado respecto a notas recientes, reconstruilo antes con:
   ```powershell
   .\.venv\Scripts\python.exe -m scripts.brain_cli rebuild-index
   ```
