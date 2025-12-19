# CertHub — Portal de Certificados com Agent

Objetivo: substituir o diretório público de `.pfx` por um fluxo controlado via **Portal (React) + API + Agent Windows**, com:
- instalação no **CurrentUser** sem o usuário ter acesso ao arquivo nem à senha
- controle de acesso via **RBAC global** + flags por usuário
- **auditoria** completa
- remoção automática às **18:00** dos certificados temporários instalados pelo Agent

> Regra de ouro: o **navegador nunca recebe PFX/senha** — a UI apenas cria/acompanha jobs.

## Arquitetura (alto nível)
- **Backend/API**: mantém catálogo (ingest/watcher), cria jobs e entrega payload somente ao Agent
- **Frontend/Portal**: UI SaaS (tema azul escuro) com abas Certificados/Jobs/Dispositivos/Auditoria
- **Agent Windows**: registra device, faz polling de jobs, instala no store do usuário e remove às 18h

## Estrutura do repo
- `backend/`: FastAPI + Alembic + Postgres + Redis/RQ + watchers
- `frontend/`: React (Vite) com layout do protótipo SaaS
- `agent/`: app Windows (C#) responsável por instalação/limpeza
- `infra/`: docker-compose (Postgres + Redis)

## Requisitos
- Python 3.10+
- Node 18+
- Docker (recomendado para Postgres/Redis)
- (Agent) .NET 8 SDK

## Quickstart (dev)

### 1) Subir Postgres + Redis
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

### 3) Worker (RQ)

```bash
cd backend
python -m app.worker.rq_worker
```

### 4) Frontend

```bash
cd frontend
npm install
npm run dev
```

## Variáveis de ambiente (.env)

Veja `.env.example`.

- `CERTS_ROOT_PATH`: caminho do diretório raiz com os `.pfx/.p12` (somente os arquivos diretos, subpastas são ignoradas).
- `OPENSSL_PATH`: binário do OpenSSL (ex.: `openssl` no Linux/macOS ou `C:\\Program Files\\OpenSSL-Win64\\bin\\openssl.exe` no Windows).
- `JWT_SECRET`, `ACCESS_TOKEN_TTL_MIN`, `REFRESH_TTL_DAYS`: chaves e TTLs para autenticação S2.
- `ALLOW_LEGACY_HEADERS`: habilita headers `X-User-Id/X-Org-Id` **apenas em dev** para compatibilidade temporária.

## S2 — Auth + RBAC (validação local)

### 1) Aplicar migration
```bash
cd backend
alembic upgrade head
```

### 2) Verificar colunas/tabelas
```bash
psql "$DATABASE_URL" -c \
  "SELECT column_name FROM information_schema.columns \
   WHERE table_name='users' AND column_name IN \
   ('password_hash', 'password_set_at', 'failed_login_attempts', 'locked_until');"

psql "$DATABASE_URL" -c \
  "SELECT tablename FROM pg_tables \
   WHERE schemaname='public' AND tablename IN ('auth_tokens', 'user_sessions');"
```

### 3) Criar usuário (DEV) e gerar token 1x
```bash
curl -X POST "http://localhost:8000/api/v1/admin/users" \
  -H "Authorization: Bearer <JWT_DEV>" \
  -H "Content-Type: application/json" \
  -d '{"email": "maria@netocontabilidade.com.br", "nome": "Maria", "role_global": "ADMIN"}'
```

### 4) Definir senha (token 1x)
```bash
curl -X POST "http://localhost:8000/api/v1/auth/password/set/confirm" \
  -H "Content-Type: application/json" \
  -d '{"token": "<TOKEN_1X>", "new_password": "SenhaForte123!"}'
```

### 5) Login e /auth/me
```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "maria@netocontabilidade.com.br", "password": "SenhaForte123!"}'

curl -H "Authorization: Bearer <JWT_ADMIN>" \
  "http://localhost:8000/api/v1/auth/me"
```

### 6) Lockout (5 falhas)
```bash
for i in {1..5}; do
  curl -X POST "http://localhost:8000/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"email": "maria@netocontabilidade.com.br", "password": "ERRADA"}'
done
```

### 7) RBAC (200 vs 403)
```bash
# VIEW não lista jobs
curl -H "Authorization: Bearer <JWT_VIEW>" \
  "http://localhost:8000/api/v1/install-jobs"

# ADMIN lista jobs
curl -H "Authorization: Bearer <JWT_ADMIN>" \
  "http://localhost:8000/api/v1/install-jobs"
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

* payload de instalação entregue somente ao Agent (evolui no S6: token one-time + expiração + device binding)
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
