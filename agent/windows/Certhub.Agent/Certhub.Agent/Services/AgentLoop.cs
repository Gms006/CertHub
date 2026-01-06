using System.Net;
using System.Security.Cryptography.X509Certificates;
using Certhub.Agent.Models;

namespace Certhub.Agent.Services;

public sealed class AgentLoop
{
    private static readonly TimeSpan MaxRateLimitDelay = TimeSpan.FromSeconds(30);
    private readonly AgentConfigStore _configStore;
    private readonly DpapiStore _dpapiStore;
    private readonly InstalledThumbprintsStore _thumbprintsStore;
    private readonly CertificateCleanupService _cleanupService;
    private readonly Logger _logger;
    private readonly AgentStatus _status = new();
    private CancellationTokenSource? _cts;
    private Task? _loopTask;
    private AgentClient? _client;
    private string? _currentBaseUrl;

    public AgentLoop(
        AgentConfigStore configStore,
        DpapiStore dpapiStore,
        InstalledThumbprintsStore thumbprintsStore,
        CertificateCleanupService cleanupService,
        Logger logger)
    {
        _configStore = configStore;
        _dpapiStore = dpapiStore;
        _thumbprintsStore = thumbprintsStore;
        _cleanupService = cleanupService;
        _logger = logger;
    }

    public AgentStatus Status => _status;

    public event Action? StatusChanged;

    public void Start()
    {
        if (_loopTask is not null && !_loopTask.IsCompleted)
        {
            return;
        }

        _cts = new CancellationTokenSource();
        _loopTask = Task.Run(() => RunAsync(_cts.Token));
    }

    public void Restart()
    {
        Stop();
        Start();
    }

    public void Stop()
    {
        if (_cts is null)
        {
            return;
        }

        _cts.Cancel();
        _cts.Dispose();
        _cts = null;
    }

    private async Task RunAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            var config = _configStore.Load();
            if (config is null || !config.IsValid())
            {
                await Task.Delay(TimeSpan.FromSeconds(5), cancellationToken);
                continue;
            }

            var deviceToken = _dpapiStore.LoadString(_configStore.SecretsPath);
            if (string.IsNullOrWhiteSpace(deviceToken))
            {
                await Task.Delay(TimeSpan.FromSeconds(5), cancellationToken);
                continue;
            }

            if (_client is null || !string.Equals(_currentBaseUrl, config.ApiBaseUrl, StringComparison.OrdinalIgnoreCase))
            {
                _client = new AgentClient(config.ApiBaseUrl, _logger);
                _currentBaseUrl = config.ApiBaseUrl;
            }

            _client.UpdateCredentials(config.DeviceId, deviceToken);

            try
            {
                await _client.AuthenticateAsync(config.DeviceId, deviceToken, cancellationToken);
            }
            catch (Exception ex)
            {
                _logger.Error("Failed to authenticate device", ex);
                UpdateStatus(error: "Auth failed");
                await Task.Delay(TimeSpan.FromSeconds(10), cancellationToken);
                continue;
            }

            await EnsureFallbackCleanupAsync(config, cancellationToken);
            await RunPollingLoopAsync(config, deviceToken, cancellationToken);
        }
    }

    private async Task RunPollingLoopAsync(AgentConfig config, string deviceToken, CancellationToken cancellationToken)
    {
        var idleSeconds = Math.Max(config.PollingIntervalSecondsIdle, 1);
        var activeSeconds = Math.Max(config.PollingIntervalSecondsActive, 1);
        if (idleSeconds < activeSeconds)
        {
            idleSeconds = activeSeconds;
        }

        var pollInterval = TimeSpan.FromSeconds(activeSeconds);
        var pollingMode = "active";
        UpdateStatus(pollingIntervalSeconds: (int)pollInterval.TotalSeconds, pollingMode: pollingMode);
        var nextHeartbeat = DateTimeOffset.UtcNow;

        while (!cancellationToken.IsCancellationRequested)
        {
            if (DateTimeOffset.UtcNow >= nextHeartbeat)
            {
                await SendHeartbeatAsync(cancellationToken);
                nextHeartbeat = DateTimeOffset.UtcNow.Add(pollInterval > TimeSpan.FromSeconds(30)
                    ? pollInterval
                    : TimeSpan.FromSeconds(30));
            }

            var hasActiveJob = false;
            try
            {
                var jobs = await _client!.GetJobsAsync(cancellationToken);
                hasActiveJob = jobs.Any(j => string.Equals(j.Status, "PENDING", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(j.Status, "REQUESTED", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(j.Status, "IN_PROGRESS", StringComparison.OrdinalIgnoreCase));
                var job = jobs.FirstOrDefault(j => string.Equals(j.Status, "PENDING", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(j.Status, "REQUESTED", StringComparison.OrdinalIgnoreCase));
                if (job is not null)
                {
                    await ProcessJobAsync(job.Id, cancellationToken);
                }
            }
            catch (Exception ex)
            {
                _logger.Error("Job polling failed", ex);
                UpdateStatus(error: "Polling failed");
            }

            if (hasActiveJob)
            {
                pollInterval = TimeSpan.FromSeconds(activeSeconds);
                pollingMode = "active";
            }
            else
            {
                var nextSeconds = Math.Min(idleSeconds, Math.Max(activeSeconds, (int)Math.Ceiling(pollInterval.TotalSeconds * 1.5)));
                pollInterval = TimeSpan.FromSeconds(nextSeconds);
                pollingMode = "idle";
            }

            UpdateStatus(pollingIntervalSeconds: (int)pollInterval.TotalSeconds, pollingMode: pollingMode);
            await Task.Delay(pollInterval, cancellationToken);
        }
    }

    private async Task EnsureFallbackCleanupAsync(AgentConfig config, CancellationToken cancellationToken)
    {
        var nowLocal = DateTime.Now;
        if (nowLocal.TimeOfDay < TimeSpan.FromHours(18))
        {
            return;
        }

        if (config.LastCleanupLocalDate?.Date == nowLocal.Date)
        {
            return;
        }

        _logger.Info("Fallback cleanup triggered (after 18:00 and not run today).");
        var result = _cleanupService.Run(CleanupMode.Fallback);
        if (result.Success)
        {
            config.LastCleanupLocalDate = nowLocal.Date;
            _configStore.Save(config);
        }

        await ReportCleanupAsync(result, cancellationToken);
    }

    private async Task ReportCleanupAsync(CleanupResult result, CancellationToken cancellationToken)
    {
        if (_client is null)
        {
            _logger.Warn("Cleanup audit skipped: client not initialized.");
            return;
        }

        try
        {
            var response = await _client.PostCleanupAsync(new AgentClient.CleanupEvent
            {
                RemovedCount = result.RemovedCount,
                FailedCount = result.FailedCount,
                RemovedThumbprints = result.RemovedThumbprints.ToList(),
                FailedThumbprints = result.FailedThumbprints.ToList(),
                SkippedCount = result.SkippedCount,
                SkippedThumbprints = result.SkippedThumbprints.ToList(),
                Mode = result.Mode.ToString().ToLowerInvariant(),
                RanAtLocal = result.RanAtLocal.ToString("o"),
            }, cancellationToken);

            if (!response.IsSuccessStatusCode)
            {
                _logger.Warn($"Cleanup audit failed: {(int)response.StatusCode} {response.ReasonPhrase}");
            }
        }
        catch (Exception ex)
        {
            _logger.Error("Cleanup audit failed with exception.", ex);
        }
    }

    private async Task SendHeartbeatAsync(CancellationToken cancellationToken)
    {
        try
        {
            var response = await _client!.PostHeartbeatAsync("1.0.0", cancellationToken);
            if (response.IsSuccessStatusCode)
            {
                UpdateStatus(lastHeartbeatAt: DateTimeOffset.UtcNow, error: null);
            }
            else
            {
                _logger.Warn($"Heartbeat failed: {(int)response.StatusCode} {response.ReasonPhrase}");
                UpdateStatus(error: "Heartbeat failed");
            }
        }
        catch (Exception ex)
        {
            _logger.Error("Heartbeat error", ex);
            UpdateStatus(error: "Heartbeat error");
        }
    }

    private async Task ProcessJobAsync(Guid jobId, CancellationToken cancellationToken)
    {
        UpdateStatus(lastJobId: jobId.ToString(), lastJobStatus: "CLAIMING", error: null);

        try
        {
            var payloadToken = await _client!.ClaimJobAsync(jobId, cancellationToken);
            UpdateStatus(lastJobStatus: "PAYLOAD_TOKEN_READY", error: null);
            await FetchAndInstallAsync(jobId, payloadToken, cancellationToken);
            return;
        }
        catch (Exception ex)
        {
            _logger.Warn($"Claim failed for job {jobId}: {ex.Message}");
            UpdateStatus(lastJobStatus: "CLAIM_FAILED", error: ex.Message);
            return;
        }
    }

    private async Task FetchAndInstallAsync(Guid jobId, string payloadToken, CancellationToken cancellationToken)
    {
        AgentClient.PayloadResponse? payload = null;
        var currentToken = payloadToken;
        var attempt = 0;
        var maxAttempts = 5;
        var rateLimitDelay = TimeSpan.FromSeconds(1);

        try
        {
            while (attempt < maxAttempts)
            {
                try
                {
                    payload = await _client!.GetPayloadAsync(jobId, currentToken, cancellationToken);
                    break;
                }
                catch (AgentClient.ApiRequestException ex) when (ex.StatusCode == HttpStatusCode.TooManyRequests)
                {
                    var delay = GetJitteredDelay(rateLimitDelay);
                    _logger.Warn($"Payload rate limited for job {jobId}. Retrying in {delay.TotalSeconds:F1}s.");
                    await Task.Delay(delay, cancellationToken);
                    rateLimitDelay = TimeSpan.FromSeconds(Math.Min(rateLimitDelay.TotalSeconds * 2, MaxRateLimitDelay.TotalSeconds));
                    attempt++;
                }
                catch (AgentClient.ApiRequestException ex) when (ex.StatusCode == HttpStatusCode.Gone
                    || ex.StatusCode == HttpStatusCode.Conflict
                    || ex.StatusCode == HttpStatusCode.Forbidden)
                {
                    _logger.Warn($"Payload token rejected ({(int)ex.StatusCode}) for job {jobId}. Re-claiming.");
                    await Task.Delay(GetJitteredDelay(TimeSpan.FromSeconds(1)), cancellationToken);
                    try
                    {
                        currentToken = await _client!.ClaimJobAsync(jobId, cancellationToken);
                        UpdateStatus(lastJobStatus: "PAYLOAD_TOKEN_REFRESHED", error: null);
                    }
                    catch (Exception claimEx)
                    {
                        _logger.Warn($"Re-claim failed for job {jobId}: {claimEx.Message}");
                        break;
                    }

                    attempt++;
                }
                catch (AgentClient.ApiRequestException ex)
                {
                    _logger.Error($"Payload fetch failed for job {jobId}: {(int)ex.StatusCode} {ex.Message}");
                    break;
                }
            }
        }
        catch (Exception ex)
        {
            _logger.Error($"Payload fetch failed for job {jobId}", ex);
        }

        if (payload is null)
        {
            await ReportFailureAsync(jobId, "PAYLOAD_FAILED", "Failed to fetch payload", cancellationToken);
            UpdateStatus(lastJobStatus: "PAYLOAD_FAILED", error: "Failed to fetch payload");
            return;
        }

        try
        {
            var thumbprint = InstallCertificate(payload);
            await _client!.SendResultAsync(jobId, new AgentClient.ResultUpdate
            {
                Status = "DONE",
                Thumbprint = thumbprint
            }, cancellationToken);
            UpdateStatus(lastJobStatus: "DONE", error: null);
        }
        catch (Exception ex)
        {
            _logger.Error($"Install failed for job {jobId}", ex);
            await ReportFailureAsync(jobId, "INSTALL_FAILED", ex.Message, cancellationToken);
            UpdateStatus(lastJobStatus: "FAILED", error: ex.Message);
        }
    }

    private string InstallCertificate(AgentClient.PayloadResponse payload)
    {
        var rawBytes = Convert.FromBase64String(payload.PfxBase64);
        using var certificate = new X509Certificate2(rawBytes, payload.Password,
            X509KeyStorageFlags.PersistKeySet | X509KeyStorageFlags.UserKeySet);

        using var store = new X509Store(StoreName.My, StoreLocation.CurrentUser);
        store.Open(OpenFlags.ReadWrite);
        var thumbprint = certificate.Thumbprint ?? string.Empty;
        var existing = store.Certificates.Find(X509FindType.FindByThumbprint, thumbprint, false);
        if (existing.Count == 0)
        {
            store.Add(certificate);
        }

        var normalized = thumbprint.Replace(" ", string.Empty).ToUpperInvariant();
        var stored = _thumbprintsStore.LoadEntries(_configStore.InstalledThumbprintsPath).ToList();
        var existingEntry = stored.FirstOrDefault(entry =>
            string.Equals(entry.Thumbprint, normalized, StringComparison.OrdinalIgnoreCase));
        if (existingEntry is not null)
        {
            existingEntry.JobId = payload.JobId;
            existingEntry.CleanupMode = payload.CleanupMode ?? "DEFAULT";
            existingEntry.KeepUntil = payload.KeepUntil;
            existingEntry.KeepReason = payload.KeepReason;
            existingEntry.InstalledAt = DateTimeOffset.UtcNow;
            _thumbprintsStore.SaveEntries(_configStore.InstalledThumbprintsPath, stored);
            _logger.Info($"Updated retention policy for thumbprint: {normalized}");
        }
        else
        {
            stored.Add(new InstalledThumbprintEntry
            {
                Thumbprint = normalized,
                JobId = payload.JobId,
                CleanupMode = payload.CleanupMode ?? "DEFAULT",
                KeepUntil = payload.KeepUntil,
                KeepReason = payload.KeepReason,
                InstalledAt = DateTimeOffset.UtcNow
            });
            _thumbprintsStore.SaveEntries(_configStore.InstalledThumbprintsPath, stored);
            _logger.Info($"Installed thumbprint persisted via DPAPI: {normalized}");
        }

        return normalized;
    }

    private async Task ReportFailureAsync(Guid jobId, string errorCode, string errorMessage, CancellationToken cancellationToken)
    {
        await _client!.SendResultAsync(jobId, new AgentClient.ResultUpdate
        {
            Status = "FAILED",
            ErrorCode = errorCode,
            ErrorMessage = errorMessage
        }, cancellationToken);
    }

    private void UpdateStatus(
        DateTimeOffset? lastHeartbeatAt = null,
        string? lastJobId = null,
        string? lastJobStatus = null,
        string? error = null,
        int? pollingIntervalSeconds = null,
        string? pollingMode = null)
    {
        if (lastHeartbeatAt.HasValue)
        {
            _status.LastHeartbeatAt = lastHeartbeatAt;
        }

        if (!string.IsNullOrWhiteSpace(lastJobId))
        {
            _status.LastJobId = lastJobId;
        }

        if (!string.IsNullOrWhiteSpace(lastJobStatus))
        {
            _status.LastJobStatus = lastJobStatus;
        }

        if (pollingIntervalSeconds.HasValue)
        {
            _status.PollingIntervalSeconds = pollingIntervalSeconds;
        }

        if (!string.IsNullOrWhiteSpace(pollingMode))
        {
            _status.PollingMode = pollingMode;
        }

        _status.LastError = error;
        StatusChanged?.Invoke();
    }

    private static TimeSpan GetJitteredDelay(TimeSpan baseDelay)
    {
        var jitterSeconds = baseDelay.TotalSeconds * 0.2;
        var jitter = (Random.Shared.NextDouble() * 2 - 1) * jitterSeconds;
        var totalSeconds = Math.Max(0, baseDelay.TotalSeconds + jitter);
        return TimeSpan.FromSeconds(totalSeconds);
    }
}
