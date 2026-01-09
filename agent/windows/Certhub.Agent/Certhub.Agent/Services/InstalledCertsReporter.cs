using System.Linq;
using System.Security.Cryptography.X509Certificates;

namespace Certhub.Agent.Services;

public sealed class InstalledCertsReporter
{
    private readonly AgentConfigStore _configStore;
    private readonly InstalledThumbprintsStore _thumbprintsStore;
    private readonly Logger _logger;

    public InstalledCertsReporter(
        AgentConfigStore configStore,
        InstalledThumbprintsStore thumbprintsStore,
        Logger logger)
    {
        _configStore = configStore;
        _thumbprintsStore = thumbprintsStore;
        _logger = logger;
    }

    public List<AgentClient.InstalledCertReportItem> BuildSnapshot()
    {
        var entries = _thumbprintsStore.LoadEntries(_configStore.InstalledThumbprintsPath);
        var entryMap = entries
            .Where(entry => !string.IsNullOrWhiteSpace(entry.Thumbprint))
            .GroupBy(entry => NormalizeThumbprint(entry.Thumbprint))
            .ToDictionary(group => group.Key, group => group.OrderByDescending(e => e.InstalledAt ?? DateTimeOffset.MinValue).First());

        using var store = new X509Store(StoreName.My, StoreLocation.CurrentUser);
        store.Open(OpenFlags.ReadOnly);

        var results = new List<AgentClient.InstalledCertReportItem>();
        foreach (var cert in store.Certificates)
        {
            var thumbprint = NormalizeThumbprint(cert.Thumbprint);
            if (string.IsNullOrWhiteSpace(thumbprint))
            {
                continue;
            }

            if (entryMap.TryGetValue(thumbprint, out var entry))
            {
                results.Add(new AgentClient.InstalledCertReportItem
                {
                    Thumbprint = thumbprint,
                    Subject = cert.Subject,
                    Issuer = cert.Issuer,
                    Serial = cert.SerialNumber,
                    NotBefore = cert.NotBefore.ToUniversalTime(),
                    NotAfter = cert.NotAfter.ToUniversalTime(),
                    InstalledViaAgent = true,
                    CleanupMode = entry.CleanupMode,
                    KeepUntil = entry.KeepUntil,
                    KeepReason = entry.KeepReason,
                    JobId = entry.JobId,
                    InstalledAt = entry.InstalledAt
                });
            }
            else
            {
                results.Add(new AgentClient.InstalledCertReportItem
                {
                    Thumbprint = thumbprint,
                    Subject = cert.Subject,
                    Issuer = cert.Issuer,
                    Serial = cert.SerialNumber,
                    NotBefore = cert.NotBefore.ToUniversalTime(),
                    NotAfter = cert.NotAfter.ToUniversalTime(),
                    InstalledViaAgent = false
                });
            }
        }

        return results;
    }

    public async Task<bool> SendSnapshotAsync(
        AgentClient client,
        string deviceId,
        CancellationToken cancellationToken)
    {
        try
        {
            var items = BuildSnapshot();
            var response = await client.PostInstalledCertsReportAsync(new AgentClient.InstalledCertReportRequest
            {
                DeviceId = deviceId,
                Items = items
            }, cancellationToken);

            if (!response.IsSuccessStatusCode)
            {
                _logger.Warn($"Installed certs report failed: {(int)response.StatusCode} {response.ReasonPhrase}");
                return false;
            }

            _logger.Info($"Installed certs report sent. Count={items.Count}.");
            return true;
        }
        catch (Exception ex)
        {
            _logger.Error("Installed certs report failed with exception.", ex);
            return false;
        }
    }

    private static string NormalizeThumbprint(string? thumbprint)
    {
        return (thumbprint ?? string.Empty).Replace(" ", string.Empty).ToUpperInvariant();
    }
}
