# Build do CertHub Agent (Windows)

Pré-requisitos: Windows 10/11 com .NET 8 SDK instalado.

> Nota: o `global.json` fixa o SDK em `8.0.404` com roll-forward para `latestMinor`.
> Se a sua instalação tiver outra versão 8.0.x, ajuste o `global.json` para a versão disponível.

```powershell
cd agent\windows\Certhub.Agent

dotnet restore

dotnet publish -c Release -r win-x64 --self-contained true /p:PublishSingleFile=true /p:IncludeNativeLibrariesForSelfExtract=true
```

O executável será gerado em:

```
agent\windows\Certhub.Agent\Certhub.Agent\bin\Release\net8.0-windows\win-x64\publish\Certhub.Agent.exe
```

Para executar, copie o `.exe` para a máquina alvo e abra o aplicativo (ele iniciará no tray).
