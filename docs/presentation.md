# Bank Assistant — presentación asíncrona

Documento de presentación. Tiempo orientativo de explicación: 8–10 minutos. Estado actual: implementación local verificada; integración AIFindr y evidencia de Parte 1 pendientes. No enviar como prueba completamente terminada hasta cerrar esos puntos.

## 1. Problema y foco (45 s)

Un agente bancario puede confundir una intención con una autorización o afirmar que ha realizado una operación que solo propuso. Elijo el reto B para hacer verificable esa frontera. La demo usa transferencias ficticias y no tiene ninguna conexión con un banco.

## 2. Parte 1: hipótesis y método (90 s)

Hipótesis: un contrato explícito sobre evidencias, estados y confirmación reduce afirmaciones falsas de ejecución y respuestas financieras no fundamentadas. Hay 20 casos fijos: consultas de productos, aclaraciones, límites, inyección, secretos, caducidad y reintentos. Cada caso tiene un criterio de éxito.

Antes de modificar el agente: capturar prompt publicado y configuración del workflow Agent en privado, ejecutar los 20 casos en conversaciones independientes y registrar respuestas, tools, latencia y uso. Después: añadir la política propuesta y repetir manteniendo constantes modelo, fuentes y herramientas. Revisar evidencias con criterio humano y comparar casos emparejados. Los casos que requieren una acción previa necesitan preparar y registrar ese estado en ambas corridas.

**Resultados reales todavía no disponibles.** No hay porcentaje de mejora inventado. El cierre requiere el contrato privado, baseline, cambio publicado y segunda ejecución. Seleccionar entonces tres casos con evidencia concreta, incluyendo una regresión si la hubiera.

## 3. Demo del flujo principal (2 min)

1. Ejecutar `scripts/demo_mcp.py`: el cliente descubre/conversa por el transporte MCP y propone 125 EUR a Alex Demo, destino DEMO-4821.
2. Abrir Next, iniciar sesión como revisor y actualizar. Ver propuesta pendiente.
3. Revisar importe, beneficiario, destino y concepto. El botón permanece deshabilitado hasta marcar la confirmación.
4. Confirmar. Estado Simulada y eventos proposed → confirmed → executed.
5. Consultar estado por MCP. Una ejecución real de esta secuencia desde AIFindr sigue pendiente; el cliente sintético demuestra la implementación local.

## 4. Decisiones técnicas (90 s)

El MCP usa el SDK oficial y solo publica herramientas de propuesta y consulta. FastAPI y MCP comparten una política determinista. El frontend usa Server Actions para que las credenciales no lleguen al navegador. SQLite es suficiente para una simulación síncrona en una única instancia. No añado una cola que no resuelve un problema del alcance.

Los importes son céntimos enteros, los destinos son ficticios y los datos de la propuesta son inmutables. La confirmación está ligada a su huella. Tokens separados impiden que el agente se autoconfirme.

## 5. Caso no trivial y mediciones (1 min)

Con peticiones concurrentes la restricción de unicidad y la transacción producen una sola propuesta y una sola ejecución. El test verifica el número de eventos, no solo el código HTTP. También se prueban datos distintos bajo la misma clave, acceso de otro propietario, caducidad y credencial incorrecta.

El benchmark local usa 100 acciones. Véase `benchmark.json` para mediana y p95 medidos y el alcance preciso. No mide al LLM ni la red. Playwright verifica el flujo web y el ancho móvil.

## 6. Límites y evolución (1 min)

Un solo proyecto y revisor, sin banca real, OAuth de usuarios ni auditoría resistente al administrador. No hay servicio de ejecución externo. Para producción: identidad OIDC, rate limiting, PostgreSQL, auditoría externa y, si aparece un proveedor real, outbox/reconciliación e idempotencia de proveedor. No escalar esta base SQLite como si fuera un servicio distribuido.

## 7. Uso de IA y autoría (45 s)

Se utilizó Codex para interpretar requisitos, implementar código, preparar documentación y ejecutar comprobaciones. Se consultó documentación oficial de Next.js, MCP y AIFindr; se verificaron dependencias en los registros. No se delegó en subagentes. La IA no tuvo autorización para enviar correos de entrega ni publicó datos confidenciales.

La persona candidata solicitó Next.js, FastAPI, el reto MCP y GitHub privado. Las elecciones de SQLite, separación de credenciales, modelo de estados y evaluación propuestas aquí fueron elaboradas con asistencia de IA y deben ser revisadas y asumidas por la persona candidata antes de la defensa. No se atribuyen retrospectivamente decisiones humanas no tomadas. Evidencia: tests, E2E, build, lint, benchmark y capturas sintéticas incluidas.
