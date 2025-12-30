# Plano — Portal de Certificados com Agent (CertHub)

## Objetivo

Substituir o diretório público de arquivos **.pfx** por um fluxo controlado via **Portal (React) + API** e um **Agent Windows** em cada máquina, permitindo:

- Instalação do certificado no **CurrentUser** sem o usuário ter acesso direto ao arquivo nem à senha.
- Controle de acesso via **RBAC global** + flags por usuário (ex.: `auto_approve_install_jobs`).
- **Auditoria** completa de uso/instalação.
- **Desabilitar/remover automaticamente às 18h** todos os certificados “temporários” instalados pelo Agent.

> Observação de segurança (realista): se o certificado precisa existir na máquina para uso em assinadores/portais/SPED, sempre existe risco residual de extração por quem tem alto privilégio local. O objetivo aqui é **reduzir drasticamente a exposição**, centralizar o acesso e **auditar** tudo.

---

## Contexto atual (estado real do repositório)

O backend já possui o catálogo e o núcleo de RBAC/Jobs:

- `app/services/certificate_ingest.py`: varre a raiz, extrai metadados (subject/issuer/serial/validade/sha1), deduz senha pelo nome, faz upsert/dedup por serial/sha1 e remove registros ausentes.
- Endpoint DEV para ingestão de filesystem: `POST /api/v1/admin/certificates/ingest-from-fs` (dry-run, limit, prune, dedupe).
- Certificados/Jobs/Devices/Usuários já com CRUD mínimo e auditoria.
- Autenticação email+senha com tokens 1x, lockout e refresh via cookie HttpOnly.
- **Não há** worker Redis/RQ nem watcher em execução no repo atual.

**O que muda:** o catálogo já existe; falta o **módulo de distribuição controlada + agent** e o pipeline real do Agent.

---

## Arquitetura alvo

### Componentes

1. **Backend/API (máquina da Maria, inicialmente)**

- Mantém ingest (watcher pendente no repo atual).
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

> Status no repo: **implementado** (tray app WinForms + endpoints `/agent/*` já disponíveis).

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
- `POST /api/v1/auth/password/set/init` → recebe `email`, retorna link 1x (token em URL, TTL 1h)
- `POST /api/v1/auth/password/set/confirm` → recebe `token` + `new_password`, seta `password_hash` + `password_set_at`

**Login normal:**
- `POST /api/v1/auth/login` → recebe `email` + `password`, valida lockout, gera JWT + refresh token
  - Resposta: `{ "access_token": "...", "user": {...} }` (+ cookie HttpOnly)
  - Status 429 (Too Many Requests) se `failed_login_attempts >= 5` antes de `locked_until`
- `POST /api/v1/auth/refresh` → usa cookie HttpOnly (ou body em dev), emite novo JWT (sem renovar refresh se ainda válido)
- `POST /api/v1/auth/logout` → revoga refresh token (marca `revoked_at` em user_sessions)

**Password reset:**
- `POST /api/v1/auth/password/reset/init` → recebe `email`, envia link 1x (token em URL, TTL 30min)
- `POST /api/v1/auth/password/reset/confirm` → recebe `token` + `new_password`, seta nova `password_hash`

**Info:**
- `GET /api/v1/auth/me` → retorna dados do user autenticado (requer JWT válido)

### Portal

- `GET /api/v1/certificados` (**implementado**)
- `POST /api/v1/certificados/{id}/install` (**implementado**) → cria `cert_install_job`
- `GET /api/v1/install-jobs` (**implementado**, com filtros `mine/my-device`)

### Agent

- `POST /api/v1/agent/register` → registra device (primeira execução)
- `POST /api/v1/agent/heartbeat` → last\_seen + versão
- `GET /api/v1/agent/jobs?device_id=...` → lista jobs pendentes para o device
- `POST /api/v1/agent/jobs/{job_id}/claim` → marca IN\_PROGRESS (one-time)
- `GET /api/v1/agent/jobs/{job_id}/payload` → entrega pacote (pfx + senha) somente para agent
- `POST /api/v1/agent/jobs/{job_id}/result` → DONE/FAILED + thumbprint

> Status: **pendente** no backend.

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
- Helper `log_audit` aplicado nos endpoints críticos (registro manual por ação).

**Status**: ✅ **Concluído**

**Evidências (S1)**

- [x] Migrações aplicadas (`alembic upgrade head` OK).
- [x] Ingest-from-fs funcionando: **323 total / 320 updated / 3 failed (esperados)**.
- [x] `audit_log` registrando: `CERT_INGEST_FROM_FS`, `INSTALL_REQUESTED`, `INSTALL_APPROVED`.
- [x] Endpoint `/api/v1/audit` disponível para consulta (filtros por ação/ator).
- [x] Smoke tests de install job:
  - VIEW com `auto_approve_install_jobs=false` → `REQUESTED`.
  - VIEW com `auto_approve_install_jobs=true` → `PENDING` + `approved_at`.
  - ADMIN/DEV → `PENDING` + `approved_at`.
- [x] Endpoints admin: criação/edição de usuários, devices e vínculo user-device.

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
     "http://localhost:8010/api/v1/certificados"
   ```
4. Criar install job (VIEW, sem auto-approve → REQUESTED):
   ```bash
   curl -X POST "http://localhost:8010/api/v1/certificados/<CERT_ID>/install" \
     -H "Content-Type: application/json" \
     -H "X-User-Id: <UUID_VIEW>" -H "X-Org-Id: 1" \
     -d '{"device_id": "<DEVICE_ID>"}'
   ```
5. Criar install job (VIEW com auto-approve ou ADMIN/DEV → PENDING + approved):
   ```bash
   curl -X POST "http://localhost:8010/api/v1/certificados/<CERT_ID>/install" \
     -H "Content-Type: application/json" \
     -H "X-User-Id: <UUID_ADMIN_OU_VIEW_AUTO>" -H "X-Org-Id: 1" \
     -d '{"device_id": "<DEVICE_ID>"}'
   ```- Aprovar job (ADMIN/DEV):
   ```bash
   curl -X POST "http://localhost:8010/api/v1/install-jobs/<JOB_ID>/approve" \
     -H "X-User-Id: <UUID_ADMIN>" -H "X-Org-Id: 1"
   ```
---

## S2 — Auth (piloto) + RBAC + Skeleton do Front (protótipo)

**Objetivo**: login no portal e RBAC global, já com a UI do protótipo rodando.

**Status**: ✅ **Concluído**

**Evidências (S2)**

- Endpoints `/api/v1/auth/*` alinhados (tokens 1x, lockout, refresh via cookie HttpOnly).
- RBAC global aplicado (VIEW 403 em `/api/v1/admin/users`, 200 em `/api/v1/certificados`).
- Auditoria registrada: `PASSWORD_SET`, `PASSWORD_RESET`, `LOGIN_SUCCESS`, `LOGIN_FAILED`, `LOGIN_LOCKED`, `LOGOUT`.

**Padrão S2: Email+Senha (usuários pré-criados)**

Não há auto-cadastro. Admin cria usuários no banco (is_active=true) e distribui link 1x para definir senha no primeiro acesso.

**Fluxos de autenticação:**

- **Novo usuário (primeiro acesso)**
  - Admin via POST `/api/v1/admin/users` (requer role DEV/ADMIN) cria user com `is_active=true`, `password_hash=NULL`
  - API retorna `setup_token` (1x, TTL 10 min) no response
  - Em DEV, `/api/v1/auth/password/set/init` retorna `token` no JSON; em PROD retorna apenas `{ ok: true }`
  - Admin envia link: `http://portal.netocms.local/auth/set-password?token=<SETUP_TOKEN>` (válido por **10 min**)
  - User acessa link e faz POST `/api/v1/auth/password/set/confirm` com `token` + `new_password`
  - Após isso: `password_hash` é preenchido (bcrypt), `password_set_at` marcado
  
- **Login normal** (sempre que voltar)
  - POST `/api/v1/auth/login` com `email` + `password`
  - Retorna: `{ "access_token": "...", "user": {...} }`
  - Access JWT: TTL **30 min** (curto)
  - Refresh token: **cookie HttpOnly**, TTL **14 dias**, rotacionável
  
- **Esqueci senha**
  - POST `/api/v1/auth/password/reset/init` com `email`
  - Em DEV, retorna `token` no JSON; em PROD retorna apenas `{ ok: true }`
  - Link: `http://portal.netocms.local/auth/reset-password?token=<TOKEN>` (válido por **30 min**)
  - POST `/api/v1/auth/password/reset/confirm` com `token` + `new_password`
  
- **Segurança de lockout**
  - 5ª tentativa inválida já retorna **HTTP 429** e marca `locked_until` (bloqueia por **15 min**)
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
- Endpoints de Auth (implementados em `backend/app/api/v1/endpoints/auth.py`):
  - `POST /api/v1/auth/password/set/init` (envia link 1x, TTL 10 min)
  - `POST /api/v1/auth/password/set/confirm` (recebe token + new_password, valida hash do token no DB)
  - `POST /api/v1/auth/login` (valida email + password, checa lockout, gera JWT + refresh)
  - `POST /api/v1/auth/refresh` (revalida refresh token, emite novo access JWT)
  - `POST /api/v1/auth/logout` (marca refresh token como revoked)
  - `POST /api/v1/auth/password/reset/init` (envia link 1x, TTL 30 min)
  - `POST /api/v1/auth/password/reset/confirm` (recebe token + new_password)
  - `GET /api/v1/auth/me` (retorna user autenticado, requer access JWT válido)
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
  - Refresh token: HttpOnly cookie, TTL **14 dias**, rotacionável (não exposto no body)
  - Payload mínimo: `sub` (user_id), `email`, `role_global`, `iat`, `exp`
- **Validação de lockout** em middleware:
  - Bloqueia login se `locked_until > now()` → HTTP 429
  - Incrementa `failed_login_attempts` a cada falha
  - Reset após 15 min ou manual por admin
- **Auditoria** (audit_log com ator=user_id):
  - `LOGIN_SUCCESS` (com ip)
  - `LOGIN_FAILED` (com ip, motivo: invalid_password | user_not_found | inactive)
  - `LOGIN_LOCKED` (após 5 falhas ou durante bloqueio)
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
    "http://localhost:8010/api/v1/install-jobs"
  # Resposta: {"detail": "Forbidden"}
  
  # ADMIN listando jobs (com acesso) → 200
  curl -H "Authorization: Bearer $JWT_ADMIN" \
    "http://localhost:8010/api/v1/install-jobs"
  # Resposta: [{"id": "...", "status": "PENDING", ...}]
  
  # VIEW tentando gerenciar usuários → 403
  curl -X POST -H "Authorization: Bearer $JWT_VIEW" \
    -H "Content-Type: application/json" \
    -d '{"email": "new@netocontabilidade.com.br", "role": "ADMIN"}' \
    "http://localhost:8010/api/v1/admin/users"
  # Resposta: {"detail": "Forbidden"}
  
  # DEV gerenciando usuários (com acesso) → 201
  curl -X POST -H "Authorization: Bearer $JWT_DEV" \
    -H "Content-Type: application/json" \
    -d '{"email": "new@netocontabilidade.com.br", "role": "ADMIN"}' \
    "http://localhost:8010/api/v1/admin/users"
  # Resposta: {"id": "...", "email": "...", "role_global": "ADMIN"}
  ```

**Front (protótipo em dev)**

- Tela de login: email + senha (com loader de submissão).
- Tela de "Primeira vez": modal para definir senha (a partir do link enviado por admin).
- Layout base (Shell + Tabs + KPI strip) consumindo dados reais via API.
- Hooks: `useAuth()` (com `apiFetch` integrado à API real).

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
curl -X POST "http://localhost:8010/api/v1/admin/users" \
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

curl -X POST "http://localhost:8010/api/v1/auth/password/set/confirm" \
  -H "Content-Type: application/json" \
  -d "{\"token\": \"${SETUP_TOKEN}\", \"new_password\": \"SenhaForte123!\"}"

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
LOGIN_RESPONSE=$(curl -s -c cookies.txt -X POST "http://localhost:8010/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "maria@netocontabilidade.com.br",
    "password": "SenhaForte123!"
  }')

ACCESS_JWT=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token')

echo "Access JWT: $ACCESS_JWT"

# Verificar payload do JWT
echo "$ACCESS_JWT" | jq -R 'split(".")[[1]] | @base64d | fromjson'
# Deve conter: sub, email, role_global, iat, exp
```

Verificar auditoria:
```bash
psql "$DATABASE_URL" -c \
  "SELECT action, meta_json, timestamp FROM audit_log \
   WHERE action='LOGIN_SUCCESS' ORDER BY timestamp DESC LIMIT 1;"
```

**5) GET /api/v1/auth/me (autenticado):**
```bash
curl -H "Authorization: Bearer ${ACCESS_JWT}" \
  "http://localhost:8010/api/v1/auth/me"

# Esperado: 200 + user data
# Sem JWT: 401

curl "http://localhost:8010/api/v1/auth/me"
# Esperado: 401 Unauthorized
```

**6) Refresh token:**
```bash
curl -s -X POST "http://localhost:8010/api/v1/auth/refresh" \
  -b cookies.txt | jq '.access_token'

# Esperado: novo access_token (diferente do anterior)
```

**7) Logout (revoga refresh):**
```bash
curl -X POST "http://localhost:8010/api/v1/auth/logout" \
  -H "Authorization: Bearer ${ACCESS_JWT}"

# Esperado: 200 {"message": "Logout realizado"}

# Tentar usar refresh revogado:
curl -X POST "http://localhost:8010/api/v1/auth/refresh" \
  -b cookies.txt

# Esperado: 401 {"detail": "Refresh token revoked"}
```

**8) Lockout (5 tentativas + 15 min bloqueio):**
```bash
for i in {1..5}; do
  curl -X POST "http://localhost:8010/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"email": "maria@netocontabilidade.com.br", "password": "ERRADA"}' \
    2>/dev/null | jq '.detail // "falha"'
  sleep 1
done

# 6ª tentativa:
curl -X POST "http://localhost:8010/api/v1/auth/login" \
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
   WHERE action IN ('LOGIN_FAILED', 'LOGIN_LOCKED') \
   AND timestamp > NOW() - interval '5 minutes' \
   GROUP BY action;"

# Desbloqueio manual (admin):
psql "$DATABASE_URL" -c \
  "UPDATE users SET failed_login_attempts=0, locked_until=NULL \
   WHERE email='maria@netocontabilidade.com.br';"

# Login funciona novamente:
curl -X POST "http://localhost:8010/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "maria@netocontabilidade.com.br", "password": "SenhaForte123!"}' | jq '.access_token'
```

**9) Reset de senha (TTL 30 min):**
```bash
curl -X POST "http://localhost:8010/api/v1/auth/password/reset/init" \
  -H "Content-Type: application/json" \
  -d '{"email": "maria@netocontabilidade.com.br"}'

# Resposta: 200 {"message": "Link enviado para o e-mail"}
# (Em dev, você recebe o token no response ou logs)

RESET_TOKEN="<TOKEN_RESET>"

curl -X POST "http://localhost:8010/api/v1/auth/password/reset/confirm" \
  -H "Content-Type: application/json" \
  -d "{\"token\": \"${RESET_TOKEN}\", \"new_password\": \"NovaSenha456!\"}"

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
  "http://localhost:8010/api/v1/install-jobs"

# Esperado: 403 {"detail": "Forbidden"}
```

ADMIN listando jobs (com permissão) → 200:
```bash
curl -H "Authorization: Bearer ${JWT_ADMIN}" \
  "http://localhost:8010/api/v1/install-jobs"

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
- [ ] Login: email + password retorna access_token (refresh via cookie HttpOnly).
- [ ] GET /api/v1/auth/me com JWT válido retorna dados corretos.
- [ ] Refresh token renova JWT com sucesso.
- [ ] Logout revoga refresh_token (próximo refresh falha com 401).
- [ ] Lockout funciona: 5 tentativas → HTTP 429, locked_until marcado.
- [ ] Reset de senha: link 1x (30 min) funciona, nova password_hash preenchida.
- [ ] RBAC 200/403: VIEW → 403 em /api/v1/admin/users, ADMIN → 200.
- [ ] Auditoria registra: PASSWORD_SET, LOGIN_SUCCESS, LOGIN_FAILED, LOGIN_LOCKED, PASSWORD_RESET.
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

**Status**: ✅ **Concluído**

**Evidências (S3)**

- API: `POST /certificados/{id}/install`, `GET /install-jobs`, `POST /install-jobs/{id}/approve|deny`.
- Front: modal “Instalar” cria job, aba Jobs lista/atualiza e permite aprovar/negar (ADMIN/DEV).

**Aceite**

- Criar job pelo modal e ver status PENDING/REQUESTED na aba Jobs.

---

## S4.1 — Watcher (PFX directory)

**Objetivo**: operacionalizar o watcher event-driven do diretório de `.pfx` com **o mesmo comportamento do watcher legado**.

**Status**: ✅ **Concluído**

**Comportamento obrigatório (paridade com o legado)**

- `watchdog` observer.
- **Debounce + rate limit** para evitar ingest duplicado.
- Monitorar **apenas a raiz** do diretório (ignorar subpastas).
- `created`/`modified` ⇒ enqueue **ingest por arquivo**.
- `deleted` ⇒ enqueue **delete por caminho**.
- `moved`:
  - Se **saiu da raiz**: enqueue delete.
  - Se **entrou na raiz**: enqueue ingest.
- **Dedup** por `job_id` determinístico baseado no path normalizado:
  - `job_id = sha1(path_lowercase_normalized)`.
- **RQ/Redis** para fila e worker compatível com Windows (`SimpleWorker` + `TimerDeathPenalty`).

**Entregáveis**

1. Redis no `docker-compose` (se ainda não existir).
2. Worker RQ (entrypoint).
3. Watcher (entrypoint).
4. Jobs: ingest por arquivo e delete por caminho.
5. Logs e variáveis de ambiente documentadas.

**Variáveis de ambiente (S4.1)**

- `ORG_ID`: org padrão para os jobs do watcher.
- `CERTIFICADOS_ROOT`: raiz a monitorar (apenas arquivos diretos).
- `WATCHER_DEBOUNCE_SECONDS`: janela de debounce (segundos).
- `WATCHER_MAX_EVENTS_PER_MINUTE`: limite de eventos por minuto.
- `REDIS_URL`: URL do Redis.
- `RQ_QUEUE_NAME`: nome da fila usada pelo watcher/worker.

**Logs (S4.1)**

- Watcher: evento recebido (`created/modified/deleted/moved`), path normalizado, ação enfileirada, `job_id`.
- Worker: job iniciado/finalizado, sucesso/erro, path alvo, `job_id`.
- Delete: `job_delete_started`, `job_delete_result` (strategy/rowcount/found_ids_count), `job_delete_finished`.
- Delete fallback: quando `source_path` não encontra, tenta `name == <stem>` e registra `job_delete_not_found` ou `job_delete_ambiguous`.
- Queue: `queue_deduped` para jobs ativos e `queue_reenqueue` quando um job finalizado é substituído.
- Rate limit: eventos descartados ou coalescidos.

**Checklist de aceite (S4.1)**

- [x] Subir infra (docker compose) com Redis disponível.
- [x] Rodar worker RQ.
- [x] Rodar watcher com `CERTIFICADOS_ROOT` apontando para a raiz monitorada.
- [x] Eventos `created/modified/deleted/moved` (entra/sai da raiz) geram logs e efeitos no DB.
- [x] Subpastas são ignoradas.

**Rollback (S4.1)**

1. Parar watcher e worker.
2. Remover o serviço Redis do `docker-compose` (se não utilizado).
3. Reverter commits relacionados ao S4.1.

**Critérios de aceite do S4.1**

- Watcher reproduz o comportamento legado para create/modify/delete/move.
- Jobs são deduplicados por `job_id` determinístico.
- Worker RQ processa ingest/delete sem depender de Linux-specific features.
- Logs deixam claro o fluxo evento → job → resultado.

**Como validar**

> Os comandos abaixo são **PowerShell** e assumem que o backend já está com dependências instaladas.

1) Subir a infra (Postgres + Redis):
```powershell
docker compose -f infra/docker-compose.yml up -d
```

2) Rodar o worker (em um terminal):
```powershell
Set-Location backend
python -m app.workers.rq_worker
```

3) Rodar o watcher (em outro terminal):
```powershell
Set-Location backend
$env:ORG_ID="1"
$env:CERTIFICADOS_ROOT="C:\certs"
$env:WATCHER_DEBOUNCE_SECONDS="2"
$env:WATCHER_MAX_EVENTS_PER_MINUTE="60"
$env:REDIS_URL="redis://localhost:6379/0"
$env:RQ_QUEUE_NAME="certs"
python -m app.watchers.pfx_directory
```

4) Verificar ingest e delete no DB (psql):
```powershell
# Após copiar um .pfx válido para a raiz monitorada:
# Copy-Item "C:\origem\teste.pfx" "C:\certs\teste.pfx"
psql "$env:DATABASE_URL" -c "select id, source_path from certificates where source_path = 'C:\\certs\\teste.pfx';"

# Após deletar o arquivo monitorado:
# Remove-Item "C:\certs\teste.pfx"
psql "$env:DATABASE_URL" -c "select id, source_path from certificates where source_path = 'C:\\certs\\teste.pfx';"
```

> Observação: se o `source_path` no DB estiver divergente (UNC vs drive), o delete faz fallback por `name == teste`.

**Job ID por ação (S4.1)**

- Ingest: `cert_ing__<org_id>__<sha1(path_lower_normalized)>`
- Delete: `cert_del__<org_id>__<sha1(path_lower_normalized)>`

**Inspeção rápida da fila (S4.1)**

```powershell
python - <<'PY'
from app.workers.queue import get_queue, get_redis
q = get_queue(get_redis())
print("queued", q.count)
print("job_ids", q.job_ids)
PY
```

---

## S4 — Agent MVP (registro + polling + import)


**Objetivo**: rodar o agent e instalar 1 certificado com segurança básica.

**Status**: ✅ **Concluído**

**Entregáveis**

- App tray com auto-start.
- Register + heartbeat.
- Polling + claim.
- Import no CurrentUser e report DONE.
- Local store de thumbprints instalados (DPAPI).

**Backend (API do agent)**

- `POST /api/v1/agent/auth` → device token → JWT role=DEVICE.
- `POST /api/v1/agent/heartbeat` → atualiza `last_seen_at`/`last_heartbeat_at`.
- `GET /api/v1/agent/jobs` → jobs PENDING/IN_PROGRESS do device.
- `POST /api/v1/agent/jobs/{job_id}/claim` → PENDING → IN_PROGRESS.
- `GET /api/v1/agent/jobs/{job_id}/payload` → retorna `pfx_base64` + `password`.
- `POST /api/v1/agent/jobs/{job_id}/result` → IN_PROGRESS → DONE/FAILED.

**Observação de senha**: o payload usa `certificate.source_path` e a senha é inferida do nome do arquivo (padrão `senha`).
Se não houver senha, a API retorna erro explícito.

**Aceite**

- Portal cria job → agent instala → status vira DONE.

**Evidências/validação reproduzível (S4)**

- Portal: criar request → job `PENDING` → agent faz claim → job `DONE`.
- Windows: validar no `certmgr.msc` em **Current User > Personal** (certificado presente).

**Checklist de aceite (S4)**

- [x] Agent abre no tray e persiste configuração.
- [x] Auto-start (HKCU Run) criado.
- [x] Heartbeat atualiza `last_heartbeat_at` no DB.
- [x] Polling encontra job PENDING.
- [x] Claim muda status para IN_PROGRESS e preenche `started_at/claimed_at`.
- [x] Payload baixa PFX + senha.
- [x] Certificado aparece no `certmgr.msc` (Current User > Personal).
- [x] Result marca DONE e grava thumbprint no DB.
- [x] `installed_thumbprints` (DPAPI) atualizado.

**Como validar (PowerShell)**

1) Provisionar device/token:
```powershell
$device = Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/admin/devices" `
  -Headers @{ Authorization = "Bearer <JWT_ADMIN>" } `
  -ContentType "application/json" `
  -Body '{"hostname":"PC-01","domain":"NETOCMS","os_version":"Windows 11","agent_version":"1.0.0"}'
$device.device_token
$device.id
```

Opcional: rotacionar token do device:
```powershell
$rotated = Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/admin/devices/$($device.id)/rotate-token" `
  -Headers @{ Authorization = "Bearer <JWT_ADMIN>" }
$rotated.device_token
```

2) Autenticar agent:
```powershell
$auth = Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/agent/auth" `
  -ContentType "application/json" `
  -Body (@{ device_id = $device.id; device_token = $device.device_token } | ConvertTo-Json)
$agentJwt = $auth.access_token
```

3) Heartbeat:
```powershell
Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/agent/heartbeat" `
  -Headers @{ Authorization = "Bearer $agentJwt" } `
  -ContentType "application/json" `
  -Body '{"agent_version":"1.0.0"}'
```

4) Jobs:
```powershell
Invoke-RestMethod "http://localhost:8010/api/v1/agent/jobs" `
  -Headers @{ Authorization = "Bearer $agentJwt" }
```

5) Claim + payload + result:
```powershell
Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/agent/jobs/<JOB_ID>/claim" `
  -Headers @{ Authorization = "Bearer $agentJwt" }

Invoke-RestMethod "http://localhost:8010/api/v1/agent/jobs/<JOB_ID>/payload" `
  -Headers @{ Authorization = "Bearer $agentJwt" }

Invoke-RestMethod -Method Post "http://localhost:8010/api/v1/agent/jobs/<JOB_ID>/result" `
  -Headers @{ Authorization = "Bearer $agentJwt" } `
  -ContentType "application/json" `
  -Body '{"status":"DONE","thumbprint":"<TP>"}'
```

---

## S5 — Regra das 18h (limpeza garantida)

**Objetivo**: remover automaticamente às 18h tudo que o agent instalou como temporário.

**Status**: ✅ Concluído

**Entregáveis**

- Scheduled Task diária 18:00 (ProgramData).
- Comando `--cleanup` (modo scheduled).
- Auditoria: CERT\_REMOVED\_18H.

**Aceite**

- Task “CertHub Cleanup 18h” existe e Task To Run aponta para `C:\ProgramData\CertHubAgent\publish\Certhub.Agent.exe`.
- `schtasks /Run` executa e o `agent.log` registra “Starting cleanup (Scheduled)”.
- DB registra `audit_log` com action `CERT_REMOVED_18H`.
- Certificados pré-existentes não são removidos.

**Validação (S5)**

```powershell
# Rodar cleanup manual (headless)
C:\ProgramData\CertHubAgent\publish\Certhub.Agent.exe --cleanup --mode manual

# Verificar Scheduled Task
schtasks /Query /TN "CertHub Cleanup 18h" /V /FO LIST
schtasks /Run /TN "CertHub Cleanup 18h"
```

```sql
select action, meta_json, timestamp
from audit_log
where action = 'CERT_REMOVED_18H'
order by timestamp desc
limit 5;
```

**Rollback (S5)**

```powershell
Unregister-ScheduledTask -TaskName "CertHub Cleanup 18h" -Confirm:$false
```

```bash
git revert <commit_sha>
```

---

## S6 — Hardening (segurança de payload + device binding)

**Objetivo**: impedir que alguém “use o navegador” para baixar PFX/senha.

**Status**: ✅ **Concluído**

**Entregáveis**

- Payload somente para agent (client credential do device).
- Token one-time + expiração curta (**TTL 120s**).
- Rate limit por device (auth **10/min**, payload **5/min**).
- Bloqueio por device não autorizado.
- (Opcional forte) criptografia por `public_key` do device **fora deste patch**.

**Aceite**

- Requisição de payload sem credencial do agent falha.
- Token payload é single-use, expira em 120s e é validado por device.
- /result é idempotente (replay retorna 409 com audit de duplicidade).
- Reaper de jobs presos em IN_PROGRESS funciona e registra JOB_REAPED.
- Audit logs registram PAYLOAD_DENIED e PAYLOAD_RATE_LIMITED com meta consistente.

**Validação (S6)**

```bash
# Backend
cd backend
alembic upgrade head
pytest
python -m pytest -q ./tests/test_agent_payload_hardening.py ./tests/test_agent_job_controls.py
```

```bash
# Reaper (ADMIN/DEV)
curl -X POST "http://localhost:8010/api/v1/admin/jobs/reap?threshold_minutes=60" \
  -H "Authorization: Bearer <JWT_ADMIN>"
```

```sql
-- Auditorias chave
select action, meta_json, timestamp
from audit_log
where action in ('PAYLOAD_DENIED', 'PAYLOAD_RATE_LIMITED', 'RESULT_DUPLICATE', 'JOB_REAPED')
order by timestamp desc
limit 20;
```

---

## S7 — UX do Portal + Operação (finalizar telas do protótipo)

**Objetivo**: transformar o protótipo em produto operacional: fácil pro time e auditável para você/TI.

**Status**: 🚧 **Em andamento (parcial)**

**Entregáveis (Front)**

- **Certificados**
  - [x] Busca/filtros/ordenação (como no protótipo).
  - [x] Cards consistentes com CNPJ/CPF mascarado, badges e datas.
  - [x] Tela “Detalhes” opcional (serial, SHA1, issuer, subject, vínculo empresa, último uso).
- **Jobs**
  - [x] Filtro por device (ADMIN/DEV).
  - [ ] Filtros por status.
  - [ ] Atalho “Repetir instalação” (cria novo job) e “Cancelar job” (se PENDING).
- **Dispositivos**
  - [x] Aprovar/bloquear device (perfil admin).
  - [x] Exibir last seen e versão do agent.
  - [ ] Destaque para agents desatualizados.
- **Auditoria**
  - [x] Filtro por ação/ator (texto).
  - [ ] Filtros por usuário, empresa e período.

**Entregáveis (Backend/Operação)**

- [x] Endpoints para listagem/admin de devices e auditoria.
- [ ] Alertas básicos (ex.: tentativa em device bloqueado, agent desatualizado, job falhando repetidamente).

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
- [x] Limpeza 18h garantida (Scheduled Task + fallback no startup).
- [ ] TLS interno (mesmo self-signed) com certificado confiável nas máquinas.
- [ ] Backup do DB + logs + diretório de certificados.

---

## Anexo — Convenção de nomes .pfx (compatibilidade)

Padrão atual: `nome_CPF/CNPJ Senha [senha].pfx`

- O ingest continua deduzindo senha do nome.
- No médio prazo, recomendação: parar de usar senha no nome e migrar para “secret store” (sem quebrar o portal).
