---
trigger: model_decision
description: "Aplicar al registrar, consultar o corregir hechos con fechas, vigencia o historial en el tiempo."
---

# Política de Temporalidad y Procedencia

1. **Doble fecha obligatoria:** distinguí siempre `ocurrio_el` (fecha real del hecho, `null` si se desconoce; prohibido rellenar con la fecha actual) de `registrado_el` (fecha de incorporación al sistema).
2. **Incertidumbre explícita:** cuando una nota o relación tenga `vigencia: desconocida` o `historica`, advertilo al usuario antes de recomendar un contacto, proveedor o dato técnico.
3. **Historia no destructiva:** una corrección o cambio de estado nunca borra hechos pasados. Cerrá la relación anterior con `vigente_hasta` y `vigencia: historica`, registrá un nodo `evento` en `Historia/Eventos/` que documente el cambio, y agregá la nueva relación vigente.
4. **Cadenas documentales vs. CPM:** diferenciá bloqueos documentales (`depende_de` / `habilita_a`) de planificación temporal; nunca llames *"ruta crítica CPM"* a dependencias sin duraciones ni calendario verificados.
