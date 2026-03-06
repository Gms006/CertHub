# S10 — TLS/HTTPS (piloto LAN com Caddy)

Este runbook cobre um piloto local usando **Caddy** com `tls internal`, servindo o frontend e roteando `/api/v1` para o backend.

## Pré-requisitos

- Backend rodando em `http://127.0.0.1:8010`.
- Frontend buildado em `frontend/dist`.
- Caddy instalado no Windows.

## 1) Preparar o frontend

```bash
cd frontend
npm install
npm run build
```

O build do Vite gera o diretório `frontend/dist`, que é servido pelo Caddyfile.

## 2) Configurar hosts (piloto)

Adicione no `hosts` do Windows:

```
127.0.0.1 certhub.local
```

## 3) Confiar no certificado interno (Caddy)

No Windows, execute:

```powershell
caddy trust
```

Isso adiciona a CA local do Caddy ao armazenamento de confiança do sistema.

## 4) Rodar o proxy TLS

```powershell
caddy run --config infra/https/Caddyfile --adapter caddyfile
```

Acesse:

```
https://certhub.local
```

## 5) Validar o setup TLS (importante)

Execute o script de validação oficial:

```powershell
.\scripts\windows\s10_validate_tls.ps1
```

Esperado:
- `[OK] TLS handshake portal sem -k`
- `[OK] GET /health retornou 200`
- `[OK] Strict-Transport-Security`
- `[OK] X-Content-Type-Options`
- `[OK] X-Frame-Options`
- `[OK] Content-Security-Policy`
- `[OK] Sem mixed content inválido em HTML principal`
- `[OK] Validação TLS concluída`
- **exit code: 0**

Ou testes manuais rápidos:

```powershell
# HEAD + status
curl --ssl-no-revoke -I https://certhub.local

# Health endpoint
curl --ssl-no-revoke -fsSL https://certhub.local/health

# Headers de segurança
curl --ssl-no-revoke -I https://certhub.local | findstr /I "Strict-Transport-Security X-Content-Type-Options X-Frame-Options Content-Security-Policy"
```

## Variáveis de ambiente recomendadas

Backend (`.env`):

```
FRONTEND_BASE_URL=https://certhub.local
CORS_ALLOW_ORIGINS=http://localhost:5173,http://localhost:8011,http://192.168.25.51:5173,https://certhub.local
```

Frontend (`frontend/.env`):

```
VITE_API_URL=/api/v1
```

## Rollback (piloto)

- Parar o Caddy.
- Remover `https://certhub.local` de `CORS_ALLOW_ORIGINS`.
- Voltar `VITE_API_URL` para `http://localhost:8010/api/v1` no frontend.

## Nota de HSTS (prod)

No piloto, o HSTS usa `max-age=3600` sem `includeSubDomains`. Em produção, ajuste para algo como `max-age=31536000; includeSubDomains`.
