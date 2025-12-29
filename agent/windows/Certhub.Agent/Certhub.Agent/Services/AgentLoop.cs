using System.Security.Cryptography.X509Certificates;
using Certhub.Agent.Models;

namespace Certhub.Agent.Services;

public sealed class AgentLoop
{
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
            await _client!.ClaimJobAsync(jobId, cancellationToken);
        }
        catch (Exception ex)
        {
            _logger.Warn($"Claim failed for job {jobId}: {ex.Message}");
            UpdateStatus(lastJobStatus: "CLAIM_FAILED", error: ex.Message);
            return;
        }

        AgentClient.PayloadResponse payload;
        try
        {
            payload = await _client!.GetPayloadAsync(jobId, cancellationToken);
        }
        catch (Exception ex)
        {
            _logger.Error($"Payload fetch failed for job {jobId}", ex);
            await ReportFailureAsync(jobId, "PAYLOAD_FAILED", "Failed to fetch payload", cancellationToken);
            UpdateStatus(lastJobStatus: "PAYLOAD_FAILED", error: ex.Message);
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
        var stored = _thumbprintsStore.Load(_configStore.InstalledThumbprintsPath).ToList();
        if (!stored.Contains(normalized, StringComparer.OrdinalIgnoreCase))
        {
            stored.Add(normalized);
            _thumbprintsStore.Save(_configStore.InstalledThumbprintsPath, stored);
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
}
