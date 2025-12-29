# CertHub Frontend

## Desenvolvimento

```bash
npm install
npm run dev
```

O frontend sobe em `http://localhost:8011` para evitar conflito com outros portais locais.

### Variáveis de ambiente

Copie `.env.example` para `.env` e ajuste conforme necessário:

```bash
VITE_API_URL=http://localhost:8010/api/v1
```

`VITE_API_URL` (opcional) define a URL base da API. Padrão: `http://localhost:8010/api/v1`.
