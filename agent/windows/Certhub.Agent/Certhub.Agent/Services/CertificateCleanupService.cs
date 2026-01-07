using System.Security.Cryptography.X509Certificates;

namespace Certhub.Agent.Services;

public sealed class CertificateCleanupService
{
    private readonly AgentConfigStore _configStore;
    private readonly InstalledThumbprintsStore _thumbprintsStore;
    private readonly Logger _logger;

    public CertificateCleanupService(
        AgentConfigStore configStore,
        InstalledThumbprintsStore thumbprintsStore,
        Logger logger)
    {
        _configStore = configStore;
        _thumbprintsStore = thumbprintsStore;
        _logger = logger;
    }

    public CleanupResult Run(CleanupMode mode)
    {
        var entries = _thumbprintsStore.LoadEntries(_configStore.InstalledThumbprintsPath).ToList();
        var normalizedEntries = entries
            .Where(entry => !string.IsNullOrWhiteSpace(entry.Thumbprint))
            .GroupBy(entry => entry.Thumbprint.Replace(" ", string.Empty).ToUpperInvariant())
            .Select(group =>
            {
                var entry = SelectBestEntry(group);
                entry.Thumbprint = group.Key;
                return entry;
            })
            .ToList();

        _logger.Info($"Starting cleanup ({mode}). Total stored thumbprints: {normalizedEntries.Count}.");

        var removed = new List<string>();
        var failed = new List<string>();
        var skipped = new List<string>();

        using var store = new X509Store(StoreName.My, StoreLocation.CurrentUser);
        store.Open(OpenFlags.ReadWrite);

        foreach (var entry in normalizedEntries)
        {
            if (ShouldSkipRetention(entry, mode, _logger))
            {
                skipped.Add(entry.Thumbprint);
                continue;
            }

            try
            {
                var existing = store.Certificates.Find(X509FindType.FindByThumbprint, entry.Thumbprint, false);
                if (existing.Count == 0)
                {
                    removed.Add(entry.Thumbprint);
                    _logger.Warn($"Thumbprint not found in store (already removed): {entry.Thumbprint}");
                    continue;
                }

                foreach (var cert in existing)
                {
                    store.Remove(cert);
                }

                removed.Add(entry.Thumbprint);
                _logger.Info($"Removed certificate thumbprint: {entry.Thumbprint}");
            }
            catch (Exception ex)
            {
                failed.Add(entry.Thumbprint);
                _logger.Error($"Failed to remove certificate thumbprint: {entry.Thumbprint}", ex);
            }
        }

        var remaining = normalizedEntries
            .Where(entry =>
                failed.Contains(entry.Thumbprint, StringComparer.OrdinalIgnoreCase) ||
                skipped.Contains(entry.Thumbprint, StringComparer.OrdinalIgnoreCase))
            .ToList();

        _thumbprintsStore.SaveEntries(_configStore.InstalledThumbprintsPath, remaining);

        _logger.Info(
            $"Cleanup finished. Total: {normalizedEntries.Count}, Removed: {removed.Count}, Failed: {failed.Count}, Skipped: {skipped.Count}.");

        return new CleanupResult(
            mode,
            DateTimeOffset.Now,
            normalizedEntries.Count,
            removed,
            failed,
            skipped);
    }

    private static bool ShouldSkipRetention(
        InstalledThumbprintEntry entry,
        CleanupMode cleanupMode,
        Logger logger)
    {
        var entryMode = entry.CleanupMode?.ToUpperInvariant() ?? "DEFAULT";
        if (entryMode == "EXEMPT")
        {
            return true;
        }

        if (cleanupMode == CleanupMode.KeepUntil && entryMode != "KEEP_UNTIL")
        {
            return true;
        }

        if (entryMode == "KEEP_UNTIL")
        {
            if (!entry.KeepUntil.HasValue)
            {
                logger.Warn(
                    $"Retention missing keep_until value (KEEP_UNTIL). Skipping removal. Thumbprint={entry.Thumbprint}, CleanupMode={entry.CleanupMode}.");
                return true;
            }

            var nowUtc = DateTimeOffset.UtcNow;
            var keepUntilUtc = entry.KeepUntil.Value.ToUniversalTime();
            var keepUntilLocal = entry.KeepUntil.Value.ToLocalTime();
            if (nowUtc < keepUntilUtc)
            {
                logger.Info(
                    $"Retention active (KEEP_UNTIL). Thumbprint={entry.Thumbprint}, CleanupMode={entry.CleanupMode}, KeepUntilUtc={keepUntilUtc:O}, KeepUntilLocal={keepUntilLocal:O}, NowUtc={nowUtc:O}.");
                return true;
            }

            logger.Info(
                $"Retention expired (KEEP_UNTIL). Eligible for removal. Thumbprint={entry.Thumbprint}, CleanupMode={entry.CleanupMode}, KeepUntilUtc={keepUntilUtc:O}, KeepUntilLocal={keepUntilLocal:O}, NowUtc={nowUtc:O}.");
        }

        return false;
    }

    private static InstalledThumbprintEntry SelectBestEntry(IEnumerable<InstalledThumbprintEntry> entries)
    {
        var list = entries.ToList();
        var exempt = list
            .Where(entry => string.Equals(entry.CleanupMode, "EXEMPT", StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(entry => entry.InstalledAt ?? DateTimeOffset.MinValue)
            .FirstOrDefault();
        if (exempt is not null)
        {
            return exempt;
        }

        var keepUntil = list
            .Where(entry => string.Equals(entry.CleanupMode, "KEEP_UNTIL", StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(entry => entry.KeepUntil ?? DateTimeOffset.MinValue)
            .ThenByDescending(entry => entry.InstalledAt ?? DateTimeOffset.MinValue)
            .FirstOrDefault();
        if (keepUntil is not null)
        {
            return keepUntil;
        }

        return list
            .OrderByDescending(entry => entry.InstalledAt ?? DateTimeOffset.MinValue)
            .First();
    }
}

public enum CleanupMode
{
    Scheduled,
    Fallback,
    Manual,
    KeepUntil
}

public sealed record CleanupResult(
    CleanupMode Mode,
    DateTimeOffset RanAtLocal,
    int TotalThumbprints,
    IReadOnlyList<string> RemovedThumbprints,
    IReadOnlyList<string> FailedThumbprints,
    IReadOnlyList<string> SkippedThumbprints)
{
    public int RemovedCount => RemovedThumbprints.Count;

    public int FailedCount => FailedThumbprints.Count;

    public int SkippedCount => SkippedThumbprints.Count;

    public bool Success => FailedCount == 0;
}
