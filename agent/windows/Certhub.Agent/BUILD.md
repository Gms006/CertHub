# Build do CertHub Agent (Windows)

Pré-requisitos: Windows 10/11 com .NET 8 SDK instalado.

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
