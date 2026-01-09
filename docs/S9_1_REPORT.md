# Relatório S9.1 — Inventário Installed Certs

## Lista DPAPI de thumbprints (Agent)
- **Arquivo/classe**: `agent/windows/Certhub.Agent/Certhub.Agent/Services/InstalledThumbprintsStore.cs`.
- **Formato**: lista JSON de `InstalledThumbprintEntry` protegida via DPAPI.
- **Campos existentes**: `thumbprint`, `cleanup_mode`, `keep_until`, `keep_reason`, `job_id`, `installed_at`. (Propriedades: `Thumbprint`, `CleanupMode`, `KeepUntil`, `KeepReason`, `JobId`, `InstalledAt`).
- **Persistência**: `installed_thumbprints.json` em `LocalApplicationData/CertHubAgent`, cifrado com DPAPI (CurrentUser) via `DpapiStore`.

## Endpoints do Agent (backend)
- **Arquivo**: `backend/app/api/v1/endpoints/agent.py`.
- **Endpoints**:
  - `POST /agent/auth`
  - `GET /agent/me`
  - `POST /agent/heartbeat`
  - `POST /agent/cleanup`
  - `GET /agent/jobs`
  - `POST /agent/jobs/{job_id}/claim`
  - `GET /agent/jobs/{job_id}/payload`
  - `POST /agent/jobs/{job_id}/result`
- **Devices**: `backend/app/api/v1/endpoints/devices.py` possui `GET /devices/mine` para listar devices permitidos ao usuário.

## Jobs e retenção (backend)
- **Model**: `backend/app/models/cert_install_job.py`.
- **Campos de retenção**: `cleanup_mode`, `keep_until`, `keep_reason`, `keep_set_by_user_id`, `keep_set_at`.
- **Migração S9**: `backend/alembic/versions/0012_s9_retention_fields.py`.

## Autenticação do Agent e rate limits
- **JWT do device**: criado por `create_device_access_token` em `backend/app/core/security.py` (role `DEVICE`).
- **Validação**: `require_device` em `backend/app/core/security.py`.
- **Rate limits**: aplicados em `/agent/auth` e `/agent/jobs/{id}/payload` dentro de `backend/app/api/v1/endpoints/agent.py`.
