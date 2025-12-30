# CertHub — Portal de Certificados com Agent

Objetivo: substituir o diretório público de `.pfx` por um fluxo controlado via **Portal (React) + API + Agent Windows**, com:
- instalação no **CurrentUser** sem o usuário ter acesso ao arquivo nem à senha
- controle de acesso via **RBAC global** + flags por usuário
- **auditoria** completa
- remoção automática às **18:00** dos certificados temporários instalados pelo Agent

> Regra de ouro: o **navegador nunca recebe PFX/senha** — a UI apenas cria/acompanha jobs.

## Arquitetura (alto nível)
- **Backend/API**: mantém catálogo (ingest), cria jobs e registra auditoria
- **Frontend/Portal**: UI SaaS (tema azul escuro) com abas Certificados/Jobs/Dispositivos/Auditoria
- **Agent Windows**: registra device, faz polling de jobs, instala no store do usuário e remove às 18h (S5)

## Estrutura do repo
- `backend/`: FastAPI + Alembic + Postgres
- `frontend/`: React (Vite) com layout do protótipo SaaS e integração à API
- `infra/`: docker-compose (Postgres)

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

## Quickstart (dev)

### 1) Subir Postgres
```bash
docker compose -f infra/docker-compose.yml up -d
````

### 2) Backend

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate

pip install -r requirements.txt

cd backend
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
```

### 3) Frontend

```bash
cd frontend
npm install
npm run dev
```

## Quickstart Agent Windows (S4)

1) Provisionar device e token (ADMIN/DEV) no portal ou via API:

```powershell
$device = Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/admin/devices" `
  -Headers @{ Authorization = "Bearer <JWT_ADMIN>" } `
  -ContentType "application/json" `
  -Body '{"hostname":"PC-01","domain":"NETOCMS","os_version":"Windows 11","agent_version":"1.0.0"}'

$device.device_token
$device.id
```

2) Build/publish do agent:

```powershell
Set-Location agent\windows\Certhub.Agent
dotnet restore
dotnet publish -c Release -r win-x64 --self-contained true `
  /p:PublishSingleFile=true /p:IncludeNativeLibrariesForSelfExtract=true `
  -o C:\Temp\CerthubAgent\publish
```

Alternativa com script (PowerShell):

```powershell
.\scripts\windows\publish_agent.ps1 -PublishDir C:\Temp\CerthubAgent\publish
```

## Instalação oficial do Agent (ProgramData + Task 18h)

Publica (ou reutiliza um diretório já publicado) e instala em:
`C:\ProgramData\CertHubAgent\publish\Certhub.Agent.exe`

```powershell
Set-Location agent\windows\Certhub.Agent
.\INSTALL.ps1
```

Caso já tenha o publish pronto:

```powershell
Set-Location agent\windows\Certhub.Agent
.\INSTALL.ps1 -PublishDir C:\Temp\CerthubAgent\publish
```

## Agent Windows – Build/Publish

```powershell
Set-Location agent\windows\Certhub.Agent
dotnet restore
dotnet build -c Release
dotnet publish -c Release -r win-x64 --self-contained true `
  /p:PublishSingleFile=true /p:IncludeNativeLibrariesForSelfExtract=true `
  -o C:\Temp\CerthubAgent\publish
```

O executável publicado pode ser usado para instalar no ProgramData via `INSTALL.ps1`.

## S5 Cleanup 18h (Regra das 18h)

- **Rodar cleanup manual** (headless):

```powershell
C:\ProgramData\CertHubAgent\publish\Certhub.Agent.exe --cleanup --mode manual
```

- **Validar a Scheduled Task** (instalada via `INSTALL.ps1`):

```powershell
schtasks /Query /TN "CertHub Cleanup 18h" /V /FO LIST
schtasks /Run /TN "CertHub Cleanup 18h"
```

- **Validar log do agent**:

```powershell
Get-Content "$env:LOCALAPPDATA\CertHubAgent\logs\agent.log" -Tail 60
```

- **Validar auditoria no DB** (Postgres):

```sql
select action, meta_json, timestamp
from audit_log
where action = 'CERT_REMOVED_18H'
order by timestamp desc
limit 5;
```

### HealthCheck S5 (ProgramData + Task 18h)

**Critérios de aceite**
- Task “CertHub Cleanup 18h” existe e o **Task To Run** aponta para `C:\ProgramData\CertHubAgent\publish\Certhub.Agent.exe`.
- `schtasks /Run` executa e o `agent.log` registra **“Starting cleanup (Scheduled)”**.
- O banco registra `audit_log` com action `CERT_REMOVED_18H`.

1) Confirmar “Task To Run” está em ProgramData

```powershell
$taskName = "CertHub Cleanup 18h"
schtasks /Query /TN "$taskName" /V /FO LIST |
  Select-String "Tarefa a ser executada|Task To Run|Modo de Logon|Executar como Usuário"
```

2) Executar a task agora e checar log

```powershell
$taskName = "CertHub Cleanup 18h"
schtasks /Run /TN "$taskName"
Start-Sleep -Seconds 2
Get-Content "$env:LOCALAPPDATA\\CertHubAgent\\logs\\agent.log" -Tail 60
```

Aceite aqui: aparecer `Starting cleanup (Scheduled)`.

3) Validar auditoria no Postgres (psql)

```powershell
$psqlUrl = $env:DATABASE_URL `
  -replace '^postgresql\\+psycopg2', 'postgresql' `
  -replace '\\?.*$', ''

psql $psqlUrl -c "
select action, actor_device_id, timestamp, meta_json
from audit_log
where action = 'CERT_REMOVED_18H'
order by timestamp desc
limit 10;"
```

**Rollback S5**

```powershell
Unregister-ScheduledTask -TaskName "CertHub Cleanup 18h" -Confirm:$false
```

## S6 Job Control / Agent Hardening

### Fluxo completo (REQUESTED/PENDING → CLAIM → PAYLOAD → RESULT)
1. **Portal cria o job** (`REQUESTED`/`PENDING`).
2. **Agent faz CLAIM**: `POST /api/v1/agent/jobs/{job_id}/claim`.
3. **Agent busca PAYLOAD**: `GET /api/v1/agent/jobs/{job_id}/payload?token=...`.
4. **Agent envia RESULT**: `POST /api/v1/agent/jobs/{job_id}/result`.

Estados esperados: `REQUESTED|PENDING → IN_PROGRESS → DONE|FAILED`.

### Regras de segurança (Job Control)
- **TTL do payload token**: 120s (single-use).
- **Token single-use**: 2ª tentativa retorna 409 e registra `PAYLOAD_DENIED` (`token_used`).
- **Rate limit** por device/IP no payload.
- **/result idempotente**: replay retorna 409 com `RESULT_DUPLICATE` (ou `RESULT_DENIED`).

### Validações (backend)
```bash
cd backend
alembic upgrade head
pytest
python -m pytest -q ./tests/test_agent_payload_hardening.py ./tests/test_agent_job_controls.py
```

### Exemplos de chamadas (simulação de erros)

**Token mismatch (403)**
```bash
curl -X GET "http://localhost:8010/api/v1/agent/jobs/<job_id>/payload?token=wrong" \
  -H "Authorization: Bearer <DEVICE_JWT>"
```

**Token expired (410)** (após expirar o payload token no DB)
```bash
curl -X GET "http://localhost:8010/api/v1/agent/jobs/<job_id>/payload?token=<token>" \
  -H "Authorization: Bearer <DEVICE_JWT>"
```

**Token already used (409)** (replay do mesmo token)
```bash
curl -X GET "http://localhost:8010/api/v1/agent/jobs/<job_id>/payload?token=<token>" \
  -H "Authorization: Bearer <DEVICE_JWT>"
```

**Rate limit (429)**
```bash
for i in {1..10}; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -H "Authorization: Bearer <DEVICE_JWT>" \
    "http://localhost:8010/api/v1/agent/jobs/<job_id>/payload?token=<token>"
done
```

### Operação / diagnóstico

**Reaper de jobs presos**
```bash
curl -X POST "http://localhost:8010/api/v1/admin/jobs/reap?threshold_minutes=60" \
  -H "Authorization: Bearer <JWT_ADMIN>"
```

**Significados de status/error_code**
- `DONE`: instalação concluída
- `FAILED`: falha na instalação (`error_code`/`error_message`)
- `TIMEOUT`: job reaped (stuck `IN_PROGRESS`)

### Queries úteis (Postgres)

**Jobs presos IN_PROGRESS há X minutos**
```sql
select id, device_id, started_at, status
from cert_install_jobs
where status = 'IN_PROGRESS'
  and started_at <= now() - interval '60 minutes'
order by started_at;
```

**Auditorias PAYLOAD_DENIED / RATE_LIMITED / RESULT_DUPLICATE**
```sql
select action, actor_device_id, meta_json, timestamp
from audit_log
where action in ('PAYLOAD_DENIED', 'PAYLOAD_RATE_LIMITED', 'RESULT_DUPLICATE')
  and timestamp >= now() - interval '7 days'
order by timestamp desc;
```

**Últimos jobs por device**
```sql
select device_id, max(created_at) as last_job_at
from cert_install_jobs
group by device_id
order by last_job_at desc;
```

```bash
git revert <commit_sha>
```

3) Executar o `Certhub.Agent.exe` (tray app). No menu do tray:

- **Pair device**: informe `API Base URL` (ex.: `http://localhost:8010/api/v1`), `Device ID` e `Device Token`.
- **Iniciar com Windows** fica habilitado por padrão (HKCU Run).
- **Polling idle/ativo**: padrão 30s (idle) / 5s (ativo) para reduzir o tempo de claim
  (defaults em `agent/windows/Certhub.Agent/Certhub.Agent/Models/AgentConfig.cs`).
- (Opcional) configurar `Portal URL` para abrir o frontend.

4) Teste rápido:

- No portal, crie um job de instalação para o device.
- O agent deve fazer claim, baixar payload e instalar no `Current User > Personal` (`certmgr.msc`).
- O job passa para DONE com thumbprint.

## Deploy do Agent em outras máquinas (piloto)

1) Copiar o executável publicado para a máquina alvo (ex.):
   - **Recomendado**: `C:\ProgramData\CertHubAgent\publish\Certhub.Agent.exe` (evita UAC do Program Files).
   - **Importante**: não execute o `.exe` diretamente de share/UNC; copie local primeiro
     (pode aparecer “Windows não pode acessar o dispositivo, caminho ou arquivo…”).
   - Exemplo de publish local: `dotnet publish ... -o C:\Temp\CerthubAgent\publish` e copiar depois para `C:\ProgramData\CertHubAgent\publish`.
   - Alternativa com script:

     ```powershell
     .\scripts\windows\deploy_agent.ps1 -SourceExe C:\Temp\CerthubAgent\publish\Certhub.Agent.exe -StartAgent
     ```

2) Executar **uma vez** para parear (tray → **Pair device**):
   - **API Base URL** (ex.: `https://<dominio>/api/v1`)
   - **Device ID** (um por máquina)
   - **Device Token** (gerado no portal / API)
3) Habilitar auto-start:
   - Marcar **Iniciar com Windows** (cria entry em HKCU Run).
   - Confirmar que o ícone do agent está em **Ícones ocultos** do tray (menu `^`).
4) Validar no portal/DB:
   - `last_heartbeat_at` atualizado (timestamps no DB são **UTC +00**, UI pode mostrar horário local).
   - Job vai de `PENDING` → `DONE` e grava thumbprint.

**Troubleshooting rápido**

- Tray não aparece → verifique **Ícones ocultos** do tray.
- “API Base: Not configured” na tela de status → executar **Pair device** novamente.
- “Auth failed” → Device ID/token inválido ou expirado.
- Job demora para claim → confira o polling atual no **CertHub Agent Status**.
- Erro 500 em login/agent auth com stacktrace de `psycopg2` → verifique se o Postgres está rodando
  (ex.: `127.0.0.1:5433`) e se `DATABASE_URL` aponta para o host/porta corretos.

## Variáveis de ambiente (.env)

Veja `.env.example`.

- `CERTS_ROOT_PATH`: caminho do diretório raiz com os `.pfx/.p12` (somente os arquivos diretos, subpastas são ignoradas).
- `OPENSSL_PATH`: binário do OpenSSL (ex.: `openssl` no Linux/macOS ou `C:\\Program Files\\OpenSSL-Win64\\bin\\openssl.exe` no Windows).
- `JWT_SECRET`, `ACCESS_TOKEN_TTL_MIN`, `REFRESH_TTL_DAYS`: chaves e TTLs para autenticação S2.
- `DEVICE_TOKEN_TTL_MIN`: TTL do JWT do device (agent).
- `ALLOW_LEGACY_HEADERS`: habilita headers `X-User-Id/X-Org-Id` **apenas em dev** para compatibilidade temporária.
- (Front) `VITE_API_URL`: URL base da API (padrão `/api/v1`).
- (Watcher S4.1) `ORG_ID`, `CERTIFICADOS_ROOT`, `WATCHER_DEBOUNCE_SECONDS`, `WATCHER_MAX_EVENTS_PER_MINUTE`, `REDIS_URL`, `RQ_QUEUE_NAME`.

## Watcher (S4.1)

> Rodar em paralelo ao backend, com Redis + RQ.

**Rodar em dev (PowerShell, terminais separados):**

```powershell
# Infra (Postgres + Redis)
docker compose -f infra/docker-compose.yml up -d
```

```powershell
# Worker (RQ)
Set-Location backend
$env:REDIS_URL="redis://localhost:6380/0"
$env:RQ_QUEUE_NAME="certs"
python -m app.workers.rq_worker
```

```powershell
# Watcher
Set-Location backend
$env:ORG_ID="1"
$env:CERTIFICADOS_ROOT="C:\certs"
$env:WATCHER_DEBOUNCE_SECONDS="2"
$env:WATCHER_MAX_EVENTS_PER_MINUTE="60"
$env:REDIS_URL="redis://localhost:6380/0"
$env:RQ_QUEUE_NAME="certs"
python -m app.watchers.pfx_directory
```

**Notas de delete (S4.1)**

- O worker tenta apagar primeiro por `source_path` normalizado.
- Se não encontrar, faz fallback por `name == <stem do arquivo>`.
- Logs do job mostram `strategy`, `rowcount` e `found_ids_count`.

**Job ID por ação (S4.1)**

- Ingest usa `cert_ing__<org_id>__<sha1(path_lower_normalized)>`.
- Delete usa `cert_del__<org_id>__<sha1(path_lower_normalized)>`.
- Isso evita colisões entre delete/ingest quando o mesmo arquivo é removido e reinserido.

**Paths UNC vs drive letter (S4.1)**

- Em Windows, paths como `\\servidor\share\certs\arquivo.pfx` podem divergir de `G:\certs\arquivo.pfx`.
- Para depuração, valide também por `name` (stem do arquivo), além de `source_path`.

**Inspeção rápida da fila (S4.1)**

```powershell
# Ver jobs na fila
python - <<'PY'
from app.workers.queue import get_queue, get_redis
q = get_queue(get_redis())
print("queued", q.count)
print("job_ids", q.job_ids)
PY
```

**Validação rápida (S4.1, PowerShell)**

```powershell
# Após copiar um .pfx válido para a raiz monitorada:
psql "$env:DATABASE_URL" -c "select id, source_path from certificates where source_path = 'C:\\certs\\teste.pfx';"

# Após deletar o arquivo monitorado:
psql "$env:DATABASE_URL" -c "select id from certificates where source_path = 'C:\\certs\\teste.pfx';"
```

### Validação S4.1 Watcher (checklist rápido)

```powershell
# Infra
docker compose -f infra/docker-compose.yml up -d

# Worker
Set-Location backend
$env:REDIS_URL="redis://localhost:6380/0"
$env:RQ_QUEUE_NAME="certs"
python -m app.workers.rq_worker
```

Em outro terminal:

```powershell
Set-Location backend
$env:ORG_ID="1"
$env:CERTIFICADOS_ROOT="C:\\certs"
$env:WATCHER_DEBOUNCE_SECONDS="2"
$env:WATCHER_MAX_EVENTS_PER_MINUTE="60"
$env:REDIS_URL="redis://localhost:6380/0"
$env:RQ_QUEUE_NAME="certs"
python -m app.watchers.pfx_directory
```

```powershell
# Created/modified (raiz)
Copy-Item "C:\\origem\\teste.pfx" "C:\\certs\\teste.pfx"
psql "$env:DATABASE_URL" -c "select id, source_path from certificates where source_path = 'C:\\certs\\teste.pfx';"

# Deleted (raiz)
Remove-Item "C:\\certs\\teste.pfx"
psql "$env:DATABASE_URL" -c "select id from certificates where source_path = 'C:\\certs\\teste.pfx';"

# Move para fora da raiz (delete)
Move-Item "C:\\certs\\teste.pfx" "C:\\origem\\teste.pfx"

# Move para dentro da raiz (ingest)
Move-Item "C:\\origem\\teste.pfx" "C:\\certs\\teste.pfx"
```

> Subpastas devem ser ignoradas (`C:\\certs\\sub\\teste.pfx` não entra no watcher).

**Rollback (S4.1)**

1. Parar watcher e worker.
2. Remover o serviço Redis do `infra/docker-compose.yml` (se não utilizado).
3. Reverter commits relacionados ao S4.1.

## S4 — Agent MVP (backend)

### Provisionar device/token (ADMIN/DEV)

```powershell
$device = Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/admin/devices" `
  -Headers @{ Authorization = "Bearer <JWT_ADMIN>" } `
  -ContentType "application/json" `
  -Body '{"hostname":"PC-01","domain":"NETOCMS","os_version":"Windows 11","agent_version":"1.0.0"}'

# Guarde o token: ele só aparece nesta resposta.
$device.device_token
$device.id
```

### Rotacionar token do device (ADMIN/DEV)

```powershell
$rotated = Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/admin/devices/$($device.id)/rotate-token" `
  -Headers @{ Authorization = "Bearer <JWT_ADMIN>" }

$rotated.device_token
```

### Auth do agent

```powershell
$auth = Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/agent/auth" `
  -ContentType "application/json" `
  -Body (@{ device_id = $device.id; device_token = $device.device_token } | ConvertTo-Json)

$agentJwt = $auth.access_token
```

### Heartbeat

```powershell
Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/agent/heartbeat" `
  -Headers @{ Authorization = "Bearer $agentJwt" } `
  -ContentType "application/json" `
  -Body '{"agent_version":"1.0.0"}'
```

### Fluxo de jobs (agent)

```powershell
# Listar jobs PENDING/IN_PROGRESS do device
Invoke-RestMethod "http://localhost:8010/api/v1/agent/jobs" `
  -Headers @{ Authorization = "Bearer $agentJwt" }

# Claim do job (PENDING -> IN_PROGRESS)
Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/agent/jobs/<JOB_ID>/claim" `
  -Headers @{ Authorization = "Bearer $agentJwt" }

# Payload (pfx_base64 + password)
Invoke-RestMethod "http://localhost:8010/api/v1/agent/jobs/<JOB_ID>/payload" `
  -Headers @{ Authorization = "Bearer $agentJwt" }

# Resultado (IN_PROGRESS -> DONE/FAILED)
Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/agent/jobs/<JOB_ID>/result" `
  -Headers @{ Authorization = "Bearer $agentJwt" } `
  -ContentType "application/json" `
  -Body '{"status":"DONE","thumbprint":"<TP>"}'
```

> Nota: o payload usa `certificate.source_path` e a senha é inferida do nome do arquivo (`senha` no filename).
> Se não houver senha no nome, o endpoint retorna 422 e o agent deve reportar erro.

### Rollback (S4)

1. Reverter a migration:
   ```bash
   cd backend && alembic downgrade -1
   ```
2. Reverter o commit do S4.

## Checklist de aceite (S4/S4.1)

### S4.1

- [ ] Redis rodando.
- [ ] Worker rodando.
- [ ] Watcher rodando.
- [ ] Adicionar `.pfx` na raiz ⇒ certificado no DB.
- [ ] Remover `.pfx` ⇒ delete no DB.
- [ ] Subpasta ignorada.
- [ ] Move para fora da raiz ⇒ delete no DB.
- [ ] Move para dentro da raiz ⇒ ingest no DB.

### S4 Agent

- [ ] Agent abre no tray e persiste config.
- [ ] Auto-start registry (HKCU Run) criado.
- [x] Heartbeat atualiza `last_heartbeat_at` no DB.
- [x] Polling encontra job PENDING.
- [x] Claim muda status para IN_PROGRESS e preenche `started_at/claimed_at`.
- [x] Payload baixa PFX + senha.
- [x] Certificado aparece no certmgr.msc (Current User > Personal).
- [x] Result marca DONE e grava thumbprint no DB.
- [x] `installed_thumbprints` (DPAPI) atualizado.

## S2 — Auth + RBAC (roteiro PowerShell)

> Os exemplos abaixo usam PowerShell 7+ no Windows.

### 1) Listar paths do OpenAPI
```powershell
$openapi = Invoke-RestMethod "http://localhost:8010/openapi.json"
$openapi.paths.PSObject.Properties.Name | Sort-Object
```

### 2) Set password (DEV/ADMIN/VIEW)
```powershell
# DEV/ADMIN gera token 1x para um usuário alvo (VIEW/ADMIN/DEV)
$setup = Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/auth/password/set/init" `
  -Headers @{ Authorization = "Bearer <JWT_DEV_OU_ADMIN>" } `
  -ContentType "application/json" `
  -Body '{"email": "view@netocontabilidade.com.br"}'

# Em DEV, o token é retornado no JSON; em PROD, apenas { ok: true }.
$setup.token

Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/auth/password/set/confirm" `
  -ContentType "application/json" `
  -Body (@{ token = $setup.token; new_password = "SenhaForte123!" } | ConvertTo-Json)
```

### 3) Login / me / refresh / logout (cookie HttpOnly)
```powershell
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession

$login = Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/auth/login" `
  -WebSession $session `
  -ContentType "application/json" `
  -Body '{"email": "maria@netocontabilidade.com.br", "password": "SenhaForte123!"}'

$access = $login.access_token

Invoke-RestMethod "http://localhost:8010/api/v1/auth/me" `
  -Headers @{ Authorization = "Bearer $access" }

# Refresh usa o cookie HttpOnly (não precisa enviar refresh_token no body)
$refreshed = Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/auth/refresh" `
  -WebSession $session
$refreshed.access_token

Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/auth/logout" `
  -WebSession $session `
  -Headers @{ Authorization = "Bearer $access" }
```

### 4) Lockout (5 falhas → 429)
```powershell
1..5 | ForEach-Object {
  Invoke-WebRequest -Method Post "http://localhost:8010/api/v1/auth/login" `
    -ContentType "application/json" `
    -Body '{"email": "maria@netocontabilidade.com.br", "password": "ERRADA"}' `
    -SkipHttpErrorCheck | Select-Object StatusCode
}

# 6ª tentativa bloqueada
Invoke-WebRequest -Method Post "http://localhost:8010/api/v1/auth/login" `
  -ContentType "application/json" `
  -Body '{"email": "maria@netocontabilidade.com.br", "password": "ERRADA"}' `
  -SkipHttpErrorCheck | Select-Object StatusCode
```

### 5) RBAC (VIEW 403 em /admin/users, 200 em /certificados)
```powershell
# VIEW tentando acessar admin/users → 403
Invoke-WebRequest "http://localhost:8010/api/v1/admin/users" `
  -Headers @{ Authorization = "Bearer <JWT_VIEW>" } `
  -SkipHttpErrorCheck | Select-Object StatusCode

# VIEW listando certificados → 200
Invoke-WebRequest "http://localhost:8010/api/v1/certificados" `
  -Headers @{ Authorization = "Bearer <JWT_VIEW>" } `
  -SkipHttpErrorCheck | Select-Object StatusCode
```

## Ingestão de certificados a partir do filesystem (DEV)

Endpoint DEV-only para ingestão rápida dos `.pfx/.p12` da pasta configurada em `CERTS_ROOT_PATH`:

```bash
curl -X POST "http://localhost:8010/api/v1/admin/certificates/ingest-from-fs" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: <UUID_DO_DEV>" -H "X-Org-Id: 1" \
  -d '{"dry_run": true, "limit": 5}'
```

* Campos opcionais: `dry_run` (true/false) e `limit` (0 = sem limite).
* A senha é deduzida do nome do arquivo (padrão "Senha ..."), caso contrário tenta vazia.
* Metadados extraídos via OpenSSL (`subject`, `issuer`, `serial`, `notBefore`, `notAfter`, `sha1`).
* Deduplicação por `sha1` (preferencial) ou `serial` por `org_id`; falhas de parse são registradas em `parse_error`.

## Segurança (S6)

* payload entregue somente ao Agent (JWT role=DEVICE + binding ao device)
* token one-time com TTL **120s** (retornado no claim)
* rate limit por device (auth **10/min**, payload **5/min**)
* auditoria: INSTALL_REQUESTED / INSTALL_CLAIMED / PAYLOAD_ISSUED / PAYLOAD_DENIED / PAYLOAD_RATE_LIMITED / INSTALL_DONE / INSTALL_FAILED / REMOVED_18H
* visibilidade de certificados é global por `org_id` (sem carteiras/permissões por certificado)
* se o payload falhar/expirar, o agent pode chamar `claim` novamente no mesmo job **IN_PROGRESS** para receber um novo `payload_token`

### Validação rápida (S6)

```powershell
# Auth do agent (device_id + device_token)
$auth = Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/agent/auth" `
  -ContentType "application/json" `
  -Body (@{ device_id = "<DEVICE_ID>"; device_token = "<DEVICE_TOKEN>" } | ConvertTo-Json)
$agentJwt = $auth.access_token

# Claim retorna payload_token
$claim = Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/agent/jobs/<JOB_ID>/claim" `
  -Headers @{ Authorization = "Bearer $agentJwt" } `
  -ContentType "application/json" `
  -Body "{}"
$claim.payload_token

# Payload exige token one-time via query string
Invoke-RestMethod "http://localhost:8010/api/v1/agent/jobs/<JOB_ID>/payload?token=$($claim.payload_token)" `
  -Headers @{ Authorization = "Bearer $agentJwt" }

# Reuso do token (esperado: 409)
Invoke-WebRequest "http://localhost:8010/api/v1/agent/jobs/<JOB_ID>/payload?token=$($claim.payload_token)" `
  -Headers @{ Authorization = "Bearer $agentJwt" } `
  -SkipHttpErrorCheck | Select-Object StatusCode
```

Auditoria:
```sql
select action, meta_json, timestamp
from audit_log
where action in ('PAYLOAD_ISSUED', 'PAYLOAD_DENIED', 'PAYLOAD_RATE_LIMITED')
order by timestamp desc
limit 10;
```

Rollback S6:
```bash
cd backend
alembic downgrade -1
git revert <commit_sha>
```

### Validação rápida (S6)

```powershell
# Auth do agent (device_id + device_token)
$auth = Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/agent/auth" `
  -ContentType "application/json" `
  -Body (@{ device_id = "<DEVICE_ID>"; device_token = "<DEVICE_TOKEN>" } | ConvertTo-Json)
$agentJwt = $auth.access_token

# Claim retorna payload_token
$claim = Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/agent/jobs/<JOB_ID>/claim" `
  -Headers @{ Authorization = "Bearer $agentJwt" } `
  -ContentType "application/json" `
  -Body "{}"
$claim.payload_token

# Payload exige token one-time via query string
Invoke-RestMethod "http://localhost:8010/api/v1/agent/jobs/<JOB_ID>/payload?token=$($claim.payload_token)" `
  -Headers @{ Authorization = "Bearer $agentJwt" }

# Reuso do token (esperado: 409)
Invoke-WebRequest "http://localhost:8010/api/v1/agent/jobs/<JOB_ID>/payload?token=$($claim.payload_token)" `
  -Headers @{ Authorization = "Bearer $agentJwt" } `
  -SkipHttpErrorCheck | Select-Object StatusCode
```

Auditoria:
```sql
select action, meta_json, timestamp
from audit_log
where action in ('PAYLOAD_ISSUED', 'PAYLOAD_DENIED', 'PAYLOAD_RATE_LIMITED')
order by timestamp desc
limit 10;
```

Rollback S6:
```bash
cd backend
alembic downgrade -1
git revert <commit_sha>
```

### Exemplo: habilitar auto-approve para um usuário VIEW

Endpoint ADMIN para atualizar um usuário existente (mesmo `org_id`) e permitir auto-approve em jobs de instalação:

```bash
curl -X PATCH "http://localhost:8010/api/v1/admin/users/<ID_DO_USUARIO>" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: <UUID_DEV_OU_ADMIN>" -H "X-Org-Id: 1" \
  -d '{"auto_approve_install_jobs": true}'
```

Campos opcionais no corpo: `auto_approve_install_jobs`, `role_global`, `is_active`, `ad_username`, `email`, `nome`.

## Stages

* S1: Base de dados + auditoria (tabelas users/devices/jobs/audit + seeds/rotas admin + middleware de auditoria)
* S2: Auth piloto + RBAC + skeleton do front (protótipo)
* S3+: Jobs + Agent MVP + limpeza às 18h + hardening
> As partes de S1/S2/S3/S4/S5/S6 estão todas descritas no plano (incluindo tabelas/endpoints e a política das 18h).
