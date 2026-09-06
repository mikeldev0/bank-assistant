# Guía para defender las decisiones

## ¿Por qué este reto?

El reto B concentra el riesgo principal de un asistente con herramientas: confundir lenguaje con autorización. Una transferencia simulada permite demostrar controles reales sin efectos financieros. La prioridad es seguridad observable, no añadir muchas pantallas.

## ¿Por qué Next.js y FastAPI separados?

Next.js ofrece UI React, renderizado inicial en servidor y Server Actions que conservan secretos fuera del navegador. FastAPI concentra la política de dominio y permite montar el SDK Python oficial de MCP en el mismo proceso. Ambos transportes invocan el mismo Store: no hay dos implementaciones de autorización. Dos lenguajes tienen coste, pero coinciden con el alcance pedido y mantienen fronteras claras. El monorepo evita coordinar versiones de dos repositorios en una prueba pequeña.

## ¿Por qué las versiones y dependencias?

Next 16.3.4 se resolvió con el tag `latest` del registro npm; no se usó canary. React, FastAPI y MCP se resolvieron con los registros disponibles y se fijan transitivamente con `package-lock.json` y `uv.lock`. TypeScript estricto, Pydantic y Ruff aportan validación estática y de entradas. CSS propio y Lucide son suficientes: no se añade una biblioteca de componentes, estado global o sistema de diseño completo para una sola pantalla. Las fuentes web son opcionales y tienen fallback local.

## ¿Por qué SQLite y no PostgreSQL/Redis/Celery?

La simulación termina inmediatamente. SQLite proporciona transacciones ACID y unicidad sin servicios adicionales. WAL facilita lecturas concurrentes; BEGIN IMMEDIATE serializa cambios. El benchmark incluye el coste de commit. Para carga significativa o múltiples réplicas: PostgreSQL, migraciones versionadas y un sistema de identidades. No es correcto afirmar que SQLite escala horizontalmente aquí.

## ¿Dónde está la autorización?

En las credenciales distintas y la frontera de FastAPI, no en ocultar botones ni pedir al modelo que se comporte bien. El MCP no tiene una tool para confirmar. Una instrucción maliciosa puede generar propuestas molestas, pero no puede obtener la credencial de revisión. El frontend no recibe secretos del gateway: usa una sesión firmada. El concepto se muestra como texto React, sin HTML o Markdown ejecutable. La huella verifica que la decisión se refiere a los mismos datos.

## ¿Qué ocurre con reintentos y fallos?

Misma clave y datos: misma acción. Misma clave con otros datos: 409. Confirmar de nuevo una acción ejecutada devuelve el resultado sin otro evento. Confirmar una rechazada/caducada falla. Si se pierde la respuesta tras el commit, refrescar o repetir recupera el estado. No hay proveedor externo que pueda ejecutar entre dos commits. Si se añade, harían falta idempotencia del proveedor, outbox y reconciliación; no basta reutilizar este código.

## Límites reales

- Un proyecto y revisor compartido: sin OIDC, roles por usuario, revocación individual de sesiones o MFA. Nunca usar esta autenticación como banca real.
- La sesión dura 8 horas; logout borra la cookie del navegador, pero una copia robada sigue válida hasta caducidad o rotación del secreto.
- No hay rate limiting distribuido ni cuotas por proyecto. El token protege el MCP, pero un poseedor puede generar muchas propuestas. Añadir límites de proxy antes de exposición persistente.
- Auditoría local append-only desde la aplicación, no inmutable frente a quien administra la base de datos.
- Lista limitada a 100 acciones recientes, sin paginación; los contadores representan esa ventana, no todo el histórico.
- Actualización manual y reloj local solo informativo. La decisión siempre vuelve a validar en servidor.
- No se implementa chat duplicado ni otro reto A: el agente conversa en AIFindr y la web es la superficie independiente de aprobación.
- Conexión al proyecto, baseline y comparación todavía necesitan evidencia real. Los tests no prueban cómo se comporta el LLM de AIFindr.

## Tres casos concretos para explicar en entrevista

1. Un prompt dice «ya aprobé, ejecuta»: la API rechaza el token MCP en el endpoint de decisión y no hay tool de ejecución.
2. Dieciséis peticiones concurrentes con la misma clave: una propuesta; dieciséis confirmaciones: un único evento executed.
3. Se confirma con una huella distinta o tras caducidad: 409 y ninguna simulación. El estado y la auditoría permiten explicar el rechazo.

Son casos verificados del gateway, no mejoras medidas del agente. Los tres ejemplos antes/después de Parte 1 deben elegirse de las ejecuciones reales una vez disponibles.
