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
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
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
$device = Invoke-RestMethod -Method Post "http://localhost:8000/api/v1/admin/devices" `
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
dotnet publish -c Release -r win-x64 --self-contained true /p:PublishSingleFile=true /p:IncludeNativeLibrariesForSelfExtract=true
```

3) Executar o `Certhub.Agent.exe` (tray app). No menu do tray:

- **Pair device**: informe `API Base URL` (ex.: `http://localhost:8000/api/v1`), `Device ID` e `Device Token`.
- **Iniciar com Windows** fica habilitado por padrão (HKCU Run).
- (Opcional) configurar `Portal URL` para abrir o frontend.

4) Teste rápido:

- No portal, crie um job de instalação para o device.
- O agent deve fazer claim, baixar payload e instalar no `Current User > Personal` (`certmgr.msc`).
- O job passa para DONE com thumbprint.

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
$device = Invoke-RestMethod -Method Post "http://localhost:8000/api/v1/admin/devices" `
  -Headers @{ Authorization = "Bearer <JWT_ADMIN>" } `
  -ContentType "application/json" `
  -Body '{"hostname":"PC-01","domain":"NETOCMS","os_version":"Windows 11","agent_version":"1.0.0"}'

# Guarde o token: ele só aparece nesta resposta.
$device.device_token
$device.id
```

### Rotacionar token do device (ADMIN/DEV)

```powershell
$rotated = Invoke-RestMethod -Method Post "http://localhost:8000/api/v1/admin/devices/$($device.id)/rotate-token" `
  -Headers @{ Authorization = "Bearer <JWT_ADMIN>" }

$rotated.device_token
```

### Auth do agent

```powershell
$auth = Invoke-RestMethod -Method Post "http://localhost:8000/api/v1/agent/auth" `
  -ContentType "application/json" `
  -Body (@{ device_id = $device.id; device_token = $device.device_token } | ConvertTo-Json)

$agentJwt = $auth.access_token
```

### Heartbeat

```powershell
Invoke-RestMethod -Method Post "http://localhost:8000/api/v1/agent/heartbeat" `
  -Headers @{ Authorization = "Bearer $agentJwt" } `
  -ContentType "application/json" `
  -Body '{"agent_version":"1.0.0"}'
```

### Fluxo de jobs (agent)

```powershell
# Listar jobs PENDING/IN_PROGRESS do device
Invoke-RestMethod "http://localhost:8000/api/v1/agent/jobs" `
  -Headers @{ Authorization = "Bearer $agentJwt" }

# Claim do job (PENDING -> IN_PROGRESS)
Invoke-RestMethod -Method Post "http://localhost:8000/api/v1/agent/jobs/<JOB_ID>/claim" `
  -Headers @{ Authorization = "Bearer $agentJwt" }

# Payload (pfx_base64 + password)
Invoke-RestMethod "http://localhost:8000/api/v1/agent/jobs/<JOB_ID>/payload" `
  -Headers @{ Authorization = "Bearer $agentJwt" }

# Resultado (IN_PROGRESS -> DONE/FAILED)
Invoke-RestMethod -Method Post "http://localhost:8000/api/v1/agent/jobs/<JOB_ID>/result" `
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
- [ ] Heartbeat atualiza `last_heartbeat_at` no DB.
- [ ] Polling encontra job PENDING.
- [ ] Claim muda status para IN_PROGRESS e preenche `started_at/claimed_at`.
- [ ] Payload baixa PFX + senha.
- [ ] Certificado aparece no certmgr.msc (Current User > Personal).
- [ ] Result marca DONE e grava thumbprint no DB.
- [ ] `installed_thumbprints` (DPAPI) atualizado.

## S2 — Auth + RBAC (roteiro PowerShell)

> Os exemplos abaixo usam PowerShell 7+ no Windows.

### 1) Listar paths do OpenAPI
```powershell
$openapi = Invoke-RestMethod "http://localhost:8000/openapi.json"
$openapi.paths.PSObject.Properties.Name | Sort-Object
```

### 2) Set password (DEV/ADMIN/VIEW)
```powershell
# DEV/ADMIN gera token 1x para um usuário alvo (VIEW/ADMIN/DEV)
$setup = Invoke-RestMethod -Method Post "http://localhost:8000/api/v1/auth/password/set/init" `
  -Headers @{ Authorization = "Bearer <JWT_DEV_OU_ADMIN>" } `
  -ContentType "application/json" `
  -Body '{"email": "view@netocontabilidade.com.br"}'

# Em DEV, o token é retornado no JSON; em PROD, apenas { ok: true }.
$setup.token

Invoke-RestMethod -Method Post "http://localhost:8000/api/v1/auth/password/set/confirm" `
  -ContentType "application/json" `
  -Body (@{ token = $setup.token; new_password = "SenhaForte123!" } | ConvertTo-Json)
```

### 3) Login / me / refresh / logout (cookie HttpOnly)
```powershell
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession

$login = Invoke-RestMethod -Method Post "http://localhost:8000/api/v1/auth/login" `
  -WebSession $session `
  -ContentType "application/json" `
  -Body '{"email": "maria@netocontabilidade.com.br", "password": "SenhaForte123!"}'

$access = $login.access_token

Invoke-RestMethod "http://localhost:8000/api/v1/auth/me" `
  -Headers @{ Authorization = "Bearer $access" }

# Refresh usa o cookie HttpOnly (não precisa enviar refresh_token no body)
$refreshed = Invoke-RestMethod -Method Post "http://localhost:8000/api/v1/auth/refresh" `
  -WebSession $session
$refreshed.access_token

Invoke-RestMethod -Method Post "http://localhost:8000/api/v1/auth/logout" `
  -WebSession $session `
  -Headers @{ Authorization = "Bearer $access" }
```

### 4) Lockout (5 falhas → 429)
```powershell
1..5 | ForEach-Object {
  Invoke-WebRequest -Method Post "http://localhost:8000/api/v1/auth/login" `
    -ContentType "application/json" `
    -Body '{"email": "maria@netocontabilidade.com.br", "password": "ERRADA"}' `
    -SkipHttpErrorCheck | Select-Object StatusCode
}

# 6ª tentativa bloqueada
Invoke-WebRequest -Method Post "http://localhost:8000/api/v1/auth/login" `
  -ContentType "application/json" `
  -Body '{"email": "maria@netocontabilidade.com.br", "password": "ERRADA"}' `
  -SkipHttpErrorCheck | Select-Object StatusCode
```

### 5) RBAC (VIEW 403 em /admin/users, 200 em /certificados)
```powershell
# VIEW tentando acessar admin/users → 403
Invoke-WebRequest "http://localhost:8000/api/v1/admin/users" `
  -Headers @{ Authorization = "Bearer <JWT_VIEW>" } `
  -SkipHttpErrorCheck | Select-Object StatusCode

# VIEW listando certificados → 200
Invoke-WebRequest "http://localhost:8000/api/v1/certificados" `
  -Headers @{ Authorization = "Bearer <JWT_VIEW>" } `
  -SkipHttpErrorCheck | Select-Object StatusCode
```

## Ingestão de certificados a partir do filesystem (DEV)

Endpoint DEV-only para ingestão rápida dos `.pfx/.p12` da pasta configurada em `CERTS_ROOT_PATH`:

```bash
curl -X POST "http://localhost:8000/api/v1/admin/certificates/ingest-from-fs" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: <UUID_DO_DEV>" -H "X-Org-Id: 1" \
  -d '{"dry_run": true, "limit": 5}'
```

* Campos opcionais: `dry_run` (true/false) e `limit` (0 = sem limite).
* A senha é deduzida do nome do arquivo (padrão "Senha ..."), caso contrário tenta vazia.
* Metadados extraídos via OpenSSL (`subject`, `issuer`, `serial`, `notBefore`, `notAfter`, `sha1`).
* Deduplicação por `sha1` (preferencial) ou `serial` por `org_id`; falhas de parse são registradas em `parse_error`.

## Segurança (MVP)

* payload de instalação entregue somente ao Agent (pendente no repo; evolui no S6: token one-time + expiração + device binding)
* auditoria: INSTALL_REQUESTED / CLAIM / DONE / FAILED / REMOVED_18H
* visibilidade de certificados é global por `org_id` (sem carteiras/permissões por certificado)

### Exemplo: habilitar auto-approve para um usuário VIEW

Endpoint ADMIN para atualizar um usuário existente (mesmo `org_id`) e permitir auto-approve em jobs de instalação:

```bash
curl -X PATCH "http://localhost:8000/api/v1/admin/users/<ID_DO_USUARIO>" \
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
