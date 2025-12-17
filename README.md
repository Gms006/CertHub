# CertHub — Portal de Certificados com Agent

Objetivo: substituir o diretório público de `.pfx` por um fluxo controlado via **Portal (React) + API + Agent Windows**, com:
- instalação no **CurrentUser** sem o usuário ter acesso ao arquivo nem à senha
- controle de permissões (usuário ↔ empresas)
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

## Segurança (MVP)

* payload de instalação entregue somente ao Agent (evolui no S6: token one-time + expiração + device binding)
* auditoria: INSTALL_REQUESTED / CLAIM / DONE / FAILED / REMOVED_18H

## Stages

* S1: Base de dados + auditoria (tabelas users/devices/jobs/audit + seeds/rotas admin + middleware de auditoria)
* S2: Auth piloto + RBAC + skeleton do front (protótipo)
* S3+: Jobs + Agent MVP + limpeza às 18h + hardening
> As partes de S1/S2/S3/S4/S5/S6 estão todas descritas no plano (incluindo tabelas/endpoints e a política das 18h).

