# S10 Deployment Guide (Piloto LAN e Trilha Produção)

## Escopo
- Fechar S10 (piloto LAN) com domínio único `certhub.local`.
- Preparar S10.1 (produção) sem ativar infraestrutura automaticamente.

## Opção 1: Caddy com Let's Encrypt (S10.1)
Requisitos:
- Domínio público válido (ex.: `portal.suaempresa.com`).
- Portas 80 e 443 publicamente acessíveis.
- E-mail para ACME/Let's Encrypt.

Passos:
1. Copiar `infra/https/Caddyfile.prod.template` para um arquivo de trabalho (ex.: `infra/https/Caddyfile.prod`).
2. Substituir placeholders:
   - `{$CERT_DOMAIN}` pelo domínio final.
   - `{$LE_EMAIL}` pelo e-mail operacional.
3. Garantir backend em `127.0.0.1:8010` e frontend em `frontend/dist`.
4. Iniciar Caddy com o arquivo de produção.
5. Validar:
   - `curl -I https://<dominio>`
   - `curl -I https://<dominio>/api/v1/health`

## Opção 2: CA corporativa
Quando usar:
- Ambiente sem exposição pública.
- Política corporativa de certificados internos.

Passos high-level:
1. Emitir certificado server para o domínio final no PKI corporativo.
2. Instalar cadeia completa (root/intermediate) no servidor e clientes.
3. Configurar Caddy para usar cert/key emitidos pela CA corporativa.
4. Validar cadeia e hostname com `curl -I https://<dominio>`.

## Rodar como serviço no Windows (abordagem NSSM)
Sem download automático neste repositório.

Passos:
1. Instalar NSSM manualmente (fonte oficial da empresa/política interna).
2. Criar serviço apontando para `caddy.exe`.
3. Argumentos típicos:
   - `run --config <caminho-do-caddyfile> --adapter caddyfile`
4. Definir diretório de trabalho do serviço para `infra/https`.
5. Configurar política de restart do serviço.

## Renovação e monitoramento
- Let's Encrypt: renovação automática pelo Caddy (validar logs periodicamente).
- Verificação rápida:
  - `curl -Iv https://<dominio>`
  - `caddy list-modules` (sanidade do binário)
- Monitorar:
  - validade do certificado
  - falhas de handshake
  - status do serviço Caddy

## Backup e restore
Backup mínimo:
- Banco Postgres (dump consistente).
- `infra/https/Caddyfile` e variações (`Caddyfile.prod`).
- Arquivos `.env` por ambiente (sem versionar segredos).

Restore mínimo:
1. Restaurar banco.
2. Restaurar config Caddy e variáveis de ambiente.
3. Subir backend + Caddy.
4. Validar health e login do portal.

## Checklist de validação (curl/PowerShell)
1. `curl -I https://certhub.local`
2. `curl -I https://certhub.local/api/v1/health`
3. `.\scripts\windows\s10_validate_tls.ps1 -PortalUrl https://certhub.local`
4. Confirmar headers:
   - `Strict-Transport-Security`
   - `X-Content-Type-Options`
   - `X-Frame-Options`
   - `Content-Security-Policy`
5. Confirmar ausência de `http://` no HTML principal.
