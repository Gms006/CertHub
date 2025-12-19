# Plano — Portal de Certificados com Agent (CertHub)

## Objetivo

Substituir o diretório público de arquivos **.pfx** por um fluxo controlado via **Portal (React) + API** e um **Agent Windows** em cada máquina, permitindo:

- Instalação do certificado no **CurrentUser** sem o usuário ter acesso direto ao arquivo nem à senha.
- Controle de acesso via **RBAC global** + flags por usuário (ex.: `auto_approve_install_jobs`).
- **Auditoria** completa de uso/instalação.
- **Desabilitar/remover automaticamente às 18h** todos os certificados “temporários” instalados pelo Agent.

> Observação de segurança (realista): se o certificado precisa existir na máquina para uso em assinadores/portais/SPED, sempre existe risco residual de extração por quem tem alto privilégio local. O objetivo aqui é **reduzir drasticamente a exposição**, centralizar o acesso e **auditar** tudo.

---

## Contexto atual (reuso do seu projeto)

Você já tem um pipeline robusto:

- `app/services/certificados_ingest.py`: varre a raiz, extrai metadados (subject/issuer/serial/validade/sha1), deduz senha pelo nome, faz upsert/dedup por serial/sha1 e remove registros ausentes.
- `app/worker/jobs_certificados.py`: jobs unitários/full/removal, com Redis/RQ.
- `app/worker/watchers.py`: watcher (sem recursão) com debounce/rate limit, enfileira ingest unitário ou remoção.
- API: `/api/v1/certificados/ingest` e `/api/v1/certificados` (via `v_certificados_status`).

**O que muda:** você mantém o ingest/watcher como “catálogo” e adiciona um **módulo de distribuição controlada + auditoria + agent**.

---

## Arquitetura alvo

### Componentes

1. **Backend/API (máquina da Maria, inicialmente)**

- Mantém watcher/ingest.
- Cria **Jobs de Instalação**.
- Entrega “pacotes” de instalação **somente para o Agent**.
- Armazena RBAC global/flags, devices e auditoria.

2. **Frontend/Portal (React) — base no protótipo SaaS (azul escuro)**

- **Base visual**: usar o protótipo React do canvas (**PortalCertificadosPrototype**) como layout padrão.
- **Tema**: identidade SaaS com azul escuro (gradiente `#0e2659 → #22489c`), cards brancos, tipografia limpa e badges de status.
- **Layout (Shell)**
  - Topbar com marca + usuário logado (identidade do AD exibida no header).
  - Sidebar com cards de política (ex.: “remoção às 18:00”, “Agent”, “Auditoria”).
  - Área principal com KPIs + navegação por abas.
- **Navegação (Tabs)**
  - **Certificados** (tela principal)
  - **Jobs**
  - **Dispositivos**
  - **Auditoria**
- **Certificados (UX do protótipo)**
  - KPI strip (totais, vencidos, vence em 7d, jobs ativos, devices OK).
  - Busca + filtros (status) + ordenação (validade/empresa/status).
  - Cards por empresa com: **Status**, **Validade**, **Dias restantes**, **Titular**, **Serial/SHA1**.
  - Modal “Instalar certificado” com **seleção de dispositivo** e CTA “Criar job de instalação”.
  - Toasts para feedback (job criado, device bloqueado, etc.).
- **Jobs (UX do protótipo)**
  - Tabela com quando/empresa/device/solicitante/status/resultado.
  - Botão “Atualizar” e indicadores de status (PENDING/IN_PROGRESS/DONE/FAILED/EXPIRED).
- **Dispositivos (UX do protótipo)**
  - Cards por device com: hostname, domínio, user hint, versão do agent, last seen, **Autorizado/Bloqueado**.
  - Ações: “Gerenciar”, “Autorizar” (apenas perfis admins).
- **Auditoria (UX do protótipo)**
  - Tabela por evento (timestamp, ator, action, entidade, meta).

> Regra de ouro de segurança no front: **o navegador nunca recebe PFX nem senha**; a UI apenas cria/acompanha **jobs**.

3. **Agent Windows (por máquina / por usuário)**

- Executa em background (tray app recomendado).
- Registra a máquina (“device”).
- Puxa jobs pendentes.
- Instala no **Cert:\CurrentUser\My** (store do usuário).
- Registra no backend (sucesso/erro).
- **Remove às 18h** os certificados que ele instalou como temporários.

### Premissas que orientam o desenho

- Ambiente: **Windows Domain Joined**, sem Entra ID.
- Uso: assinador local + portais + SPED/ASD → precisa estar no store do Windows.
- Instalação: **CurrentUser**.
- Política: remover/“desabilitar” às **18:00**.
- Escala: \~10 usuários.

---

## Estratégia de autenticação

### Caminho preferido (intranet): SSO do AD via Windows Integrated Authentication

Como o domínio é AD, o “SSO de verdade” hoje é:

- IIS/Reverse Proxy com **Windows Authentication** (Kerberos/NTLM) ativado.
- Endpoint `/auth/whoami` devolve o usuário AD (`NETOCMS\\Maria.clara`).
- O gateway emite um **JWT interno** do seu sistema (curto + refresh opcional).

**Benefícios:** sem senha no seu sistema, login instantâneo dentro da rede.

### Fallback simples (se não quiser IIS/Windows Auth no início): Magic Link

- Usuário informa e-mail `@netocontabilidade.com.br`.
- API envia link de login com token de uso único (expira rápido).

---

## Política de “não excluir o que já existia”

O Agent **nunca** deve remover certificados que:

- já existiam no `CurrentUser` antes do job, ou
- foram instalados manualmente, ou
- foram instalados por outro software.

**Como garantir:**

- Antes de importar, o Agent verifica se o thumbprint já existe no store. Se existir, ele **não marca como temporário**.
- O Agent mantém uma lista local **apenas dos thumbprints que ele instalou** (DPAPI).
- Às 18h ele remove **somente** essa lista.

---

## Modelo de dados (mínimo)

### Tabelas novas

1. `users`

- `id`, `org_id`, `ad_username`, `email`, `nome`, `is_active`, `created_at`
- RBAC:
  - `role_global` (DEV | ADMIN | VIEW)
  - `auto_approve_install_jobs` (bool, default false)
- **Autenticação (S2)**:
  - `password_hash` (nullable, vazio até primeira configuração)
  - `password_set_at` (nullable, timestamp da primeira senha)
  - `failed_login_attempts` (int, default 0)
  - `locked_until` (nullable, timestamp de desbloqueio por lockout)

2. `devices`

- `id` (uuid), `org_id`, `hostname`, `domain`, `os_version`, `agent_version`, `last_seen_at`, `is_allowed`
- opcional: `public_key` (para criptografar pacotes para o device)

3. `user_device`

- vínculo: `user_id`, `device_id`, `is_allowed`

4. `cert_install_jobs`

- `id` (uuid), `org_id`, `certificado_id`, `empresa_id` (opcional), `requested_by_user_id`
- `target_user_id` (quem vai receber), `target_device_id`
- `status` (REQUESTED, PENDING, IN\_PROGRESS, DONE, FAILED, EXPIRED, CANCELED)
- `expires_at`, `created_at`, `started_at`, `finished_at`
- `error_code`, `error_message`
- NOVO:
  - `approved_by_user_id` (nullable)
  - `approved_at` (nullable)

5. `audit_log`

- `id`, `org_id`, `actor_user_id` (ou `actor_device_id`), `action`, `entity_type`, `entity_id`, `timestamp`, `ip`, `meta_json`

6. `auth_tokens` (novo em S2)

- `id` (uuid), `user_id`, `token_hash` (SHA256), `purpose` (SET_PASSWORD | RESET_PASSWORD | REFRESH)
- `expires_at`, `created_at`, `used_at` (nullable)
- índice: (token_hash, purpose, expires_at)

7. `user_sessions` (opcional, recomendado em S2)

- `id` (uuid), `user_id`, `refresh_token_hash` (SHA256), `ip`, `user_agent`
- `created_at`, `expires_at`, `revoked_at` (nullable)
- índice: (refresh_token_hash, user_id)

### Ajustes na tabela `certificados`

- Ideal: **não** persistir `senha` em texto puro.
- Sugestão: adicionar campos:
  - `secret_ref` (ponteiro para vault/DPAPI)
  - `password_encrypted` (se ficar no DB, sempre criptografado com chave fora do DB)

---

## Endpoints (contrato sugerido)

### Auth (S1: Windows Auth / S2: email+senha)

**First-time password setup:**
- `POST /auth/password/set/init` → recebe `email`, retorna link 1x (token em URL, TTL 1h)
- `POST /auth/password/set/confirm` → recebe `token` + `new_password`, seta `password_hash` + `password_set_at`

**Login normal:**
- `POST /auth/login` → recebe `email` + `password`, valida lockout, gera JWT + refresh token
  - Resposta: `{ "access_token": "...", "refresh_token": "...", "user": {...} }`
  - Status 429 (Too Many Requests) se `failed_login_attempts >= 5` antes de `locked_until`
- `POST /auth/refresh` → recebe `refresh_token`, emite novo JWT (sem renovar refresh se ainda válido)
- `POST /auth/logout` → revoga refresh token (marca `revoked_at` em user_sessions)

**Password reset:**
- `POST /auth/password/reset/init` → recebe `email`, envia link 1x (token em URL, TTL 30min)
- `POST /auth/password/reset/confirm` → recebe `token` + `new_password`, seta nova `password_hash`

**Info:**
- `GET /auth/me` → retorna dados do user autenticado (requer JWT válido)

### Portal

- `GET /api/v1/certificados` (já existe)
- `POST /api/v1/certificados/{id}/install` → cria `cert_install_job` (valida RBAC global + auto-approve + device)
- `GET /api/v1/install-jobs?mine=true` → status para o usuário

### Agent

- `POST /api/v1/agent/register` → registra device (primeira execução)
- `POST /api/v1/agent/heartbeat` → last\_seen + versão
- `GET /api/v1/agent/jobs?device_id=...` → lista jobs pendentes para o device
- `POST /api/v1/agent/jobs/{job_id}/claim` → marca IN\_PROGRESS (one-time)
- `GET /api/v1/agent/jobs/{job_id}/payload` → entrega pacote (pfx + senha) somente para agent
- `POST /api/v1/agent/jobs/{job_id}/result` → DONE/FAILED + thumbprint

**Pacote de payload (recomendado):**

- `pfx_bytes_base64` + `password` criptografados para o device (usando `public_key` do device) **ou**
- payload em TLS + token one-time + expiração curtíssima (mínimo viável).

---

## Agent Windows — comportamento

### Forma

- **Tray app** (WinForms/WPF) é o melhor custo/benefício.
- Inicializa com o Windows (HKCU Run) e também cria uma **Scheduled Task** diária às 18:00.

### Funções

1. **Registro do device**

- Coleta hostname/domínio/versão.
- Gera `device_id`.
- (Opcional forte) gera um par de chaves e envia `public_key`.

2. **Execução de jobs**

- Polling a cada 10–30s (ajustável) ou websocket (futuro).
- Para cada job:
  - `claim`
  - baixa `payload`
  - importa no CurrentUser store
  - pega thumbprint
  - grava localmente como “temporário instalado por mim” (se não existia antes)
  - envia `result`

3. **Limpeza às 18h**

- Task chama o próprio agent com argumento `--cleanup`.
- O agent remove os thumbprints armazenados como “temporários” e limpa a lista.

### Importação do certificado

- Preferência: importar sem opção “exportável”.
- Implementação prática (mínimo viável):
  - Agent cria um arquivo temporário em pasta do usuário (ACL restrita), importa via ferramenta do Windows e apaga o arquivo.
  - Alternativa: importar via API .NET a partir de bytes (sem arquivo), mantendo flags adequadas.

---

## Hospedagem inicial na máquina da Maria (ok para piloto)

### Requisitos mínimos para não virar dor de cabeça

- IP fixo ou DNS interno (ex.: `portal.netocms.local`).
- Serviço sempre ligado.
- API e front expostos na LAN (porta 443 recomendado).
- HTTPS (mesmo self-signed) e confiança instalada nas máquinas (GPO facilita).
- Backup do DB e do diretório de certificados.

> Migração futura para servidor: transparente se você manter URLs por DNS e variáveis de ambiente.

---

# Fluxo de desenvolvimento por stages

## S0 — Blueprint e baseline

**Entregáveis**

- Documento de arquitetura (este) validado.
- Lista de requisitos/políticas (18h, CurrentUser, auditoria, RBAC).
- Definição do modo de autenticação inicial: Windows Auth (preferido) ou Magic Link (piloto).

**Aceite**

- Time concorda com escopo e limitações.

---

## S1 — Base de dados e auditoria

**Objetivo**: criar tabelas `users/devices/jobs/audit` e integrar ao `org_id`.

**Decisão**: **visibilidade global de certificados (sem carteiras)**. Não há vínculo por empresa/certificado; apenas RBAC global + flags por usuário.

**Entregáveis**

- Migração Alembic.
- Seeds/rotas admin mínimas para cadastrar usuários e devices.
- Middleware de auditoria (log básico por endpoint).

**Status**: ✅ **Concluído**

**Evidências (S1)**

- [x] Migrações aplicadas (`alembic upgrade head` OK).
- [x] Ingest-from-fs funcionando: **323 total / 320 updated / 3 failed (esperados)**.
- [x] `audit_log` registrando: `CERT_INGEST_FROM_FS`, `INSTALL_REQUESTED`, `INSTALL_APPROVED`.
- [x] Smoke tests de install job:
  - VIEW com `auto_approve_install_jobs=false` → `REQUESTED`.
  - VIEW com `auto_approve_install_jobs=true` → `PENDING` + `approved_at`.
  - ADMIN/DEV → `PENDING` + `approved_at`.

**Checklist de validação S1 (reproduzível)**

1. Contar certificados:
   ```bash
   psql "$DATABASE_URL" -c "select count(*) from certificates;"
   ```
2. Ver últimos logs de auditoria:
   ```bash
   psql "$DATABASE_URL" -c "select action, entity_type, entity_id, timestamp from audit_log order by timestamp desc limit 10;"
   ```
3. Listar certificados via API (retorna todos do org):
   ```bash
   curl -H "X-User-Id: <UUID_VIEW>" -H "X-Org-Id: 1" \
     "http://localhost:8000/api/v1/certificados"
   ```
4. Criar install job (VIEW, sem auto-approve → REQUESTED):
   ```bash
   curl -X POST "http://localhost:8000/api/v1/certificados/<CERT_ID>/install" \
     -H "Content-Type: application/json" \
     -H "X-User-Id: <UUID_VIEW>" -H "X-Org-Id: 1" \
     -d '{"device_id": "<DEVICE_ID>"}'
   ```
5. Criar install job (VIEW com auto-approve ou ADMIN/DEV → PENDING + approved):
   ```bash
   curl -X POST "http://localhost:8000/api/v1/certificados/<CERT_ID>/install" \
     -H "Content-Type: application/json" \
     -H "X-User-Id: <UUID_ADMIN_OU_VIEW_AUTO>" -H "X-Org-Id: 1" \
     -d '{"device_id": "<DEVICE_ID>"}'
   ```- Aprovar job (ADMIN/DEV):
   ```bash
   curl -X POST "http://localhost:8000/api/v1/install-jobs/<JOB_ID>/approve" \
     -H "X-User-Id: <UUID_ADMIN>" -H "X-Org-Id: 1"
   ```
---

## S2 — Auth (piloto) + RBAC + Skeleton do Front (protótipo)

**Objetivo**: login no portal e RBAC global, já com a UI do protótipo rodando.

**Status**: 🟡 Em andamento

**Evidências (S2 em andamento)**

- Migração criada para `auth_tokens/user_sessions` e colunas de auth em `users` (alembic 0007).
- Endpoints `/auth/*` implementados com JWT + refresh cookie e lockout.
- Skeleton do front com páginas `Login`, `SetPassword`, `ResetPassword` e hook `useAuth`.

**Padrão S2: Email+Senha (usuários pré-criados)**

Não há auto-cadastro. Admin cria usuários no banco (is_active=true) e distribui link 1x para definir senha no primeiro acesso.

**Fluxos de autenticação:**

- **Novo usuário (primeiro acesso)**
  - Admin via POST `/api/v1/admin/users` (requer role DEV/ADMIN) cria user com `is_active=true`, `password_hash=NULL`
  - API retorna `setup_token` (1x, TTL 10 min) no response
  - Admin envia link: `http://portal.netocms.local/auth/set-password?token=<SETUP_TOKEN>` (válido por **10 min**)
  - User acessa link e faz POST `/auth/password/set/confirm` com `token` + `new_password`
  - Após isso: `password_hash` é preenchido (bcrypt), `password_set_at` marcado
  
- **Login normal** (sempre que voltar)
  - POST `/auth/login` com `email` + `password`
  - Retorna: `{ "access_token": "...", "refresh_token": "...", "user": {...} }`
  - Access JWT: TTL **30 min** (curto)
  - Refresh token: HttpOnly cookie, TTL **14 dias**, rotacionável
  
- **Esqueci senha**
  - POST `/auth/password/reset/init` com `email`
  - Link: `http://portal.netocms.local/auth/reset-password?token=<TOKEN>` (válido por **30 min**)
  - POST `/auth/password/reset/confirm` com `token` + `new_password`
  
- **Segurança de lockout**
  - Após 5 tentativas de login falhadas → `locked_until` marcado (bloqueia por **15 min**)
  - Retorna HTTP 429 (Too Many Requests) durante lockout
  - Admin pode resetar manualmente: `UPDATE users SET failed_login_attempts=0, locked_until=NULL WHERE email='...'`

**Modo futuro (Windows Auth via IIS)**

- Caminho A (intranet/ideal, implementar após S2)
- IIS/Reverse Proxy com **Windows Authentication** (Kerberos/NTLM) ativado
- Endpoint `/auth/whoami` retorna usuário AD normalizado (strip `DOMINIO\`, lowercase, busca case-insensitive no DB)
- Gateway emite JWT interno (sem exigir password_hash)
- Benefício: login transparente dentro da rede corporativa

**Entregáveis (Backend)**

- Migração Alembic: adicionar colunas a `users` + tabelas `auth_tokens` + `user_sessions`.
- Endpoints de Auth (a criar em S2: `backend/app/api/v1/endpoints/auth.py`):
  - `POST /auth/password/set/init` (envia link 1x, TTL 10 min)
  - `POST /auth/password/set/confirm` (recebe token + password, valida hash do token no DB)
  - `POST /auth/login` (valida email + password, checa lockout, gera JWT + refresh)
  - `POST /auth/refresh` (revalida refresh token, emite novo access JWT)
  - `POST /auth/logout` (marca refresh token como revoked)
  - `POST /auth/password/reset/init` (envia link 1x, TTL 30 min)
  - `POST /auth/password/reset/confirm` (recebe token + password)
  - `GET /auth/me` (retorna user autenticado, requer access JWT válido)
- **Segurança de senha** (usar `passlib[bcrypt]`):
  - Hash: bcrypt (min. custo 12)
  - Senhas nunca em logs, tokens ou responses
- **Tokens 1x** (para setup/reset):
  - Armazenados como `token_hash` (SHA256) no DB
  - Validação: calcular hash do token recebido e comparar
  - Campos: `expires_at`, `created_at`, `used_at` (marca quando consumido)
  - Expiração: 10 min (setup), 30 min (reset)
- **JWT interno** (HS256):
  - Access JWT: TTL **30 min** (curto)
  - Refresh token: HttpOnly cookie, TTL **14 dias**, rotacionável
  - Payload mínimo: `sub` (user_id), `email`, `role_global`, `iat`, `exp`
- **Validação de lockout** em middleware:
  - Bloqueia login se `locked_until > now()` → HTTP 429
  - Incrementa `failed_login_attempts` a cada falha
  - Reset após 15 min ou manual por admin
- **Auditoria** (audit_log com ator=user_id):
  - `LOGIN_ATTEMPT_SUCCESS` (com ip)
  - `LOGIN_ATTEMPT_FAILED` (com ip, motivo: invalid_password | user_not_found | locked)
  - `LOGIN_LOCKED` (depois de 5 falhas)
  - `PASSWORD_SET` (primeiro acesso)
  - `PASSWORD_RESET` (esqueci senha)
  - `LOGOUT` (revogação de refresh)

**RBAC global (sem carteiras por empresa)**

- **Visibilidade**: todos enxergam todos os certificados do `org_id` (sem segregação por empresa).
- **Perfis**:
  - **DEV** (você): acesso total (todas as abas: Certificados, Jobs, Dispositivos, Auditoria).
    - Pode gerenciar usuários e flags (`auto_approve_install_jobs`)
    - Pode aprovar/executar jobs
    - Pode authorizar/bloquear devices
  - **ADMIN** (ex.: Maria, 4 usuários): acesso às abas Certificados, Jobs e Dispositivos.
    - Pode aprovar/executar jobs
    - Pode gerenciar devices (autorizar/bloquear)
    - Sem acesso à aba Auditoria
    - Sem gerenciar usuários
  - **VIEW** (demais usuários): acesso apenas à aba Certificados.
    - Pode ver todos certificados do org
    - Pode solicitar jobs (cria em REQUESTED ou PENDING, vide regra abaixo)
    - Sem acesso às abas Jobs, Dispositivos, Auditoria
    - Sem gerenciar nada

- **Auto-aprovação** (`auto_approve_install_jobs` flag por usuário):
  - DEV/ADMIN: sempre aprovam (job nasce em PENDING)
  - VIEW com `auto_approve_install_jobs=false` (padrão): job nasce em REQUESTED, precisa de ADMIN/DEV aprovar
  - VIEW com `auto_approve_install_jobs=true`: job nasce em PENDING (auto-aprovado)

- **Exemplos HTTP (200 vs 403)**:
  ```bash
  # VIEW tentando listar jobs (sem acesso) → 403
  curl -H "Authorization: Bearer $JWT_VIEW" \
    "http://localhost:8000/api/v1/install-jobs"
  # Resposta: {"detail": "Forbidden"}
  
  # ADMIN listando jobs (com acesso) → 200
  curl -H "Authorization: Bearer $JWT_ADMIN" \
    "http://localhost:8000/api/v1/install-jobs"
  # Resposta: [{"id": "...", "status": "PENDING", ...}]
  
  # VIEW tentando gerenciar usuários → 403
  curl -X POST -H "Authorization: Bearer $JWT_VIEW" \
    -H "Content-Type: application/json" \
    -d '{"email": "new@netocontabilidade.com.br", "role": "ADMIN"}' \
    "http://localhost:8000/api/v1/admin/users"
  # Resposta: {"detail": "Forbidden"}
  
  # DEV gerenciando usuários (com acesso) → 201
  curl -X POST -H "Authorization: Bearer $JWT_DEV" \
    -H "Content-Type: application/json" \
    -d '{"email": "new@netocontabilidade.com.br", "role": "ADMIN"}' \
    "http://localhost:8000/api/v1/admin/users"
  # Resposta: {"id": "...", "email": "...", "role_global": "ADMIN"}
  ```

**Front (protótipo em dev)**

- Tela de login: email + senha (com loader de submissão).
- Tela de "Primeira vez": modal para definir senha (a partir do link enviado por admin).
- Layout base (Shell + Tabs + KPI strip) com dados mock.
- Hooks: `useAuth()`, `useCertificados()`, `useDevices()`, `useJobs()`, `useAudit()`.

**Variáveis de ambiente (S2)**

Adicionar em `.env` (backend root):

```env
# Auth JWT
JWT_SECRET=<GERADO_VIA_SECRETS>
ACCESS_TOKEN_TTL_MIN=30
REFRESH_TTL_DAYS=14
SET_PASSWORD_TOKEN_TTL_MIN=10
RESET_PASSWORD_TOKEN_TTL_MIN=30

# Segurança de Senha
BCRYPT_COST=12
LOCKOUT_MAX_ATTEMPTS=5
LOCKOUT_MINUTES=15

# Cookies (refresh token)
COOKIE_SECURE=true
COOKIE_SAMESITE=Strict
COOKIE_HTTPONLY=true
```

Gerar JWT_SECRET seguro:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Validações (S2)**

**1) Verificar Alembic e colunas:**
```bash
cd backend && alembic upgrade head

psql "$DATABASE_URL" -c \
  "SELECT column_name, data_type FROM information_schema.columns \
   WHERE table_name='users' AND column_name IN \
   ('password_hash', 'password_set_at', 'failed_login_attempts', 'locked_until') \
   ORDER BY column_name;"

psql "$DATABASE_URL" -c \
  "SELECT tablename FROM pg_tables \
   WHERE schemaname='public' AND tablename IN ('auth_tokens', 'user_sessions');"
```

**2) Criar primeiro user (bootstrap):**

Via SQL (comando psql):
```bash
psql "$DATABASE_URL" -c \
  "INSERT INTO users (id, org_id, email, nome, ad_username, role_global, is_active, password_hash, failed_login_attempts, created_at) \
   VALUES (gen_random_uuid(), 1, 'maria@netocontabilidade.com.br', 'Maria', 'maria.clara', 'ADMIN', true, NULL, 0, NOW());"
```

Ou via POST /api/v1/admin/users (requer user DEV/ADMIN já no DB):
```bash
curl -X POST "http://localhost:8000/api/v1/admin/users" \
  -H "Authorization: Bearer <JWT_ADMIN>" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "maria@netocontabilidade.com.br",
    "nome": "Maria Clara",
    "role_global": "ADMIN"
  }'

# Resposta: {"id": "<USER_ID>", "email": "maria@...", "setup_token": "<TOKEN_1X>"}
```

**3) Setup de senha (link 1x, TTL 10 min):**
```bash
SETUP_TOKEN="<TOKEN_RETORNADO_ACIMA>"

curl -X POST "http://localhost:8000/auth/password/set/confirm" \
  -H "Content-Type: application/json" \
  -d "{\"token\": \"${SETUP_TOKEN}\", \"password\": \"SenhaForte123!\"}"

# Resposta esperada: 200 {"message": "Senha configurada com sucesso"}
```

Verificar auditoria:
```bash
psql "$DATABASE_URL" -c \
  "SELECT action, actor_user_id, timestamp FROM audit_log \
   WHERE action='PASSWORD_SET' ORDER BY timestamp DESC LIMIT 1;"
```

**4) Login (email + password):**
```bash
LOGIN_RESPONSE=$(curl -s -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "maria@netocontabilidade.com.br",
    "password": "SenhaForte123!"
  }')

ACCESS_JWT=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token')
REFRESH_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.refresh_token')

echo "Access JWT: $ACCESS_JWT"
echo "Refresh Token: $REFRESH_TOKEN"

# Verificar payload do JWT
echo "$ACCESS_JWT" | jq -R 'split(".")[[1]] | @base64d | fromjson'
# Deve conter: sub, email, role_global, iat, exp
```

Verificar auditoria:
```bash
psql "$DATABASE_URL" -c \
  "SELECT action, meta_json, timestamp FROM audit_log \
   WHERE action='LOGIN_ATTEMPT_SUCCESS' ORDER BY timestamp DESC LIMIT 1;"
```

**5) GET /auth/me (autenticado):**
```bash
curl -H "Authorization: Bearer ${ACCESS_JWT}" \
  "http://localhost:8000/auth/me"

# Esperado: 200 + user data
# Sem JWT: 401

curl "http://localhost:8000/auth/me"
# Esperado: 401 Unauthorized
```

**6) Refresh token:**
```bash
curl -s -X POST "http://localhost:8000/auth/refresh" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\": \"${REFRESH_TOKEN}\"}" | jq '.access_token'

# Esperado: novo access_token (diferente do anterior)
```

**7) Logout (revoga refresh):**
```bash
curl -X POST "http://localhost:8000/auth/logout" \
  -H "Authorization: Bearer ${ACCESS_JWT}"

# Esperado: 200 {"message": "Logout realizado"}

# Tentar usar refresh revogado:
curl -X POST "http://localhost:8000/auth/refresh" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\": \"${REFRESH_TOKEN}\"}"

# Esperado: 401 {"detail": "Refresh token revoked"}
```

**8) Lockout (5 tentativas + 15 min bloqueio):**
```bash
for i in {1..5}; do
  curl -X POST "http://localhost:8000/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"email": "maria@netocontabilidade.com.br", "password": "ERRADA"}' \
    2>/dev/null | jq '.detail // "falha"'
  sleep 1
done

# 6ª tentativa:
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "maria@netocontabilidade.com.br", "password": "ERRADA"}'

# Esperado: HTTP 429 {"detail": "Too many login attempts. Try again in 15 minutes."}

# Verificar lockout no DB:
psql "$DATABASE_URL" -c \
  "SELECT email, failed_login_attempts, locked_until, EXTRACT(EPOCH FROM (locked_until - NOW())) as segundos_restantes \
   FROM users WHERE email='maria@netocontabilidade.com.br';"

# Deve mostrar: failed_login_attempts >= 5, locked_until = NOW() + 15 min

# Auditoria:
psql "$DATABASE_URL" -c \
  "SELECT action, COUNT(*) FROM audit_log \
   WHERE action IN ('LOGIN_ATTEMPT_FAILED', 'LOGIN_LOCKED') \
   AND timestamp > NOW() - interval '5 minutes' \
   GROUP BY action;"

# Desbloqueio manual (admin):
psql "$DATABASE_URL" -c \
  "UPDATE users SET failed_login_attempts=0, locked_until=NULL \
   WHERE email='maria@netocontabilidade.com.br';"

# Login funciona novamente:
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "maria@netocontabilidade.com.br", "password": "SenhaForte123!"}' | jq '.access_token'
```

**9) Reset de senha (TTL 30 min):**
```bash
curl -X POST "http://localhost:8000/auth/password/reset/init" \
  -H "Content-Type: application/json" \
  -d '{"email": "maria@netocontabilidade.com.br"}'

# Resposta: 200 {"message": "Link enviado para o e-mail"}
# (Em dev, você recebe o token no response ou logs)

RESET_TOKEN="<TOKEN_RESET>"

curl -X POST "http://localhost:8000/auth/password/reset/confirm" \
  -H "Content-Type: application/json" \
  -d "{\"token\": \"${RESET_TOKEN}\", \"password\": \"NovaSenha456!\"}"

# Esperado: 200 {"message": "Senha atualizada"}

# Auditoria:
psql "$DATABASE_URL" -c \
  "SELECT action FROM audit_log WHERE action='PASSWORD_RESET' ORDER BY timestamp DESC LIMIT 1;"
```

**10) RBAC (200 vs 403):**

Criar segundo user VIEW:
```bash
psql "$DATABASE_URL" -c \
  "INSERT INTO users (id, org_id, email, nome, ad_username, role_global, is_active, password_hash, failed_login_attempts, created_at) \
   VALUES (gen_random_uuid(), 1, 'view@netocontabilidade.com.br', 'View User', 'view.user', 'VIEW', true, NULL, 0, NOW());"

# Setup senha dele (repita fluxo acima)
```

VIEW tentando listar jobs (sem permissão) → 403:
```bash
curl -H "Authorization: Bearer ${JWT_VIEW}" \
  "http://localhost:8000/api/v1/install-jobs"

# Esperado: 403 {"detail": "Forbidden"}
```

ADMIN listando jobs (com permissão) → 200:
```bash
curl -H "Authorization: Bearer ${JWT_ADMIN}" \
  "http://localhost:8000/api/v1/install-jobs"

# Esperado: 200 [{"id": "...", "status": "PENDING", ...}]
```

**Rollback (S2)**

Para desfazer S2 em ambiente dev:

```bash
# 1) Identificar commit de S2
cd backend
git log --oneline --all | head -20

# 2) Reverter commit (cria novo commit de reversão, preserva histórico)
git revert <COMMIT_S2_SHA>
# Ou reverter múltiplos commits:
git revert <OLDEST_S2>..<NEWEST_S2>

# 3) Desfazer migrations
alembic downgrade -1

# 4) Limpar sessions/tokens para invalidar JWTs
psql "$DATABASE_URL" -c "TRUNCATE TABLE user_sessions, auth_tokens CASCADE;"

# 5) (Opcional) Remover users de teste
psql "$DATABASE_URL" -c "DELETE FROM users WHERE email IN ('maria@netocontabilidade.com.br', 'view@netocontabilidade.com.br');"
```

**Checklist de Aceite (S2)**

- [ ] Migração Alembic aplicada: colunas em `users` + tabelas `auth_tokens` + `user_sessions`.
- [ ] Variáveis de ambiente (.env) configuradas com JWT_SECRET gerado.
- [ ] User criado via SQL ou POST /api/v1/admin/users.
- [ ] Setup de senha: curl com SETUP_TOKEN funciona, password_hash preenchido no DB.
- [ ] Login: email + password retorna access_token + refresh_token.
- [ ] GET /auth/me com JWT válido retorna dados corretos.
- [ ] Refresh token renova JWT com sucesso.
- [ ] Logout revoga refresh_token (próximo refresh falha com 401).
- [ ] Lockout funciona: 5 tentativas → HTTP 429, locked_until marcado.
- [ ] Reset de senha: link 1x (30 min) funciona, nova password_hash preenchida.
- [ ] RBAC 200/403: VIEW → 403 em /api/v1/admin/users, ADMIN → 200.
- [ ] Auditoria registra: PASSWORD_SET, LOGIN_ATTEMPT_SUCCESS, LOGIN_LOCKED, PASSWORD_RESET.
- [ ] UI: telas de login, setup, reset renderizam e submetem requisições corretamente.
- [ ] Rollback: git revert + alembic downgrade -1 restauram estado pré-S2.

---

## S3 — API de Jobs (criar/acompanhar) + wiring do protótipo

**Objetivo**: portal cria job e acompanha status, usando as telas do protótipo.

 **Entregáveis (Backend)**
 
 - `POST /certificados/{id}/install` cria job para device alvo.
 - `GET /install-jobs` lista status.
 - Auditoria: INSTALL_REQUESTED.
- Aprovação:
  - Se `auto_approve_install_jobs=true` (ou perfil ADMIN/DEV), job nasce em `PENDING` (pronto pro agent).
  - Se `auto_approve_install_jobs=false` (VIEW padrão), job nasce em `REQUESTED` e precisa de aprovação.
  - Endpoints novos (ADMIN/DEV):
    - `POST /install-jobs/{job_id}/approve` -> muda `REQUESTED` -> `PENDING`
    - `POST /install-jobs/{job_id}/deny` -> muda `REQUESTED` -> `CANCELED` (ou `DENIED`)
  - Auditoria adicional: INSTALL_APPROVED / INSTALL_DENIED.

**Entregáveis (Front — protótipo)**

 - Aba **Certificados**
   - Botão “Instalar” abre o modal.
   - Modal lista devices autorizados (e marca bloqueados).
   - CTA “Criar job” chama `POST /certificados/{id}/install`.
   - Toast de sucesso/erro (job criado / device bloqueado).
- VIEW não precisa ver a aba Jobs:
  - Se job ficou `REQUESTED`, mostrar mensagem "Pedido enviado para aprovação".
  - Opcional: mostrar "Últimos pedidos" dentro do modal/tela de Certificados.
 - Aba **Jobs**
   - Carrega `GET /install-jobs?mine=true` e exibe tabela com status.
  - Polling leve (ex.: 5–10s) só enquanto existir `PENDING/IN_PROGRESS`.

**Aceite**

- Criar job pelo modal e ver status PENDING na aba Jobs.

---

## S4 — Agent MVP (registro + polling + import)


**Objetivo**: rodar o agent e instalar 1 certificado com segurança básica.

**Entregáveis**

- App tray com auto-start.
- Register + heartbeat.
- Polling + claim.
- Import no CurrentUser e report DONE.
- Local store de thumbprints instalados (DPAPI).

**Aceite**

- Portal cria job → agent instala → status vira DONE.

---

## S5 — Regra das 18h (limpeza garantida)

**Objetivo**: remover automaticamente às 18h tudo que o agent instalou como temporário.

**Entregáveis**

- Scheduled Task diária 18:00.
- Comando `--cleanup`.
- Auditoria: CERT\_REMOVED\_18H.

**Aceite**

- Instala 10:00 → 18:00 remove.
- Certificados pré-existentes não são removidos.

---

## S6 — Hardening (segurança de payload + device binding)

**Objetivo**: impedir que alguém “use o navegador” para baixar PFX/senha.

**Entregáveis**

- Payload somente para agent (client credential do device).
- Token one-time + expiração curta.
- (Opcional forte) criptografia por `public_key` do device.
- Rate limit e bloqueio por device não autorizado.

**Aceite**

- Requisição de payload sem credencial do agent falha.

---

## S7 — UX do Portal + Operação (finalizar telas do protótipo)

**Objetivo**: transformar o protótipo em produto operacional: fácil pro time e auditável para você/TI.

**Entregáveis (Front)**

- **Certificados**
  - Busca/filtros/ordenação (como no protótipo).
  - Cards consistentes com CNPJ/CPF mascarado, badges e datas.
  - Tela “Detalhes” opcional (serial, SHA1, issuer, subject, vínculo empresa, último uso).
- **Jobs**
  - Filtros por status e por device.
  - Atalho “Repetir instalação” (cria novo job) e “Cancelar job” (se PENDING).
- **Dispositivos**
  - Aprovar/bloquear device (perfil admin).
  - Exibir last seen e versão do agent com destaque para desatualizados.
- **Auditoria**
  - Filtros por usuário, empresa, ação e período.

**Entregáveis (Backend/Operação)**

- Endpoints para listagem/admin de devices e auditoria.
- Alertas básicos (ex.: tentativa em device bloqueado, agent desatualizado, job falhando repetidamente).

**Aceite**

- Maria consegue ver “quem instalou qual certificado em qual máquina e quando” e operar sem acessar diretório.

---

## S8 — Piloto e rollout

**Objetivo**: colocar em 2 máquinas, depois expandir.

**Entregáveis**

- Checklist de instalação do agent.
- Política do diretório e backups.
- Treinamento rápido do time (1 página).

**Aceite**

- 2 usuários operando por 1 semana sem fricção.

---

## Evoluções futuras (quando o projeto provar valor)

- Rodar API no servidor (IIS/Reverse proxy), DNS interno e TLS via CA.
- Integração com AD para preencher e-mail/nome automaticamente.
- Janela de exceção (ex.: “prorrogar até 20h” mediante aprovação).
- Modo “uso server-side” (Opção 1) para rotinas que não exigem instalação local.

---

## Checklist de segurança (resumo)

- [ ] Diretório de PFX com ACL mínima (já ok).
- [ ] Watcher/ingest rodando com conta de serviço.
- [ ] **Browser nunca recebe PFX/senha** (somente o Agent).
- [ ] Senha **não** armazenada em texto puro (secret store / criptografia).
- [ ] Jobs: token one-time + expiração curta + rate limit.
- [ ] Device binding: device registrado e is_allowed.
- [ ] Auditoria: INSTALL_REQUESTED / INSTALL_APPROVED / INSTALL_DENIED / CLAIM / DONE / FAILED / REMOVED_18H.
- [ ] Limpeza 18h garantida (Scheduled Task + fallback no startup).
- [ ] TLS interno (mesmo self-signed) com certificado confiável nas máquinas.
- [ ] Backup do DB + logs + diretório de certificados.

---

## Anexo — Convenção de nomes .pfx (compatibilidade)

Padrão atual: `nome_CPF/CNPJ Senha [senha].pfx`

- O ingest continua deduzindo senha do nome.
- No médio prazo, recomendação: parar de usar senha no nome e migrar para “secret store” (sem quebrar o portal).
