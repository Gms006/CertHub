# S10.2 IIS Alternative (High-Level)

Este guia descreve uma alternativa de proxy TLS via IIS para cenários corporativos Windows.

## Quando considerar IIS
- Padrão operacional da empresa já é IIS.
- Integração com autenticação/monitoramento corporativo centrada em IIS.

## Passos resumidos
1. Publicar backend FastAPI localmente (`127.0.0.1:8010`).
2. Publicar frontend estático (`frontend/dist`) em site IIS.
3. Criar regra de reverse proxy para `/api/v1` apontando para `http://127.0.0.1:8010`.
4. Vincular certificado TLS no binding HTTPS do site.
5. Aplicar headers de segurança no IIS (equivalentes aos usados no Caddy).
6. Validar com:
   - `curl -I https://<dominio>`
   - `curl -I https://<dominio>/api/v1/health`

## Referências oficiais
- IIS: https://learn.microsoft.com/iis/
- URL Rewrite: https://learn.microsoft.com/iis/extensions/url-rewrite-module/
- ARR (Application Request Routing): https://learn.microsoft.com/iis/extensions/planning-for-arr/
