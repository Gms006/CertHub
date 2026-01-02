# Treinamento rápido — CertHub (usuário final)

## 1) Como pedir instalação no portal

1. Acesse o portal com seu usuário.
2. Encontre o certificado desejado.
3. Clique em **Instalar**.
4. Selecione o dispositivo correto e confirme.

## 2) Status dos jobs (significado)

- **REQUESTED**: pedido enviado e **aguardando aprovação** (ADMIN/DEV).
- **PENDING**: aprovado e aguardando o agent instalar.
- **DONE**: certificado instalado com sucesso.
- **FAILED**: falha na instalação (contate o admin).

## 3) O que acontece quando precisa de aprovação

Se o status ficar **REQUESTED**, um ADMIN/DEV precisa aprovar.
Após a aprovação, o status muda para **PENDING** e o agent executa a instalação.

## 4) Como verificar no Windows se instalou

- **certmgr.msc** → *Current User* → *Personal*.
- ou via terminal:
  ```powershell
  certutil -user -store My
  ```

## 5) O que acontece às 18h

Todos os certificados temporários instalados pelo agent são removidos às **18:00**.

Para suporte, o admin pode consultar o log do agent: `agent.log`.
