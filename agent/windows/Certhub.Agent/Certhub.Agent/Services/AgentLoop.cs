using System.Net;
using System.Security.Cryptography.X509Certificates;
using System.Threading;
using Certhub.Agent.Models;

namespace Certhub.Agent.Services;

public sealed class AgentLoop
{
    private static readonly TimeSpan MaxRateLimitDelay = TimeSpan.FromSeconds(30);
    private const string RemoveJobType = "REMOVE_CERT";
    private readonly AgentConfigStore _configStore;
    private readonly DpapiStore _dpapiStore;
    private readonly InstalledThumbprintsStore _thumbprintsStore;
    private readonly CertificateCleanupService _cleanupService;
    private readonly ScheduledCleanupTaskService _scheduledTaskService;
    private readonly InstalledCertsReporter _installedCertsReporter;
    private readonly string _executablePath;
    private readonly Logger _logger;
    private readonly AgentStatus _status = new();
    private CancellationTokenSource? _cts;
    private Task? _loopTask;
    private AgentClient? _client;
    private string? _currentBaseUrl;
    private DateTimeOffset _nextInstalledCertsReportAt = DateTimeOffset.MinValue;
    private readonly SemaphoreSlim _installedCertsReportLock = new(1, 1);

    public AgentLoop(
        AgentConfigStore configStore,
        DpapiStore dpapiStore,
        InstalledThumbprintsStore thumbprintsStore,
        CertificateCleanupService cleanupService,
        ScheduledCleanupTaskService scheduledTaskService,
        InstalledCertsReporter installedCertsReporter,
        string executablePath,
        Logger logger)
    {
        _configStore = configStore;
        _dpapiStore = dpapiStore;
        _thumbprintsStore = thumbprintsStore;
        _cleanupService = cleanupService;
        _scheduledTaskService = scheduledTaskService;
        _installedCertsReporter = installedCertsReporter;
        _executablePath = executablePath;
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

            await ReportInstalledCertsAsync(config, cancellationToken);

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
        await ReportInstalledCertsAsync(config, cancellationToken, force: true);
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

    private async Task ReportInstalledCertsAsync(
        AgentConfig config,
        CancellationToken cancellationToken,
        bool force = false)
    {
        if (_client is null)
        {
            return;
        }

        var intervalSeconds = config.InstalledCertsReportIntervalSeconds;
        if (intervalSeconds <= 0)
        {
            return;
        }

        var now = DateTimeOffset.UtcNow;
        if (!force && now < _nextInstalledCertsReportAt)
        {
            return;
        }

        if (!await _installedCertsReportLock.WaitAsync(0, cancellationToken))
        {
            return;
        }

        try
        {
            var success = await _installedCertsReporter.SendSnapshotAsync(
                _client,
                config.DeviceId,
                cancellationToken);
            if (success)
            {
                _nextInstalledCertsReportAt = now.AddSeconds(intervalSeconds);
            }
        }
        finally
        {
            _installedCertsReportLock.Release();
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
            if (string.Equals(payload.JobType, RemoveJobType, StringComparison.OrdinalIgnoreCase))
            {
                await RemoveCertificateAsync(payload, cancellationToken);
                return;
            }

            var installed = InstallCertificate(payload);
            var duplicateCleanup = RemoveExpiredDuplicateCertificates(installed);
            await _client!.SendResultAsync(jobId, new AgentClient.ResultUpdate
            {
                Status = "DONE",
                Thumbprint = installed.Thumbprint
            }, cancellationToken);
            UpdateStatus(lastJobStatus: "DONE", error: null);
            try
            {
                EnsureKeepUntilCleanupTask(payload);
            }
            catch (Exception ex)
            {
                _logger.Error($"Failed to ensure keep-until cleanup task for job {jobId}", ex);
            }
            var config = _configStore.Load();
            if (config is not null)
            {
                await ReportDuplicateExpiredCleanupAsync(payload, installed, duplicateCleanup, cancellationToken);
                await ReportInstalledCertsAsync(config, cancellationToken, force: true);
            }
        }
        catch (Exception ex)
        {
            _logger.Error($"Job failed for job {jobId}", ex);
            var errorCode = string.Equals(payload.JobType, RemoveJobType, StringComparison.OrdinalIgnoreCase)
                ? "REMOVE_FAILED"
                : "INSTALL_FAILED";
            await ReportFailureAsync(jobId, errorCode, ex.Message, cancellationToken);
            UpdateStatus(lastJobStatus: "FAILED", error: ex.Message);
        }
    }

    private InstalledCertificateResult InstallCertificate(AgentClient.PayloadResponse payload)
    {
        if (string.IsNullOrWhiteSpace(payload.PfxBase64) || payload.Password is null)
        {
            throw new InvalidOperationException("Payload missing certificate data.");
        }

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

        var normalized = NormalizeThumbprint(thumbprint);
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

        return new InstalledCertificateResult(normalized, certificate.Subject ?? string.Empty);
    }

    private async Task RemoveCertificateAsync(
        AgentClient.PayloadResponse payload,
        CancellationToken cancellationToken)
    {
        var targetThumbprint = NormalizeThumbprint(payload.TargetThumbprint);
        if (string.IsNullOrWhiteSpace(targetThumbprint))
        {
            await ReportFailureAsync(payload.JobId, "INVALID_PAYLOAD", "Missing target thumbprint.", cancellationToken);
            UpdateStatus(lastJobStatus: "FAILED", error: "Missing target thumbprint");
            return;
        }

        _logger.Info($"Manual remove requested: {MaskThumbprint(targetThumbprint)}");
        var removedCount = 0;
        using var store = new X509Store(StoreName.My, StoreLocation.CurrentUser);
        store.Open(OpenFlags.ReadWrite);
        var found = store.Certificates.Find(X509FindType.FindByThumbprint, targetThumbprint, false);
        foreach (var cert in found)
        {
            store.Remove(cert);
            removedCount++;
        }

        var dpapiRemoved = RemoveThumbprintFromStore(targetThumbprint);
        _logger.Info($"Manual remove result. Found={found.Count}, Removed={removedCount}, DPAPIEntryRemoved={dpapiRemoved}.");

        if (found.Count == 0 && !dpapiRemoved)
        {
            await ReportFailureAsync(payload.JobId, "NOT_FOUND", "Certificate not found.", cancellationToken);
            UpdateStatus(lastJobStatus: "FAILED", error: "Certificate not found");
        }
        else
        {
            await _client!.SendResultAsync(payload.JobId, new AgentClient.ResultUpdate
            {
                Status = "DONE",
                Thumbprint = targetThumbprint
            }, cancellationToken);
            UpdateStatus(lastJobStatus: "DONE", error: null);
        }

        var config = _configStore.Load();
        if (config is not null)
        {
            await ReportInstalledCertsAsync(config, cancellationToken, force: true);
        }
    }

    private bool RemoveThumbprintFromStore(string thumbprint)
    {
        var stored = _thumbprintsStore.LoadEntries(_configStore.InstalledThumbprintsPath).ToList();
        var normalized = NormalizeThumbprint(thumbprint);
        var before = stored.Count;
        stored = stored
            .Where(entry => !string.Equals(NormalizeThumbprint(entry.Thumbprint), normalized, StringComparison.OrdinalIgnoreCase))
            .ToList();
        if (stored.Count == before)
        {
            return false;
        }

        _thumbprintsStore.SaveEntries(_configStore.InstalledThumbprintsPath, stored);
        _logger.Info($"DPAPI entry removed for thumbprint: {normalized}");
        return true;
    }

    private DuplicateExpiredCleanupResult RemoveExpiredDuplicateCertificates(InstalledCertificateResult installed)
    {
        var entityKey = CertificateEntityKey.ExtractEntityKey(installed.Subject);
        if (string.IsNullOrWhiteSpace(entityKey))
        {
            _logger.Warn(
                $"entity_key_not_found subject={CertificateEntityKey.MaskSubjectForLog(installed.Subject)}");
            return DuplicateExpiredCleanupResult.Empty;
        }

        var entityKeyHash = CertificateEntityKey.HashEntityKey(entityKey);
        var nowUtc = DateTime.UtcNow;
        var removed = new List<string>();
        var failed = new List<string>();
        var skippedRetention = 0;
        var toRemove = new List<string>();

        var entries = _thumbprintsStore.LoadEntries(_configStore.InstalledThumbprintsPath);
        var entryMap = entries
            .Where(entry => !string.IsNullOrWhiteSpace(entry.Thumbprint))
            .GroupBy(entry => NormalizeThumbprint(entry.Thumbprint))
            .ToDictionary(group => group.Key, group => CertificateCleanupService.SelectBestEntry(group));

        using var store = new X509Store(StoreName.My, StoreLocation.CurrentUser);
        store.Open(OpenFlags.ReadWrite);

        foreach (var cert in store.Certificates)
        {
            var thumbprint = NormalizeThumbprint(cert.Thumbprint);
            if (string.IsNullOrWhiteSpace(thumbprint))
            {
                continue;
            }

            if (string.Equals(thumbprint, installed.Thumbprint, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            if (cert.NotAfter.ToUniversalTime() >= nowUtc)
            {
                continue;
            }

            var candidateKey = CertificateEntityKey.ExtractEntityKey(cert.Subject);
            if (string.IsNullOrWhiteSpace(candidateKey))
            {
                continue;
            }

            if (!string.Equals(candidateKey, entityKey, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            if (entryMap.TryGetValue(thumbprint, out var entry) &&
                CertificateCleanupService.ShouldSkipRetention(entry, _logger))
            {
                skippedRetention++;
                continue;
            }

            toRemove.Add(thumbprint);
        }

        foreach (var thumbprint in toRemove.Distinct(StringComparer.OrdinalIgnoreCase))
        {
            try
            {
                var found = store.Certificates.Find(X509FindType.FindByThumbprint, thumbprint, false);
                foreach (var cert in found)
                {
                    store.Remove(cert);
                }
                removed.Add(thumbprint);
                _logger.Info($"Removed expired duplicate cert thumbprint: {thumbprint}");
            }
            catch (Exception ex)
            {
                failed.Add(thumbprint);
                _logger.Error($"Failed to remove expired duplicate cert thumbprint: {thumbprint}", ex);
            }
        }

        _logger.Info(
            $"Expired duplicate cleanup done. EntityKeyHash={entityKeyHash}, Removed={removed.Count}, Failed={failed.Count}, SkippedRetention={skippedRetention}.");

        return new DuplicateExpiredCleanupResult(entityKeyHash, removed, failed, skippedRetention);
    }

    private async Task ReportDuplicateExpiredCleanupAsync(
        AgentClient.PayloadResponse payload,
        InstalledCertificateResult installed,
        DuplicateExpiredCleanupResult cleanupResult,
        CancellationToken cancellationToken)
    {
        if (_client is null)
        {
            _logger.Warn("Expired duplicate cleanup audit skipped: client not initialized.");
            return;
        }

        if (!cleanupResult.HasData)
        {
            return;
        }

        try
        {
            var response = await _client.PostDuplicateExpiredCleanupAsync(new AgentClient.DuplicateExpiredCleanupEvent
            {
                JobId = payload.JobId,
                NewThumbprint = MaskThumbprint(installed.Thumbprint),
                RemovedCount = cleanupResult.RemovedThumbprints.Count,
                RemovedThumbprints = cleanupResult.RemovedThumbprints.Select(MaskThumbprint).ToList(),
                EntityKeyHash = cleanupResult.EntityKeyHash,
                FailedCount = cleanupResult.FailedThumbprints.Count,
                FailedThumbprints = cleanupResult.FailedThumbprints.Select(MaskThumbprint).ToList()
            }, cancellationToken);

            if (!response.IsSuccessStatusCode)
            {
                _logger.Warn($"Expired duplicate cleanup audit failed: {(int)response.StatusCode} {response.ReasonPhrase}");
            }
        }
        catch (Exception ex)
        {
            _logger.Error("Expired duplicate cleanup audit failed with exception.", ex);
        }
    }

    private void EnsureKeepUntilCleanupTask(AgentClient.PayloadResponse payload)
    {
        if (!string.Equals(payload.CleanupMode, "KEEP_UNTIL", StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        if (!payload.KeepUntil.HasValue)
        {
            return;
        }

        _scheduledTaskService.EnsureKeepUntilCleanupTask(payload.KeepUntil.Value, _executablePath);
    }

    private static string NormalizeThumbprint(string? thumbprint)
    {
        return (thumbprint ?? string.Empty).Replace(" ", string.Empty).ToUpperInvariant();
    }

    private static string MaskThumbprint(string? thumbprint)
    {
        var normalized = NormalizeThumbprint(thumbprint);
        if (normalized.Length <= 6)
        {
            return normalized;
        }

        return normalized[^6..];
    }

    private sealed record InstalledCertificateResult(string Thumbprint, string Subject);

    private sealed record DuplicateExpiredCleanupResult(
        string EntityKeyHash,
        IReadOnlyList<string> RemovedThumbprints,
        IReadOnlyList<string> FailedThumbprints,
        int SkippedRetentionCount)
    {
        public static DuplicateExpiredCleanupResult Empty => new(string.Empty, Array.Empty<string>(), Array.Empty<string>(), 0);

        public bool HasData =>
            RemovedThumbprints.Count > 0 || FailedThumbprints.Count > 0;
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
