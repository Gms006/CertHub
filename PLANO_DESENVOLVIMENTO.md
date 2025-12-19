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
- NOVO:
  - `role_global` (DEV | ADMIN | VIEW)
  - `auto_approve_install_jobs` (bool, default false)

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

### Ajustes na tabela `certificados`

- Ideal: **não** persistir `senha` em texto puro.
- Sugestão: adicionar campos:
  - `secret_ref` (ponteiro para vault/DPAPI)
  - `password_encrypted` (se ficar no DB, sempre criptografado com chave fora do DB)

---

## Endpoints (contrato sugerido)

### Auth

- `GET /auth/whoami` → (via Windows Auth) retorna `ad_username`, `email` (se disponível)
- `POST /auth/jwt` → troca “whoami” por JWT interno

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

**Caminho A (intranet/ideal)**

- Gateway IIS com Windows Auth → emite JWT.

**Caminho B (rápido)**

- Magic link por e-mail.

**Entregáveis**

- JWT interno.
- RBAC: usuário enxerga todos os certificados do `org_id` (sem carteiras).
- Perfis (globais):
  - DEV (você): acesso total (todas as abas e ações).
  - ADMIN (4 usuários): acesso às abas Certificados, Jobs e Dispositivos.
  - VIEW (demais): acesso apenas à aba Certificados (pode solicitar instalação).
- Auto-aprovar: configuração habilitável por usuário (por exemplo: `auto_approve_install_jobs=true/false`).
  - DEV e ADMIN: sempre podem aprovar / executar fluxo completo.
  - VIEW: por padrão NÃO auto-aprova; quando habilitado, pode auto-aprovar seus próprios pedidos.
- **Front (protótipo em dev)**
  - Subir o layout base do protótipo (Shell + Tabs + KPI strip) com dados mock.
  - Definir o contrato dos hooks: `useAuth()`, `useCertificados()`, `useDevices()`, `useJobs()`, `useAudit()`.

**Aceite**

- Usuário loga e vê todos os certificados do org (sem carteira).
- UI do protótipo abre e renderiza “Certificados/Jobs/Dispositivos/Auditoria” (ainda que com mocks).

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

