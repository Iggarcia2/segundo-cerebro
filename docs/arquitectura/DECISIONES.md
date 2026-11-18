---
titulo: "Registro de Decisiones de Arquitectura — Segundo Cerebro V1.0"
version: "1.0.0"
fecha: "2026-11-18"
estado: "Vigente para implementación B1–D"
---

# Registro de Decisiones de Arquitectura (`DECISIONES.md`)

Este documento separa explícitamente:
1. **Decisiones aprobadas** (base conceptual + las 5 decisiones técnicas críticas aprobadas tras el diagnóstico P0).
2. **Propuestas abiertas** (temas que requieren definición final antes de cargar datos reales en la etapa D).
3. **Opciones descartadas en V1** (con criterios objetivos para reconsiderarlas en el futuro).

---

## 1. Decisiones aprobadas

### 1.1 Decisiones conceptuales base (Guía Maestra)
| ID | Decisión | Estado | Alcance |
| :--- | :--- | :--- | :--- |
| `DEC-001` | Un solo cerebro universal (ámbitos personales, profesionales y de ingeniería comparten modelo y búsqueda). | **Aprobada** | Todo el workspace. |
| `DEC-002` | Modelo evolutivo controlado (10 clases base; nuevas clases o subtipos fuera de catálogo requieren propuesta + aprobación). | **Aprobada** | Esquema V1 (`Sistema/Esquemas/`). |
| `DEC-003` | Captura selectiva inteligente y aprendizaje híbrido (preguntas críticas al momento; menores a `Memoria-Pendiente/Preguntas/`). | **Aprobada** | Extractor B2 y Skills B4. |
| `DEC-004` | Separación de staging (`Memoria-Pendiente/`) y consolidación exclusivamente mediante Dry-Run con aprobación explícita. | **Aprobada** | B2, B4 y política de seguridad. |
| `DEC-005` | Preservación temporal e histórica (`ocurrio_el`, `registrado_el`, vigencia y eventos de corrección sin destruir pasado). | **Aprobada** | Esquema YAML y B2/B3. |
| `DEC-006` | Creación de tareas (`accion`) y operaciones externas solo ante pedido explícito y aprobación del usuario. | **Aprobada** | B2, B4 y reglas de ingeniería. |
| `DEC-007` | Diferenciación estricta entre dependencias documentales y ruta crítica CPM. | **Aprobada** | B1, B3 y Skills de proyecto. |

### 1.2 Decisiones técnicas críticas aprobadas para V1 (post-P0)

| ID | Decisión técnica | Estado | Detalle e implicancia aceptada |
| :--- | :--- | :--- | :--- |
| `DEC-T01` | **Doble barrera técnica (`scripts + PreToolUse hook`)** | **Aprobada** | Los scripts validan rutas, hashes SHA-256 previos y aprobación explícita de lote antes de tocar `Conocimiento/` o `Historia/`. Adicionalmente, en B4 se configurará `.agents/hooks.json` (`PreToolUse`) para forzar confirmación (`force_ask`) si una herramienta del agente intenta modificar directamente notas fuera de `Memoria-Pendiente/`. *Implicancia:* máxima defensa ante errores o prompt injection; requiere confirmar un aviso adicional si se edita una nota consolidada directo desde el chat fuera del script de consolidación. |
| `DEC-T02` | **IDs estables secuenciales (`<prefijo3>-<6dígitos>`) independientes de archivo** | **Aprobada** | Formato `per-000001`, `con-000001`, `rel-000001` asignado contra registro central y verificado en toda la bóveda. Los enlaces autoritativos usan `destino_id`, conservando `destino: "[[Título]]"` para Obsidian. *Implicancia:* permite renombrar/mover notas en Obsidian sin romper el grafo; optimizado para operar desde una PC principal por vez. |
| `DEC-T03` | **Captura explícita de sesiones (`cerrar-sesion`) sin captura automática por turno** | **Aprobada** | Al confirmarse en P0 que Antigravity no captura conversaciones automáticamente, V1 usa la Skill `cerrar-sesion` y pedidos explícitos (`recordar`). No se ejecuta extracción LLM en hooks `Stop` por turno. *Implicancia:* cero latencia/ruido en conversaciones cotidianas; si se cierra un chat sin invocar `cerrar-sesion`, no se generan propuestas automáticamente. |
| `DEC-T04` | **Motor local en Python 3.12 + `.venv` + `PyYAML` + índice SQLite/JSON** | **Aprobada** | Aprovecha `Python 3.12.10` instalado en el equipo con entorno virtual local aislado (`.venv/`) y dependencias mínimas (`PyYAML`, `pytest`). Índice lexical + metadatos + grafo reconstruible en `Indices/`, sin embeddings ni bases de grafos externas en V1. *Implicancia:* 100 % offline, determinista y auditable; la búsqueda depende de texto, alias, metadatos y grafo explícito. |
| `DEC-T05` | **`Memoria-Pendiente/` excluida de GitHub por defecto (solo local)** | **Aprobada** | El `.gitignore` propuesto en D excluirá `Memoria-Pendiente/`, `Indices/`, `.venv/`, logs sensibles y secretos. Solo la memoria revisada y consolidada (`Conocimiento/`, `Historia/`), `Sistema/`, `docs/`, `scripts/`, `tests/` y `.agents/` se suben al repositorio privado. *Implicancia:* protege la privacidad de borradores sin curar; los borradores no estarán disponibles en otra PC hasta ser consolidados. |

---

## 2. Propuestas abiertas (a cerrar antes de usar datos reales en Etapa D)

> [!WARNING]
> Ninguno de los ítems de esta sección se considera cerrado todavía. Deben definirse antes de migrar información personal o laboral real tras superar las pruebas de la etapa C.

| ID | Tema abierto | Estado | Opciones / Criterio recomendado |
| :--- | :--- | :--- | :--- |
| `PROP-001` | **Política de datos ultra-sensibles fuera de GitHub** | **Propuesta** | Definir qué subconjunto de notas personales (ej. datos bancarios, salud, credenciales, contratos confidenciales) nunca debe salir del disco local ni sincronizarse en GitHub privado, o si requiere carpeta local cifrada/excluida en `.gitignore`. |
| `PROP-002` | **Mecanismo de respaldo externo independiente de GitHub** | **Propuesta** | Definir soporte físico/nube cifrada externa (ej. copia periódica cifrada en disco externo o backup local programado de `Conocimiento/`, `Historia/` y `Memoria-Pendiente/`). GitHub por sí solo no sustituye un backup independiente. |
| `PROP-003` | **Frecuencia de revisión de `Memoria-Pendiente/` y retención de `Auditoria/`** | **Propuesta** | Revisión semanal sugerida en el manual; definir cada cuántos días archivar o purgar propuestas `descartada` o logs de auditoría antiguos. |
| `PROP-004` | **Política efectiva de permisos en Settings de Antigravity** | **Propuesta** | Verificar antes de datos reales que el proyecto tenga *Tool Execution Policy* en `request-review` o `strict` y *Terminal Sandbox* evaluado según compatibilidad con Python/Git en Windows. |
| `PROP-005` | **Sincronización Obsidian + Git en el día a día** | **Propuesta** | Empezar en etapa D con flujo Git manual (pull → revisión → commit → push). Evaluar activar el plugin *Obsidian Git* automático solo tras validar que no genera conflictos. |
| `PROP-006` | **Criterio de evolución de IDs si se trabaja desde múltiples dispositivos** | **Propuesta** | Si en el futuro se crean nodos simultáneamente en 2 PCs antes de hacer `git pull`, migrar el generador a prefijo con sufijo de dispositivo o ULID corto para evitar colisiones numéricas. |

---

## 3. Opciones descartadas en V1 (y cuándo reconsiderarlas)

| Opción descartada | Motivo de descarte en V1 | Condición para reconsiderar en el futuro |
| :--- | :--- | :--- |
| **Embeddings / búsqueda vectorial desde el inicio** | Agrega dependencias pesadas o llamadas externas, complejidad de sincronización y menor explicabilidad frente al MVP lexical + alias + grafo. | Solo tras demostrar en pruebas comparativas reales (post-V1) que el índice lexical + `aliases` + grafo falla en consultas reales frecuentes. |
| **Base de grafos externa (Neo4j, etc.)** | Violación del principio de simplicidad Markdown-first; duplica estado y complica respaldo en Obsidian/GitHub. | Únicamente si el volumen supera decenas de miles de nodos y SQLite/memoria en Python muestra degradación medible. |
| **MCP de filesystem** | Redundante: Antigravity ya lee y escribe en el workspace nativamente. | Solo si en el futuro se necesita acceso controlado a fuentes externas (correo, calendario, ERP) con autorización específica. |
| **Motor en Node.js** | Inicialmente evaluado en P0 cuando Python no estaba instalado; quedó descartado al instalarse `Python 3.12.10` según preferencia del manual. | No requiere cambio salvo necesidad futura de interfaz web/Obsidian plugin en TypeScript. |
| **Captura automática por turno vía LLM en `Stop` hook** | Los hooks son síncronos (timeout 30 s) y ejecutar un extractor en cada mensaje generaría latencia, costos y ruido excesivo en borradores. | Solo si Antigravity incorpora hooks asíncronos nativos de fin de sesión o exportación automática de transcript con filtrado determinista. |
