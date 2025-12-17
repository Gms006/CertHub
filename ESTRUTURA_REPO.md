# Esqueleto do repo (monorepo)

```txt
certhub/
├─ backend/
│  ├─ app/
│  │  ├─ api/
│  │  │  └─ v1/
│  │  │     ├─ api.py
│  │  │     ├─ endpoints/
│  │  │     │  ├─ certificados.py
│  │  │     │  ├─ agent.py
│  │  │     │  ├─ install_jobs.py
│  │  │     │  └─ admin.py
│  │  ├─ core/
│  │  │  ├─ config.py
│  │  │  ├─ security.py
│  │  │  └─ audit.py
│  │  ├─ db/
│  │  │  ├─ base.py
│  │  │  ├─ session.py
│  │  │  └─ migrations_notes.md
│  │  ├─ models/
│  │  │  ├─ base.py
│  │  │  ├─ user.py
│  │  │  ├─ device.py
│  │  │  ├─ permissions.py
│  │  │  ├─ cert_install_job.py
│  │  │  └─ audit_log.py
│  │  ├─ schemas/
│  │  │  ├─ user.py
│  │  │  ├─ device.py
│  │  │  ├─ install_job.py
│  │  │  └─ audit.py
│  │  ├─ services/
│  │  │  ├─ certificados_catalogo.py
│  │  │  ├─ jobs_service.py
│  │  │  └─ audit_service.py
│  │  ├─ worker/
│  │  │  ├─ rq_worker.py
│  │  │  └─ watchers.py
│  │  └─ main.py
│  ├─ alembic/
│  │  ├─ env.py
│  │  ├─ script.py.mako
│  │  └─ versions/
│  ├─ tests/
│  ├─ alembic.ini
│  └─ Dockerfile
│
├─ frontend/
│  ├─ src/
│  │  ├─ app/
│  │  ├─ components/
│  │  ├─ pages/
│  │  ├─ hooks/
│  │  ├─ lib/
│  │  └─ main.tsx
│  ├─ index.html
│  ├─ package.json
│  ├─ vite.config.ts
│  └─ README.md
│
├─ agent/
│  ├─ CertHub.Agent/
│  │  ├─ CertHub.Agent.csproj
│  │  ├─ Program.cs
│  │  ├─ Services/
│  │  │  ├─ ApiClient.cs
│  │  │  ├─ JobRunner.cs
│  │  │  └─ CleanupScheduler.cs
│  │  └─ Storage/
│  │     └─ ThumbprintStore.cs
│  └─ README.md
│
├─ infra/
│  └─ docker-compose.yml
│
├─ .env.example
├─ .gitignore
├─ requirements.txt
└─ README.md
```
