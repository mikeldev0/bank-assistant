# Conectar el MCP a AIFindr DEV

## Contrato del gateway

- Transporte: Streamable HTTP, `https://<host-publico>/mcp`.
- AIFindr DEV: OAuth con scope `transfers:propose-read`; ver [oauth.md](oauth.md).
- Diagnósticos locales: `Authorization: Bearer <MCP_TOKEN>`.
- Tools permitidas: `propose_transfer`, `get_transfer_status`.
- No compartir `REVIEWER_TOKEN`, `REVIEW_PASSWORD` ni `SESSION_SECRET` con AIFindr.
- Mantener workflow **Agent**. Configurar el servidor en Settings → Custom MCPs y limitar `allowedTools` a las dos herramientas anteriores.
- OAuth está implementado y conectado en DEV. Se verificaron discovery, las dos herramientas y una propuesta desde Playground. El MCP remoto de administración de AIFindr es otro servicio distinto.

## HTTPS temporal

Instala cloudflared desde el distribuidor oficial y ejecuta:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

Copia el hostname asignado en `MCP_ALLOWED_HOSTS` de `backend/.env`, conservando los hosts locales para pruebas:

```dotenv
MCP_ALLOWED_HOSTS=["127.0.0.1:*","localhost:*","HOST-ASIGNADO.trycloudflare.com"]
```

Reinicia el backend. No desactives la protección DNS rebinding. Configura `OAUTH_ISSUER_URL`, registra en AIFindr la URL completa terminada en `/mcp` y completa OAuth. Verifica primero el transporte:

```bash
cd backend
uv run python ../scripts/demo_mcp.py --url https://HOST-ASIGNADO.trycloudflare.com/mcp
```

Un túnel expone el puerto completo: las rutas de revisión siguen necesitando su token exclusivo. La interfaz Next permanece local. El túnel temporal deja de funcionar al cerrar el proceso; para una entrega persistente usa dominio y alojamiento con disco persistente para SQLite, HTTPS y límites de peticiones en el proxy. No escales a múltiples réplicas independientes con SQLite local.

## Demostración real que debe registrarse

1. Capturar baseline del agente **antes** de cambiar el prompt o sus herramientas.
2. Conectar MCP y verificar que el agente descubre las dos tools.
3. Pedir una transferencia sintética completa; registrar ID de conversación, propuesta y estado pending.
4. Revisar y confirmar en Next; verificar un único evento executed.
5. Pedir al agente consultar el estado; su respuesta debe reflejar executed y simulación.
6. Probar rechazo/caducidad y pedir saltarse confirmación; verificar que no hay ejecución.
7. Guardar evidencia real en privado, con marcas temporales y configuración; anonimizar cualquier material compartido.

## Private API

Se verificaron por lectura autenticada los endpoints documentados `GET /api/private/projects/{projectId}/conversations` y `GET /api/private/conversations/{id}` en `api-dev.saas.aifindr.ai`, con Bearer y X-Organization-Id. Los scripts guardan conversaciones únicamente en `private/`. La configuración y las evaluaciones se realizan por la UI del Hub; no se han inventado endpoints privados de escritura ni se ha sustituido Private API por Widget API.

Fuentes: [documentación de AIFindr](https://docs.aifindr.ai/docs/api/ai-findr-api/), [SDK MCP oficial](https://github.com/modelcontextprotocol/python-sdk), [Cloudflare Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/).
