# Conectar el MCP a AIFindr DEV

## Contrato del gateway

- Transporte: Streamable HTTP, `https://<host-publico>/mcp`.
- Cabecera: `Authorization: Bearer <MCP_TOKEN>`.
- Tools permitidas: `propose_transfer`, `get_transfer_status`.
- No compartir `REVIEWER_TOKEN`, `REVIEW_PASSWORD` ni `SESSION_SECRET` con AIFindr.
- Mantener workflow **Agent**. Configurar el servidor en Settings → Custom MCPs y limitar `allowedTools` a las dos herramientas anteriores.
- El token de MCP es una credencial de servicio preacordada. No se implementa discovery OAuth; si el portal exige OAuth en vez de headers configurables, será necesaria esa adaptación. El MCP remoto de administración de AIFindr es otro servicio distinto.

## HTTPS temporal

Instala cloudflared desde el distribuidor oficial y ejecuta:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

Copia el hostname asignado en `MCP_ALLOWED_HOSTS` de `backend/.env`, conservando los hosts locales para pruebas:

```dotenv
MCP_ALLOWED_HOSTS=["127.0.0.1:*","localhost:*","HOST-ASIGNADO.trycloudflare.com"]
```

Reinicia el backend. No desactives la protección DNS rebinding. Configura en AIFindr la URL completa terminada en `/mcp` y su token. Verifica primero el transporte:

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

La documentación pública de `/api/widget/...` no satisface el requisito de Private API. El contrato privado adjunto debe verificarse antes de implementar llamadas, cambios de prompt o ejecución de evaluaciones. La clave disponible por sí sola no describe esos endpoints. No se ha inventado un adaptador ni declarado una conexión sin probar.

Fuentes: [documentación de AIFindr](https://docs.aifindr.ai/docs/api/ai-findr-api/), [SDK MCP oficial](https://github.com/modelcontextprotocol/python-sdk), [Cloudflare Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/).
