# Plano de Desenvolvimento — CertHub (S7)

## Visão geral

CertHub é um **portal + API + agent** para controle de certificados digitais (.pfx), garantindo que o usuário **não receba o arquivo/senha**, com **RBAC**, auditoria e remoção automática às 18h dos certificados temporários.

## Arquitetura

- **Backend (FastAPI + SQLAlchemy + Alembic + Postgres)**
  - Catálogo de certificados (ingest).
  - CRUD de certificados, jobs e devices.
  - RBAC (VIEW/ADMIN/DEV) e auditoria (`audit_log`).
  - Endpoints do Agent (`/agent/*`) e regras de segurança (tokens, rate limit, payload TTL).
- **Frontend (React + Vite)**
  - Portal com abas Certificados / Jobs / Dispositivos / Auditoria.
  - UI não recebe PFX/senha — apenas inicia jobs e acompanha status.
- **Agent Windows (.NET)**
  - Pareia device, faz polling de jobs, instala no `CurrentUser\My`.
  - Executa cleanup diário (task 18h).
- **Scheduler/Cleanup**
  - Task “CertHub Cleanup 18h” chamando `Certhub.Agent.exe --cleanup`.
- **Auditoria**
  - Eventos principais: `INSTALL_REQUESTED`, `INSTALL_APPROVED`, `INSTALL_DENIED`, `CERT_REMOVED_18H`, `PAYLOAD_DENIED`.

## Fluxo ponta a ponta

1. **Ingest** (DEV): catálogo do filesystem → `/admin/certificates/ingest-from-fs`.
2. **Listar**: portal carrega certificados e jobs do usuário.
3. **Solicitar install**: VIEW/ADMIN/DEV cria job via `/certificados/{id}/install`.
   - ADMIN/DEV/flag/device podem auto-aprovar.
   - VIEW sem auto-approve gera `REQUESTED`.
4. **Approve/Deny**: ADMIN/DEV aprova via `/install-jobs/{id}/approve` ou nega via `/install-jobs/{id}/deny`.
5. **Claim**: Agent pega jobs pendentes via `/agent/jobs` e faz `/claim`.
6. **Payload**: Agent baixa payload (`/agent/jobs/{id}/payload`).
7. **Done**: Agent envia resultado (`/agent/jobs/{id}/result`).
8. **Cleanup**: task 18h remove certificados temporários e registra auditoria.

## RBAC por role

- **VIEW**
  - Pode listar seus certificados/jobs e solicitar install **somente** em devices permitidos.
  - Não lista devices admin e não vê jobs globais.
- **ADMIN**
  - CRUD de usuários/devices/certificados.
  - Pode aprovar/nega jobs.
  - **Não** ativa `auto_approve` do device.
- **DEV**
  - Tudo do ADMIN.
  - Pode ativar `auto_approve` do device.
  - Pode executar ingest e rotinas de manutenção.

## Checklist de validação manual (smoke tests)

> Use os exemplos abaixo em **PowerShell** e substitua tokens/IDs.

### 1) Criar job como VIEW (REQUESTED)
```powershell
$job = Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/certificados/<CERT_ID>/install" `
  -Headers @{ Authorization = "Bearer <JWT_VIEW>" } `
  -ContentType "application/json" `
  -Body '{"device_id":"<DEVICE_ID>"}'
$job.status
```

### 2) Aprovar/Negar como ADMIN/DEV
```powershell
Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/install-jobs/<JOB_ID>/approve" `
  -Headers @{ Authorization = "Bearer <JWT_ADMIN>" } `
  -ContentType "application/json" `
  -Body '{"reason":"smoke test"}'

Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/install-jobs/<JOB_ID>/deny" `
  -Headers @{ Authorization = "Bearer <JWT_ADMIN>" } `
  -ContentType "application/json" `
  -Body '{"reason":"smoke test"}'
```

### 3) Auditoria
```sql
select action, actor_user_id, entity_id, timestamp, meta_json
from audit_log
where action in ('INSTALL_REQUESTED', 'INSTALL_APPROVED', 'INSTALL_DENIED')
order by timestamp desc
limit 20;
```

### 4) Heartbeat do agent
```powershell
Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/agent/heartbeat" `
  -Headers @{ Authorization = "Bearer <DEVICE_JWT>" } `
  -ContentType "application/json" `
  -Body '{"agent_version":"1.0.0"}'
```

## Troubleshooting (erros comuns)

- **403 device not allowed**: VIEW tentando instalar em device não vinculado (`user_device`).
- **403 forbidden**: role sem permissão para listar dispositivos admin ou jobs globais.
- **401 invalid credentials**: token de device inválido ou expirado.
- **409 payload denied**: token de payload reutilizado (single-use).
- **429 rate limit**: excesso de chamadas em `/agent/auth` ou payload.

## Definição de pronto (DoD) — S7

- [x] Fluxo REQUESTED → APPROVED/DENIED documentado e validado.
- [x] RBAC por role documentado (VIEW/ADMIN/DEV).
- [x] Auditoria cobrindo INSTALL_* e cleanup.
- [x] README com quickstart, config, smoke tests e rotina do agent.
- [x] Changelog com release notes da S7.
- [x] Tests (`pytest -q`) e checks automáticos executados.
