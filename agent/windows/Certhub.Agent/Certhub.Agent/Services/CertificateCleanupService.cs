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
        var storedThumbprints = _thumbprintsStore.Load(_configStore.InstalledThumbprintsPath).ToList();
        var normalizedThumbprints = storedThumbprints
            .Select(t => t.Replace(" ", string.Empty).ToUpperInvariant())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();

        _logger.Info($"Starting cleanup ({mode}). Total stored thumbprints: {normalizedThumbprints.Count}.");

        var removed = new List<string>();
        var failed = new List<string>();

        using var store = new X509Store(StoreName.My, StoreLocation.CurrentUser);
        store.Open(OpenFlags.ReadWrite);

        foreach (var thumbprint in normalizedThumbprints)
        {
            try
            {
                var existing = store.Certificates.Find(X509FindType.FindByThumbprint, thumbprint, false);
                if (existing.Count == 0)
                {
                    removed.Add(thumbprint);
                    _logger.Warn($"Thumbprint not found in store (already removed): {thumbprint}");
                    continue;
                }

                foreach (var cert in existing)
                {
                    store.Remove(cert);
                }

                removed.Add(thumbprint);
                _logger.Info($"Removed certificate thumbprint: {thumbprint}");
            }
            catch (Exception ex)
            {
                failed.Add(thumbprint);
                _logger.Error($"Failed to remove certificate thumbprint: {thumbprint}", ex);
            }
        }

        var remaining = normalizedThumbprints
            .Where(tp => failed.Contains(tp, StringComparer.OrdinalIgnoreCase))
            .ToList();

        _thumbprintsStore.Save(_configStore.InstalledThumbprintsPath, remaining);

        _logger.Info(
            $"Cleanup finished. Total: {normalizedThumbprints.Count}, Removed: {removed.Count}, Failed: {failed.Count}.");

        return new CleanupResult(
            mode,
            DateTimeOffset.Now,
            normalizedThumbprints.Count,
            removed,
            failed);
    }
}

public enum CleanupMode
{
    Scheduled,
    Fallback,
    Manual
}

public sealed record CleanupResult(
    CleanupMode Mode,
    DateTimeOffset RanAtLocal,
    int TotalThumbprints,
    IReadOnlyList<string> RemovedThumbprints,
    IReadOnlyList<string> FailedThumbprints)
{
    public int RemovedCount => RemovedThumbprints.Count;

    public int FailedCount => FailedThumbprints.Count;

    public bool Success => FailedCount == 0;
}
