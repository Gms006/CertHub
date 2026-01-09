# QA checklist — S9 (KEEP_UNTIL + cleanup)

> Objetivo: validar que KEEP_UNTIL é executado via task ONCE, remove apenas entradas KEEP_UNTIL e não afeta jobs DEFAULT.

## Pré-requisitos

- Backend e Agent rodando.
- Um usuário DEV e um usuário VIEW com device vinculado.
- IDs do certificado e do device disponíveis.

## Checklist

1. **Criar 1 job DEFAULT (DEV)**
   - Criar job sem `cleanup_mode` (padrão 18h).
   - Confirmar que o certificado está instalado no `Cert:\CurrentUser\My`.

2. **Criar 1 job KEEP_UNTIL (DEV)**
   - Criar job com `cleanup_mode=KEEP_UNTIL` e `keep_until` ~2 min no futuro.
   - Verificar criação da task:
     ```powershell
     schtasks /Query /TN "CertHub KeepUntil YYYYMMDD-HHmm" /V /FO LIST
     ```
   - Aguardar a execução e confirmar que a task foi auto-deletada.
   - Verificar logs do Agent: `Starting cleanup (KeepUntil)` e `In-scope: 1`.

3. **Confirmar escopo do cleanup KEEP_UNTIL (DEV)**
   - Após execução, confirmar que o certificado DEFAULT **permanece** instalado.
   - Confirmar que apenas o certificado do job KEEP_UNTIL foi removido.

4. **Repetir em usuário VIEW**
   - Criar job KEEP_UNTIL com usuário VIEW (device vinculado).
   - Validar criação/execução da task via `schtasks` e auto-delete.

## Observações

- Se necessário, o smoke test pode ser executado em `scripts/windows/s9_retention_smoke.ps1`.
