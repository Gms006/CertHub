# CertHub

Portal corporativo para gerenciamento de certificados digitais com fluxo controlado de instalação via **Frontend (React)**, **API (FastAPI)** e **Agent Windows (.NET)**. O navegador **nunca recebe PFX/senha** — a UI apenas cria e acompanha jobs.

## Visão geral
O CertHub substitui o compartilhamento direto de arquivos `.pfx` por um processo auditável e baseado em permissões, garantindo:
- Instalação no **CurrentUser** sem expor arquivo ou senha ao usuário.
- Controle de acesso com **RBAC** e políticas por dispositivo/usuário.
- **Auditoria completa** de ações críticas.
- Remoção automática de certificados temporários às **18h** via Agent.

## Principais recursos
- **RBAC** (VIEW/ADMIN/DEV) com filtros por device e listagens `mine`/`my-device`.
- **Fluxo de install job** com auto-approve por role/flag/device e aprovação manual quando necessário.
- **Auditoria** (`audit_log`) para INSTALL_REQUESTED/APPROVED/DENIED e eventos de retenção.
- **Retenção configurável** (KEEP_UNTIL/EXEMPT) com regras por job/usuário.
- **Agent Windows** com cleanup agendado e suporte a KEEP_UNTIL one‑shot.

## Arquitetura
- `frontend/`: React (Vite)
- `backend/`: FastAPI + Alembic + Postgres
- `agent/`: Agent Windows (.NET)
- `infra/`: Docker Compose (Postgres)
- `scripts/`: scripts auxiliares (PowerShell)

## Requisitos
- Python 3.10+
- Node 18+
- Docker (recomendado para Postgres)
- (Agent Windows) .NET 8 SDK

> Nota (Agent Windows): `global.json` fixa o SDK em `8.0.404` com roll‑forward para `latestMinor`.

> Nota: o backend fixa `passlib[bcrypt]==1.7.4` com `bcrypt==3.2.2` para evitar o erro de truncamento de senha do bcrypt 4+.

## Quickstart (desenvolvimento local)
### 1) Subir Postgres
```bash
docker compose -f infra/docker-compose.yml up -d
```

### 2) Backend (API)
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate

pip install -r requirements.txt

cd backend
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8010 --env-file .\.env
```

### 3) Frontend (opcional)
```bash
cd frontend
npm install
npm run dev
```

#### Na fase de implantação real e utilização em outras máquinas:
```bash
cd frontend
npm run build
npm run preview -- --host 0.0.0.0 --port 5173
```

### 4) Worker (opcional)
```bash
cd backend
$env:REDIS_URL="redis://localhost:6379/0"
$env:RQ_QUEUE_NAME="certs"   # ou o nome da fila que você colocou
$env:CERTIFICADOS_ROOT="G:\CERTIFICADOS DIGITAIS"   # ajuste para sua pasta real 
python -m app.workers.rq_worker
```

### 5) Watcher (opcional)
```bash
cd backend
$env:REDIS_URL="redis://localhost:6379/0"
$env:RQ_QUEUE_NAME="certs" # mesmo que o do worker
$env:ORG_ID="1"
$env:CERTIFICADOS_ROOT="G:\CERTIFICADOS DIGITAIS"   # ajuste para sua pasta real 
$env:WATCHER_DEBOUNCE_SECONDS="2"
$env:WATCHER_MAX_EVENTS_PER_MINUTE="60"
python -m app.watchers.pfx_directory
```


## Configuração
A API lê `.env` na raiz do repositório. Use o `.env.example` como base.

```bash
copy .env.example .env
```

Campos principais:
- `DATABASE_URL` (Postgres local)
- `JWT_SECRET` (não versionar segredo real)
- `CERTS_ROOT_PATH` e `OPENSSL_PATH`
- `FRONTEND_BASE_URL` (ex.: `http://localhost:5173`)
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`
- `CORS_ALLOW_ORIGINS` (CSV com origens permitidas)
- `ECONTROLE_WEBHOOK_ENABLED`, `ECONTROLE_WEBHOOK_URL`, `ECONTROLE_WEBHOOK_TOKEN`
- `ECONTROLE_WEBHOOK_VERIFY_TLS` (`false` em dev com TLS self-signed)

> Em DEV, se `SMTP_HOST`/`SMTP_FROM` não estiverem configurados, o backend registra o link de reset no log.

## S10 Piloto LAN (1 comando)
Domínio padrão do piloto: `certhub.local`.

Pré-requisitos:
- Backend em `http://127.0.0.1:8010` (health: `/health`).
- Caddy instalado no Windows.
- PowerShell em modo administrador para ajustes de hosts/CA.

Comando único:
```powershell
.\scripts\windows\s10_pilot_up.ps1
```

O script executa:
1. Build do frontend (se `frontend/dist` não existir).
2. Verificação da API em `http://127.0.0.1:8010/health`.
3. Setup idempotente do `hosts` (`127.0.0.1 certhub.local`).
4. `caddy trust` para confiar na CA local.
5. Inicialização do Caddy.
6. Validação TLS sem `-k` e headers obrigatórios.

Validação manual (aceite):
```bash
# Teste 1: HEAD (TLS handshake)
curl --ssl-no-revoke -I https://certhub.local
# Esperado: HTTP/1.1 200 OK

# Teste 2: Health endpoint (JSON response)
curl --ssl-no-revoke -fsSL https://certhub.local/health
# Esperado: {"status":"ok"}

# Teste 3: Headers de segurança
curl --ssl-no-revoke -I https://certhub.local | findstr /I "Strict-Transport-Security X-Content-Type-Options X-Frame-Options Content-Security-Policy"
# Esperado: 4 headers presentes

# Teste 4: Validação oficial (fonte de verdade)
.\scripts\windows\s10_validate_tls.ps1
# Esperado: exit 0, todos os [OK] marcados
```

Observação da validação TLS (`scripts/windows/s10_validate_tls.ps1`):
- O health é validado com `GET /health` (o endpoint não aceita `HEAD`).
- A checagem de mixed content ignora apenas namespaces W3C esperados:
  - `http://www.w3.org/1999/xlink`
  - `http://www.w3.org/XML/1998/namespace`
  - `http://www.w3.org/2000/xmlns/`
  - `http://www.w3.org/` (genérico para outras definições W3C)
- Headers de segurança obrigatórios (Caddyfile):
  - `Strict-Transport-Security: max-age=3600` (HSTS)
  - `X-Content-Type-Options: nosniff` (MIME sniffing prevention)
  - `X-Frame-Options: DENY` (Clickjacking prevention)
  - `Content-Security-Policy: frame-ancestors 'none'` (CSP)
- **Windows/curl + Schannel**: em redes internas sem verificação de revogação OSCP/CRL, o curl pode retornar `CRYPT_E_NO_REVOCATION_CHECK`. O script detecta automaticamente e tenta novamente com `--ssl-no-revoke` (somente para validação do piloto LAN). Isso não afeta a segurança do piloto e é documentado no audit trail.

Variáveis de ambiente (piloto):
Backend (`.env`):
```
FRONTEND_BASE_URL=https://certhub.local
CORS_ALLOW_ORIGINS=http://localhost:5173,http://localhost:8011,http://192.168.25.51:5173,https://certhub.local
```

Frontend (`frontend/.env`):
```
VITE_API_URL=/api/v1
```

Runbook piloto: `infra/https/README.md`  
Trilha produção (S10.1): `docs/S10_DEPLOYMENT_GUIDE.md`

### Rollback (S10)
- Parar Caddy (encerre a janela/processo do `caddy run`).
- Voltar para dev local:
  - API: `http://127.0.0.1:8010`
  - Frontend Vite: `npm run dev` (em `frontend/`)
- Reverter `hosts` com backup:
  - Backup gerado em `C:\Windows\System32\drivers\etc\hosts.bak`
  - Restaurar para `C:\Windows\System32\drivers\etc\hosts` (como admin).

### KEEP_UNTIL (one-shot auto-delete)
Quando um job chega com `cleanup_mode=KEEP_UNTIL`, o Agent cria uma task **ONCE** via `schtasks` no horário local do `keep_until`.
Ela executa o cleanup com `--mode keep_until` (audit_log com `meta_json.mode = "keep_until"`), remove **apenas** entradas com `CleanupMode=KEEP_UNTIL` e preserva jobs `DEFAULT/18h`.
No Windows Task Scheduler, essa task é criada como V1 com `/V1` e o próprio Agent remove a task após a execução.

```powershell
schtasks /Query /TN "CertHub KeepUntil YYYYMMDD-HHmm" /V /FO LIST
```

Logs esperados durante a execução: `Starting cleanup (KeepUntil)` e `In-scope: 1`.

### Remover task
```powershell
Unregister-ScheduledTask -TaskName "CertHub Cleanup 18h" -Confirm:$false
```

## Operação (runbooks e smoke tests)
- Runbook de piloto/rollout: `docs/S8_PILOTO_ROLLOUT.md`
- Treinamento rápido: `docs/TREINAMENTO_RAPIDO.md`
- Checklist QA S9: `docs/S9_QA_CHECKLIST.md`
- Smoke tests PowerShell:
  - `scripts/windows/s8_smoke.ps1`
  - `scripts/windows/s9_retention_smoke.ps1`

## Inventário Instalados (S9.1)
- O Agent reporta periodicamente o snapshot do store `CurrentUser\\My` (metadados apenas) para o endpoint `POST /api/v1/agent/installed-certs/report`.
- O portal consulta por device via `GET /api/v1/devices/{device_id}/installed-certs?scope=all|agent` (sem PFX/senha).
- Variável do Agent: `INSTALLED_CERTS_REPORT_INTERVAL_SECONDS` (default 30; `0` desabilita o report).

Validação rápida:
- `pytest backend/tests/test_s9_1_installed_certs.py`
- Verificar no portal a aba “Instalados” com filtro “Todos” vs “Somente via Agent”.

## Segurança
- **JWT** assinado; tokens de device armazenados como **hash** (SHA256).
- **Rate limit** para `/agent/auth` e `/agent/jobs/{id}/payload`.
- Payload token **single-use** + TTL (replay retorna 409 e audit `PAYLOAD_DENIED`).
- VIEW não pode listar devices admin nem instalar em devices não permitidos.

## Auditoria
A base de dados mantém trilhas de auditoria para ações críticas. Consulte a pasta `docs/` para detalhes de operação e retenção.

## Suporte
Em caso de dúvidas, abra uma issue no repositório com:
- versão do backend e do agent
- logs relevantes
- passos para reproduzir

## Licença
Defina a licença do projeto em `LICENSE`.
