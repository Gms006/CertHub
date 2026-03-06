param(
  [string]$PortalUrl = "https://certhub.local"
)

$hasError = $false

# Garante UTF-8 no output (evita "indisponível", etc.)
try {
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {}

function Join-Url {
  param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,
    [Parameter(Mandatory = $true)]
    [string]$PathOrUrl
  )

  if ($PathOrUrl -match '^https?://') { return $PathOrUrl }

  $base = $BaseUrl.TrimEnd('/')
  $path = $PathOrUrl.TrimStart('/')

  if ([string]::IsNullOrWhiteSpace($path)) { return $base }

  return "$base/$path"
}

function Normalize-Url {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Url
  )

  # Normaliza apenas o caminho, preservando "https://"
  if ($Url -match '^(https?://[^/]+)(/.*)?$') {
    $origin = $Matches[1]
    $pathAndMore = $Matches[2]
    if ([string]::IsNullOrEmpty($pathAndMore)) { return $origin }
    $pathAndMore = ($pathAndMore -replace '/{2,}', '/')
    return "$origin$pathAndMore"
  }

  return ($Url -replace '/{2,}', '/')
}

function Invoke-Curl-With-Fallback {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Url,
    [switch]$Head
  )

  function Invoke-CurlInternal {
    param(
      [Parameter(Mandatory = $true)]
      [string]$TargetUrl,
      [switch]$UseHead,
      [switch]$NoRevoke
    )

    $TargetUrl = Normalize-Url $TargetUrl

    $statusMarker = "__CURL_STATUS_CODE__:"
    $commonArgs = @("-fsSL")
    if ($NoRevoke) {
      $commonArgs += "--ssl-no-revoke"
    }

    if ($UseHead) {
      $args = $commonArgs + @("-I", "-w", "`n$statusMarker%{http_code}", $TargetUrl)
    } else {
      $args = $commonArgs + @("-w", "`n$statusMarker%{http_code}", $TargetUrl)
    }

    $rawOutput = & curl.exe @args 2>&1
    $joinedOutput = ($rawOutput -join "`n")

    $statusCode = $null
    if ($joinedOutput -match "$statusMarker(\d{3})") {
      $statusCode = [int]$Matches[1]
      $joinedOutput = $joinedOutput -replace "(\r?\n)?$statusMarker\d{3}\s*$", ""
    }

    $statusLine = ([regex]::Split($joinedOutput, "\r?\n") | Where-Object { $_ -match "^HTTP/" } | Select-Object -First 1)
    if ($null -eq $statusCode -and $statusLine -and $statusLine -match "^HTTP/\S+\s+(\d{3})\b") {
      $statusCode = [int]$Matches[1]
    }

    return [PSCustomObject]@{
      ExitCode   = $LASTEXITCODE
      Output     = $joinedOutput
      StatusLine = $statusLine
      StatusCode = $statusCode
    }
  }

  $firstTry = Invoke-CurlInternal -TargetUrl $Url -UseHead:$Head
  if ($firstTry.ExitCode -ne 0 -and $firstTry.Output -match "CRYPT_E_NO_REVOCATION_CHECK") {
    Write-Host "[WARN] TLS revocation check indisponível, tentando com --ssl-no-revoke: $Url"
    return Invoke-CurlInternal -TargetUrl $Url -UseHead:$Head -NoRevoke
  }

  return $firstTry
}

function Test-MixedContent {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Content,
    [Parameter(Mandatory = $true)]
    [string]$SourceLabel
  )

  $allowedHttpPrefixes = @(
    "http://www.w3.org/"
  )

  $matches = [regex]::Matches($Content, 'http://[^\s"''<>]+', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
  $allUrls = @($matches | ForEach-Object { $_.Value } | Select-Object -Unique)
  $offenders = @(
    $allUrls |
      Where-Object {
        $candidate = $_.ToLowerInvariant()
        -not ($allowedHttpPrefixes | Where-Object { $candidate.StartsWith($_.ToLowerInvariant()) })
      }
  )

  if ($offenders.Count -gt 0) {
    Write-Warning "[FAIL] Mixed content fora da allowlist em ${SourceLabel}:"
    foreach ($url in $offenders) {
      Write-Warning "  - $url"
    }
    return $false
  }

  Write-Host "[OK] Sem mixed content inválido em $SourceLabel"
  return $true
}

Write-Host "==> HEAD portal: $PortalUrl"
$portalHead = Invoke-Curl-With-Fallback -Url $PortalUrl -Head
if ($portalHead.ExitCode -eq 0) {
  Write-Host "[OK] TLS handshake portal sem -k"
  $portalHeaders = $portalHead.Output
  $portalHeaders
  if ($null -eq $portalHead.StatusCode) {
    Write-Warning "[FAIL] HEAD portal sem StatusLine/StatusCode válido"
    $hasError = $true
  } elseif ($portalHead.StatusCode -ge 400) {
    Write-Warning "[FAIL] HEAD portal retornou status $($portalHead.StatusCode)"
    $hasError = $true
  }
} else {
  Write-Warning "[FAIL] Portal indisponível via TLS sem -k"
  Write-Host $portalHead.Output
  $hasError = $true
  $portalHeaders = ""
}

Write-Host "==> GET health: $PortalUrl/health"
$healthResponse = Invoke-Curl-With-Fallback -Url (Join-Url $PortalUrl "health")
if ($healthResponse.ExitCode -eq 0 -and $healthResponse.StatusCode -eq 200) {
  Write-Host "[OK] GET /health retornou 200"
} else {
  Write-Warning "[FAIL] GET /health falhou (StatusCode=$($healthResponse.StatusCode), ExitCode=$($healthResponse.ExitCode))"
  Write-Host $healthResponse.Output
  $hasError = $true
}

$requiredHeaders = @(
  "Strict-Transport-Security",
  "X-Content-Type-Options",
  "X-Frame-Options",
  "Content-Security-Policy"
)

Write-Host "==> Checking security headers on portal response"
foreach ($header in $requiredHeaders) {
  if ($portalHeaders -match $header) {
    Write-Host "[OK] $header"
  } else {
    Write-Warning "[MISSING] $header"
    $hasError = $true
  }
}

Write-Host "==> Checking mixed content marker (http://) on portal HTML"
$portalHtml = Invoke-Curl-With-Fallback -Url $PortalUrl
if ($portalHtml.ExitCode -ne 0) {
  Write-Warning "[FAIL] Não foi possível baixar HTML do portal para validação de mixed content"
  Write-Host $portalHtml.Output
  $hasError = $true
} else {
  if (-not (Test-MixedContent -Content $portalHtml.Output -SourceLabel "HTML principal")) {
    $hasError = $true
  }
}

$jsMatches = [regex]::Matches($portalHtml.Output, 'src\s*=\s*["'']([^"'']+\.js(?:\?[^"'']*)?)["'']', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
$jsSources = @($jsMatches | ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique | Select-Object -First 3)
if ($jsSources.Count -gt 0) {
  Write-Host "==> Checking mixed content marker (http://) em até 3 arquivos JS"
}

foreach ($jsSrc in $jsSources) {
  if ($jsSrc -match "^https?://") {
    $jsUrl = $jsSrc
  } elseif ($jsSrc -match "^/") {
    $jsUrl = Join-Url $PortalUrl $jsSrc
  } else {
    $jsUrl = Join-Url $PortalUrl $jsSrc
  }

  Write-Host "==> GET JS: $jsUrl"
  $jsResponse = Invoke-Curl-With-Fallback -Url $jsUrl
  if ($jsResponse.ExitCode -ne 0) {
    Write-Warning "[FAIL] Não foi possível baixar JS: $jsUrl"
    Write-Host $jsResponse.Output
    $hasError = $true
    continue
  }

  if (-not (Test-MixedContent -Content $jsResponse.Output -SourceLabel "JS $jsUrl")) {
    $hasError = $true
  }
}

if ($hasError) {
  exit 1
}

Write-Host "[OK] Validação TLS concluída"
exit 0
