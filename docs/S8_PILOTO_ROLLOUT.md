# S8 — Piloto e rollout (runbook)

> **Objetivo do piloto**: operar em **2 máquinas** por **1 semana** sem fricção.

## Critérios de saída

- 2 usuários conseguem instalar certificados sem intervenção manual excessiva.
- Jobs percorrem **REQUESTED → PENDING → DONE** quando aprovados.
- **Cleanup 18h** roda diariamente e registra auditoria.
- Sem incidentes de acesso indevido ao PFX/senha via portal.

---

## Pré-requisitos do host (backend)

- Windows com PowerShell.
- Docker (para Postgres via `infra/docker-compose.yml`).
- Python 3.10+.
- `psql` disponível (opcional, mas recomendado).
- Porta **8010** liberada no host do backend.

---

## Subir Postgres

```bash
docker compose -f infra/docker-compose.yml up -d
```

---

## Subir backend (API)

```powershell
python -m venv .venv
.venv\Scripts\activate

cd backend
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

**Validação:**

```powershell
curl http://localhost:8010/health
```

Esperado: `{"status":"ok"}`

---

## Smoke test (PowerShell)

Execução direta:

```powershell
.\scripts\windows\s8_smoke.ps1
```

Execução garantida (Windows PowerShell, mesmo sem `powershell` no PATH):

```powershell
& "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File .\scripts\windows\s8_smoke.ps1
```

> Nota: `pwsh` é PowerShell 7 (opcional). Se não estiver instalado, use o caminho absoluto acima.

---

## Provisionar device (ADMIN/DEV)

```powershell
$device = Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/admin/devices" `
  -Headers @{ Authorization = "Bearer <JWT_ADMIN>" } `
  -ContentType "application/json" `
  -Body '{"hostname":"PC-01","domain":"NETOCMS","os_version":"Windows 11","agent_version":"1.0.0"}'

$device.device_token
$device.id
```

---

## Publish + Install do Agent (Windows)

### Publish

```powershell
.\scripts\windows\publish_agent.ps1 -PublishDir C:\Temp\CerthubAgent\publish
```

**Parâmetros úteis**:
- `-PublishDir` (destino do publish)

### Install

```powershell
.\scripts\windows\install_agent.ps1 -PublishDir C:\Temp\CerthubAgent\publish
```

**Validação da task:**

```powershell
schtasks /Query /TN "CertHub Cleanup 18h" /V /FO LIST
```

### Pair (tray)

1. Execute `Certhub.Agent.exe`.
2. Menu do tray → **Pair device**.
3. Informe:
   - `API Base URL`: `http://<HOST_BACKEND>:8010/api/v1`
   - `Device ID`
   - `Device Token`

---

## Validar heartbeat e jobs (agent)

### Autenticar agent (gera JWT)

```powershell
$auth = Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/agent/auth" `
  -ContentType "application/json" `
  -Body (@{ device_id = "<DEVICE_ID>"; device_token = "<DEVICE_TOKEN>" } | ConvertTo-Json)
$agentJwt = $auth.access_token
```

### Heartbeat

```powershell
Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/agent/heartbeat" `
  -Headers @{ Authorization = "Bearer $agentJwt" } `
  -ContentType "application/json" `
  -Body '{"agent_version":"1.0.0"}'
```

### Listar jobs

```powershell
Invoke-RestMethod "http://localhost:8010/api/v1/agent/jobs" `
  -Headers @{ Authorization = "Bearer $agentJwt" }
```

---

## Fluxo E2E (VIEW → REQUESTED → ADMIN approve → agent DONE)

### 1) VIEW cria job (REQUESTED)

```powershell
$job = Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/certificados/<CERT_ID>/install" `
  -Headers @{ Authorization = "Bearer <JWT_VIEW>" } `
  -ContentType "application/json" `
  -Body '{"device_id":"<DEVICE_ID>"}'

$job.status
$job.id
```

### 2) ADMIN/DEV aprova (REQUESTED → PENDING)

```powershell
Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/install-jobs/$($job.id)/approve" `
  -Headers @{ Authorization = "Bearer <JWT_ADMIN>" } `
  -ContentType "application/json" `
  -Body '{"reason":"piloto"}'
```

### Evidências

- Logs do agent: `%LOCALAPPDATA%\CertHubAgent\logs\agent.log`
- `audit_log` registra `INSTALL_REQUESTED` e `INSTALL_APPROVED`

---

## Cleanup 18h

### Execução manual

```powershell
C:\ProgramData\CertHubAgent\publish\Certhub.Agent.exe --cleanup --mode manual
```

### Validar task

```powershell
schtasks /Query /TN "CertHub Cleanup 18h" /V /FO LIST
```

### Rodar task

```powershell
schtasks /Run /TN "CertHub Cleanup 18h"
```

### Logs

```powershell
Get-Content "$env:LOCALAPPDATA\CertHubAgent\logs\agent.log" -Tail 80
```

### Auditoria (psql)

```sql
select action, meta_json, timestamp
from audit_log
where action = 'CERT_REMOVED_18H'
order by timestamp desc
limit 10;
```

---

## Auditoria / consultas psql

### INSTALL_REQUESTED / APPROVED / DENIED

```sql
select action, actor_user_id, entity_id, timestamp, meta_json
from audit_log
where action in ('INSTALL_REQUESTED', 'INSTALL_APPROVED', 'INSTALL_DENIED')
order by timestamp desc
limit 20;
```

### CERT_REMOVED_18H

```sql
select action, actor_device_id, meta_json, timestamp
from audit_log
where action = 'CERT_REMOVED_18H'
order by timestamp desc
limit 10;
```

### Devices (last_seen / versão)

> Nota: as colunas `last_seen_at` e `last_heartbeat_at` podem variar conforme migrations.
> Se não existirem no seu schema, remova-as da query.

```sql
select id, hostname, domain, os_version, agent_version, last_seen_at, last_heartbeat_at, is_allowed
from devices
order by created_at desc
limit 20;
```

---

## Troubleshooting (top 10)

1. **Base URL errada**: faltou `/api/v1` no agent/pair.
2. **Porta**: padrão do repo é **8010** (README). `API_PORT` do `.env` **não** é consumido pelo backend.
3. **Task não criada**: ver `schtasks /Query /TN "CertHub Cleanup 18h"`.
4. **agent.log não existe**: executar o tray ao menos 1x para gerar logs.
5. **Device token incorreto/rotacionado**: re-provisionar/rotacionar e parear novamente.
6. **Job preso**: validar claim/payload/result; verificar status no `/api/v1/agent/jobs`.
7. **DB indisponível**: `alembic upgrade head` falha ou API retorna 500.
8. **Permissão no store do Windows**: confirme execução no **CurrentUser**.
9. **Cleanup não roda**: checar se a task aponta para o EXE correto.
10. **Endpoint health falha**: API não iniciou ou porta bloqueada.

---

## Rollback operacional

```powershell
Unregister-ScheduledTask -TaskName "CertHub Cleanup 18h" -Confirm:$false
Remove-Item C:\ProgramData\CertHubAgent -Recurse -Force
Remove-Item "$env:LOCALAPPDATA\CertHubAgent" -Recurse -Force
```

> Atenção: a remoção de `%LOCALAPPDATA%\CertHubAgent` apaga `config.json`, `secrets.dat` e `installed_thumbprints.json`.
