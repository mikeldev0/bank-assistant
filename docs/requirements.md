# Matriz de requisitos

| Criterio | Evidencia | Estado |
|---|---|---|
| Elegir solo un reto | Reto B, gateway MCP | Hecho |
| Frontend y backend funcionales | Next.js + FastAPI; E2E Playwright | Verificado local |
| Registrar propuesta del agente | MCP `propose_transfer`, SQLite persistente | Verificado con cliente MCP sintético |
| Confirmación explícita | Checkbox + Server Action autenticada + endpoint exclusivo | Verificado |
| Ejecución simulada y estado | Máquina de estados y audit trail | Verificado |
| Happy path completo | MCP HTTP → web → confirmación → executed | Verificado local |
| Caso adversarial | Tokens separados, concurrencia, expiración, datos alterados | 17 tests backend |
| Evidencia objetiva | 100 muestras benchmark + reintentos concurrentes | `benchmark.json` |
| URL pública HTTPS autenticada | Cliente MCP autenticado por túnel; `https-verification.json` | Verificado; URL temporal |
| Conectar al proyecto AIFindr | Configurar Custom MCP y demostrar desde agente | Pendiente |
| Parte 1: hipótesis concreta | Fiabilidad de afirmaciones y frontera propuesta/ejecución | Preparada |
| Baseline 15–25 casos | 20 casos con criterio explícito | Dataset preparado; ejecución pendiente |
| Captura previa al cambio | Guardar config y prompt originales en privado | Pendiente |
| Cambio aplicado a Agent Workflow | Adición propuesta; conservar workflow Agent | Pendiente |
| Comparativa antes/después | `evaluations/compare.py` con revisión humana | Script preparado; resultados pendientes |
| Tres ejemplos antes/después | Seleccionar mejoras/regresiones reales | Pendiente |
| Repositorio privado GitHub | Monorepo backend + frontend | Verificar URL al publicar |
| Instrucciones, decisiones, riesgos | README + docs | Hecho |
| Presentación única + uso de IA | `presentation.md` | Documento preparado; completar resultados reales |

No confundir tests del gateway con evaluaciones del agente. No se ha alterado el proyecto antes de capturar el baseline.
