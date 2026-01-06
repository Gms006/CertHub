# CertHub — Portal de Certificados com Agent

Objetivo: substituir o diretório público de `.pfx` por um fluxo controlado via **Portal (React) + API + Agent Windows**, com:
- instalação no **CurrentUser** sem o usuário ter acesso ao arquivo nem à senha
- controle de acesso via **RBAC global** + flags por usuário
- **auditoria** completa
- remoção automática às **18:00** dos certificados temporários instalados pelo Agent

> Regra de ouro: o **navegador nunca recebe PFX/senha** — a UI apenas cria/acompanha jobs.

## S7 — Escopo e validações confirmadas

**Escopo entregue**
- RBAC global com roles **VIEW/ADMIN/DEV**, incluindo filtro por device e listagens de jobs `mine`/`my-device`.
- Fluxo de **install job** com auto-approve por role/flag/device e **aprovação manual** quando necessário.
- **Auditoria** (`audit_log`) para INSTALL_REQUESTED / INSTALL_APPROVED / INSTALL_DENIED.
- Regras de device: `is_allowed` + vínculo usuário-device para VIEW.

**Validado manualmente**
- VIEW sem auto-approve gera job em **REQUESTED**.
- ADMIN/DEV aprova/nega via `/install-jobs/{id}/approve|deny` e a auditoria registra o evento.
- VIEW não cria job para device não permitido e não lista devices administrativos.

---

## S8 — Piloto e rollout

- Runbook completo: `docs/S8_PILOTO_ROLLOUT.md`
- Treinamento rápido: `docs/TREINAMENTO_RAPIDO.md`
- Smoke test (PowerShell): `scripts/windows/s8_smoke.ps1`

## S9 — Retenção e cleanup configurável

- Política de retenção por job/usuário (KEEP_UNTIL / EXEMPT) com RBAC.
- Próximos stages planejados: S10 TLS/HTTPS, S11 Hardening Web, S12 Secrets, S13 Multi-tenant, S14 LGPD retenção, S15 DSAR, S16 Backups, S17 Observabilidade, S18 Empacotamento, S19 Jurídico.

### S9 Smoke test

PowerShell (VIEW + ADMIN/DEV):

```powershell
.\scripts\windows\s9_retention_smoke.ps1 -CertId <CERT_ID> -DeviceId <DEVICE_ID> `
  -JwtView <JWT_VIEW> -JwtAdmin <JWT_ADMIN>
```

Exemplos de curl:

```bash
# VIEW: KEEP_UNTIL (dentro do limite)
curl -X POST "http://localhost:8010/api/v1/certificados/<CERT_ID>/install" \
  -H "Authorization: Bearer <JWT_VIEW>" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"<DEVICE_ID>","cleanup_mode":"KEEP_UNTIL","keep_until":"2025-03-01T18:00:00Z"}'

# ADMIN/DEV: EXEMPT
curl -X POST "http://localhost:8010/api/v1/certificados/<CERT_ID>/install" \
  -H "Authorization: Bearer <JWT_ADMIN>" \
  -H "Content-Type: application/json" \
  -d '{"device_id":"<DEVICE_ID>","cleanup_mode":"EXEMPT","keep_reason":"Fechamento fiscal"}'
```

Consulta de auditoria (psql):

```sql
select action, meta_json, timestamp
from audit_log
where action in ('RETENTION_SET','CERT_REMOVED_18H','CERT_SKIPPED_RETENTION')
order by timestamp desc
limit 10;
```

### Como rodar o smoke test

```powershell
.\scripts\windows\s8_smoke.ps1
```

Execução garantida (Windows PowerShell):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\s8_smoke.ps1
```

> Nota: `pwsh` é PowerShell 7 (opcional). Se não estiver instalado, use `powershell`.

### Notas operacionais

- **Porta padrão do repo nos exemplos**: `8010` (ajuste via `uvicorn --port`).
- `API_PORT` do `.env.example` **não é consumido** no backend (a porta vem do comando `uvicorn`).
- Para fila RQ use `RQ_QUEUE_NAME` (não `RQ_DEFAULT_QUEUE`).

### Rollback (curto)

```powershell
Unregister-ScheduledTask -TaskName "CertHub Cleanup 18h" -Confirm:$false
Remove-Item C:\ProgramData\CertHubAgent -Recurse -Force
Remove-Item "$env:LOCALAPPDATA\CertHubAgent" -Recurse -Force
```

## Requisitos
- Python 3.10+
- Node 18+
- Docker (recomendado para Postgres)
- (Agent Windows) .NET 8 SDK

> Nota (Agent Windows): o `global.json` fixa o SDK em `8.0.404` com roll-forward para
> `latestMinor`. Caso você tenha outra versão 8.0.x instalada, ajuste o `global.json`
> para a versão disponível no seu ambiente.

> Nota: o backend fixa `passlib[bcrypt]==1.7.4` com `bcrypt==3.2.2` para evitar o erro
> "password cannot be longer than 72 bytes" introduzido em bcrypt 4+ (o passlib 1.7.4
> espera truncamento). Não remova esse pin sem atualizar o passlib.

---

## A) Quickstart local (Windows)

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
uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

### 3) Frontend (opcional)
```bash
cd frontend
npm install
npm run dev
```

---

## B) Config (.env) + `.env.example`

1) Copie o arquivo base:
```bash
copy .env.example .env
```

2) Ajuste os campos principais:
- `DATABASE_URL` (Postgres local)
- `JWT_SECRET` (não versionar segredo real)
- `CERTS_ROOT_PATH` e `OPENSSL_PATH`
- `FRONTEND_BASE_URL` (ex.: `http://localhost:5173` para o link de reset)
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` (envio de e-mail)

> Em ambiente DEV, se `SMTP_HOST`/`SMTP_FROM` não estiverem configurados, o backend
> registra o link de reset no log.

> A API lê `.env` na raiz do repo. `.env.example` não contém segredos.

---

## C) Testes e smoke tests

### Testes automatizados
```bash
pytest -q
```

### Smoke test — fluxo de install job (VIEW → REQUESTED → ADMIN approve)

> Substitua `<JWT_VIEW>` / `<JWT_ADMIN>` / `<CERT_ID>` / `<DEVICE_ID>`.

```powershell
# VIEW cria job (sem auto-approve) -> REQUESTED
$job = Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/certificados/<CERT_ID>/install" `
  -Headers @{ Authorization = "Bearer <JWT_VIEW>" } `
  -ContentType "application/json" `
  -Body '{"device_id":"<DEVICE_ID>"}'
$job.status
$job.id

# ADMIN/DEV aprova manualmente
Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/install-jobs/$($job.id)/approve" `
  -Headers @{ Authorization = "Bearer <JWT_ADMIN>" } `
  -ContentType "application/json" `
  -Body '{"reason":"smoke test"}'
```

### Smoke test — negar job
```powershell
Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/install-jobs/<JOB_ID>/deny" `
  -Headers @{ Authorization = "Bearer <JWT_ADMIN>" } `
  -ContentType "application/json" `
  -Body '{"reason":"smoke test"}'
```

### Smoke test — reset de senha (curl)
```bash
curl -X POST "http://localhost:8010/api/v1/auth/password/reset/init" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com"}'

curl -X POST "http://localhost:8010/api/v1/auth/password/reset/confirm" \
  -H "Content-Type: application/json" \
  -d '{"token":"<TOKEN>", "new_password":"NovaSenha@123"}'
```

### Smoke test — reset de senha (PowerShell)
```powershell
Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/auth/password/reset/init" `
  -ContentType "application/json" `
  -Body '{"email":"user@example.com"}'

Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/auth/password/reset/confirm" `
  -ContentType "application/json" `
  -Body '{"token":"<TOKEN>", "new_password":"NovaSenha@123"}'
```

---

## D) Rotina do Agent (pré-requisitos, instalação e validação)

### Pré-requisitos
- .NET 8 SDK instalado
- Device provisionado (ADMIN/DEV)

### Provisionar device via API
```powershell
$device = Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/admin/devices" `
  -Headers @{ Authorization = "Bearer <JWT_ADMIN>" } `
  -ContentType "application/json" `
  -Body '{"hostname":"PC-01","domain":"NETOCMS","os_version":"Windows 11","agent_version":"1.0.0"}'

$device.device_token
$device.id
```

### Build/Publish (script)
```powershell
.\scripts\windows\publish_agent.ps1 -PublishDir C:\Temp\CerthubAgent\publish
```

### Instalação oficial (ProgramData + Task 18h)
```powershell
.\scripts\windows\install_agent.ps1 -PublishDir C:\Temp\CerthubAgent\publish
```

### Registrar device no Agent (tray app)
1. Execute o `Certhub.Agent.exe`.
2. Menu do tray → **Pair device**.
3. Informe:
   - `API Base URL` (ex.: `http://localhost:8010/api/v1`)
   - `Device ID`
   - `Device Token`

### Validar heartbeat
```powershell
Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/agent/heartbeat" `
  -Headers @{ Authorization = "Bearer <DEVICE_JWT>" } `
  -ContentType "application/json" `
  -Body '{"agent_version":"1.0.0"}'
```

---

## E) Auditoria (consultas SQL prontas)

```sql
-- Install aprovado/negado
select action, actor_user_id, entity_id, timestamp, meta_json
from audit_log
where action in ('INSTALL_APPROVED', 'INSTALL_DENIED', 'INSTALL_REQUESTED')
order by timestamp desc
limit 20;

-- Remoção 18h
select action, actor_device_id, meta_json, timestamp
from audit_log
where action = 'CERT_REMOVED_18H'
order by timestamp desc
limit 10;
```

---

## F) Scheduled cleanup 18h (instalar/validar/remover)

### Rodar cleanup manual (headless)
```powershell
C:\ProgramData\CertHubAgent\publish\Certhub.Agent.exe --cleanup --mode manual
```

### Validar scheduled task
```powershell
schtasks /Query /TN "CertHub Cleanup 18h" /V /FO LIST
schtasks /Run /TN "CertHub Cleanup 18h"
Get-Content "$env:LOCALAPPDATA\CertHubAgent\logs\agent.log" -Tail 60
```

### KEEP_UNTIL (one-shot auto-delete)
Quando um job chega com `cleanup_mode=KEEP_UNTIL`, o Agent cria uma task única no horário local do `keep_until`.
Ela executa o cleanup manual e se auto-deleta após rodar.
No Windows Task Scheduler, essa task é criada como V1 com `/V1 /Z` para evitar erros de EndBoundary.
O cleanup disparado pela task usa `--mode keep_until` (audit_log com `meta_json.mode = "keep_until"`).

```powershell
schtasks /Query /TN "CertHub KeepUntil YYYYMMDD-HHmm" /V /FO LIST
schtasks /Run /TN "CertHub KeepUntil YYYYMMDD-HHmm"
```

### Remover task
```powershell
Unregister-ScheduledTask -TaskName "CertHub Cleanup 18h" -Confirm:$false
```

---

## G) Segurança (controles principais)

- **JWT** assinado; tokens de device são armazenados como **hash** (SHA256).
- **Rate limit** para `/agent/auth` e `/agent/jobs/{id}/payload`.
- Payload token **single-use** + TTL (replay retorna 409 e audit `PAYLOAD_DENIED`).
- VIEW não pode listar devices admin nem instalar em devices não permitidos.

---

## Estrutura do repo
- `backend/`: FastAPI + Alembic + Postgres
- `frontend/`: React (Vite)
- `agent/`: Agent Windows (.NET)
- `scripts/`: scripts auxiliares (PowerShell)
- `infra/`: docker-compose (Postgres)
