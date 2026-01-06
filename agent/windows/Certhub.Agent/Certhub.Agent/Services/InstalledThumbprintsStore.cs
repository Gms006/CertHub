using System;
using System.Linq;
using System.Text.Json;

namespace Certhub.Agent.Services;

public sealed class InstalledThumbprintsStore
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = true,
        PropertyNameCaseInsensitive = true
    };

    private readonly DpapiStore _dpapiStore;
    private readonly Logger _logger;

    public InstalledThumbprintsStore(DpapiStore dpapiStore, Logger logger)
    {
        _dpapiStore = dpapiStore;
        _logger = logger;
    }

    public IReadOnlyCollection<InstalledThumbprintEntry> LoadEntries(string path)
    {
        var data = _dpapiStore.LoadBytes(path);
        if (data is null)
        {
            return Array.Empty<InstalledThumbprintEntry>();
        }

        try
        {
            var json = System.Text.Encoding.UTF8.GetString(data);
            try
            {
                var entries = JsonSerializer.Deserialize<List<InstalledThumbprintEntry>>(json, JsonOptions);
                if (entries is not null)
                {
                    return entries;
                }
            }
            catch (Exception)
            {
                // fall back to legacy format
            }

            var legacy = JsonSerializer.Deserialize<List<string>>(json, JsonOptions);
            if (legacy is null)
            {
                return Array.Empty<InstalledThumbprintEntry>();
            }

            return legacy
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .Select(value => new InstalledThumbprintEntry
                {
                    Thumbprint = value,
                    CleanupMode = "DEFAULT"
                })
                .ToList();
        }
        catch (Exception ex)
        {
            _logger.Error("Failed to decode installed thumbprints", ex);
            return Array.Empty<InstalledThumbprintEntry>();
        }
    }

    public void SaveEntries(string path, IEnumerable<InstalledThumbprintEntry> entries)
    {
        var json = JsonSerializer.Serialize(entries, JsonOptions);
        _dpapiStore.SaveBytes(path, System.Text.Encoding.UTF8.GetBytes(json));
        _logger.Info("Installed thumbprints updated.");
    }
}

public sealed class InstalledThumbprintEntry
{
    public string Thumbprint { get; set; } = string.Empty;
    public Guid? JobId { get; set; }
    public string CleanupMode { get; set; } = "DEFAULT";
    public DateTimeOffset? KeepUntil { get; set; }
    public string? KeepReason { get; set; }
    public DateTimeOffset? InstalledAt { get; set; }
}
