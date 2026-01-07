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

> Em DEV, se `SMTP_HOST`/`SMTP_FROM` não estiverem configurados, o backend registra o link de reset no log.

### KEEP_UNTIL (one-shot auto-delete)
Quando um job chega com `cleanup_mode=KEEP_UNTIL`, o Agent cria uma task única no horário local do `keep_until`.
Ela executa o cleanup com `--mode keep_until` (audit_log com `meta_json.mode = "keep_until"`).
No Windows Task Scheduler, essa task é criada como V1 com `/V1` e o próprio Agent remove a task após a execução.

```powershell
schtasks /Query /TN "CertHub KeepUntil YYYYMMDD-HHmm" /V /FO LIST
schtasks /Run /TN "CertHub KeepUntil YYYYMMDD-HHmm"
```

### Remover task
```powershell
Unregister-ScheduledTask -TaskName "CertHub Cleanup 18h" -Confirm:$false
```

## Operação (runbooks e smoke tests)
- Runbook de piloto/rollout: `docs/S8_PILOTO_ROLLOUT.md`
- Treinamento rápido: `docs/TREINAMENTO_RAPIDO.md`
- Smoke tests PowerShell:
  - `scripts/windows/s8_smoke.ps1`
  - `scripts/windows/s9_retention_smoke.ps1`

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
