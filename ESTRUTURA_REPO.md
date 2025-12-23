# Esqueleto do repo (monorepo)

```txt
certhub/
├─ backend/
│  ├─ app/
│  │  ├─ __init__.py
│  │  ├─ api/
│  │  │  ├─ __init__.py
│  │  │  └─ v1/
│  │  │     ├─ __init__.py
│  │  │     ├─ api.py
│  │  │     └─ endpoints/
│  │  │        ├─ __init__.py
│  │  │        ├─ agent.py
│  │  │        ├─ admin.py
│  │  │        ├─ audit.py
│  │  │        ├─ auth.py
│  │  │        ├─ certificados.py
│  │  │        └─ install_jobs.py
│  │  ├─ core/
│  │  │  ├─ __init__.py
│  │  │  ├─ audit.py
│  │  │  ├─ config.py
│  │  │  └─ security.py
│  │  ├─ db/
│  │  │  ├─ __init__.py
│  │  │  ├─ base.py
│  │  │  └─ session.py
│  │  ├─ models/
│  │  │  ├─ __init__.py
│  │  │  ├─ audit_log.py
│  │  │  ├─ auth_token.py
│  │  │  ├─ cert_install_job.py
│  │  │  ├─ certificate.py
│  │  │  ├─ device.py
│  │  │  ├─ user.py
│  │  │  ├─ user_device.py
│  │  │  └─ user_session.py
│  │  ├─ schemas/
│  │  │  ├─ __init__.py
│  │  │  ├─ agent.py
│  │  │  ├─ audit.py
│  │  │  ├─ auth.py
│  │  │  ├─ cert_ingest.py
│  │  │  ├─ certificate.py
│  │  │  ├─ device.py
│  │  │  ├─ install_job.py
│  │  │  ├─ user.py
│  │  │  └─ user_device.py
│  │  ├─ services/
│  │  │  ├─ __init__.py
│  │  │  └─ certificate_ingest.py
│  │  ├─ watchers/
│  │  │  ├─ __init__.py
│  │  │  └─ pfx_directory.py
│  │  ├─ workers/
│  │  │  ├─ __init__.py
│  │  │  ├─ jobs_certificates.py
│  │  │  ├─ queue.py
│  │  │  └─ rq_worker.py
│  │  └─ main.py
│  ├─ alembic/
│  │  ├─ env.py
│  │  ├─ script.py.mako
│  │  └─ versions/
│  │     ├─ 0001_create_s1_tables.py
│  │     ├─ 0002_rbac_auto_approve_jobs.py
│  │     ├─ 0003_certificate_metadata.py
│  │     ├─ 0004_certificate_parse_status.py
│  │     ├─ 0005_user_updated_at.py
│  │     ├─ 0006_remove_user_emp_perm.py
│  │     ├─ 0007_auth_tokens_sessions.py
│  │     └─ 0008_device_assigned_user.py
│  ├─ tests/
│  │  ├─ __init__.py
│  │  ├─ conftest.py
│  │  ├─ helpers.py
│  │  ├─ test_admin_devices_assignment.py
│  │  ├─ test_admin_users_update.py
│  │  ├─ test_certificate_ingest.py
│  │  ├─ test_workers_queue.py
│  │  └─ test_rbac_jobs.py
│  ├─ alembic.ini
│  └─ requirements.txt
│
├─ docs/
│  └─ api/
│     └─ openapi.json
│
├─ frontend/
│  ├─ src/
│  │  ├─ App.tsx
│  │  ├─ components/
│  │  │  ├─ AppShell.tsx
│  │  │  ├─ Modal.tsx
│  │  │  ├─ ProtectedRoute.tsx
│  │  │  ├─ SectionTabs.tsx
│  │  │  └─ Toast.tsx
│  │  ├─ context/
│  │  │  └─ AuthContext.tsx
│  │  ├─ hooks/
│  │  │  ├─ useAuth.ts
│  │  │  └─ useToast.ts
│  │  ├─ lib/
│  │  │  ├─ apiClient.ts
│  │  │  └─ formatters.ts
│  │  ├─ pages/
│  │  │  ├─ Audit.tsx
│  │  │  ├─ Certificates.tsx
│  │  │  ├─ Devices.tsx
│  │  │  ├─ Jobs.tsx
│  │  │  ├─ Login.tsx
│  │  │  ├─ ResetPassword.tsx
│  │  │  └─ SetPassword.tsx
│  │  ├─ index.css
│  │  └─ main.tsx
│  ├─ index.html
│  ├─ package-lock.json
│  ├─ package.json
│  ├─ postcss.config.cjs
│  ├─ README.md
│  ├─ tailwind.config.cjs
│  ├─ tsconfig.json
│  ├─ tsconfig.node.json
│  └─ vite.config.ts
│
├─ infra/
│  └─ docker-compose.yml
│
├─ scripts/
│  └─ http/
│     ├─ login.admin.json
│     ├─ login.dev.json
│     ├─ payload_confirm.json
│     ├─ payload_init.json
│     ├─ set_confirm.json
│     └─ set_init.json
│
├─ .env.example
├─ .gitignore
├─ ESTRUTURA_REPO.md
├─ PLANO_DESENVOLVIMENTO.md
├─ README.md
└─ requirements.txt
```

## S4.1 (planejado)

- `infra/docker-compose.yml`: incluir serviço Redis para fila do watcher/worker.
- `backend/`: novos entrypoints do watcher e do worker RQ, além dos jobs de ingest/delete, serão adicionados dentro do pacote `app/`.
- `backend/app/workers/jobs_certificates.py`: delete por `source_path` com fallback por `name` e logs de estratégia/rowcount.
