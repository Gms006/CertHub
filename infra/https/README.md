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
127.0.0.1 portal.local
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
https://portal.local
```

## Variáveis de ambiente recomendadas

Backend (`.env`):

```
FRONTEND_BASE_URL=https://portal.local
CORS_ALLOW_ORIGINS=http://localhost:5173,http://localhost:8011,http://192.168.25.51:5173,https://portal.local
```

Frontend (`frontend/.env`):

```
VITE_API_URL=/api/v1
```

## Rollback (piloto)

- Parar o Caddy.
- Remover `https://portal.local` de `CORS_ALLOW_ORIGINS`.
- Voltar `VITE_API_URL` para `http://localhost:8010/api/v1` no frontend.

## Nota de HSTS (prod)

No piloto, o HSTS usa `max-age=3600` sem `includeSubDomains`. Em produção, ajuste para algo como `max-age=31536000; includeSubDomains`.
