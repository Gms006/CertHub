using System.Text.Json;

namespace Certhub.Agent.Services;

public sealed class InstalledThumbprintsStore
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = true
    };

    private readonly DpapiStore _dpapiStore;
    private readonly Logger _logger;

    public InstalledThumbprintsStore(DpapiStore dpapiStore, Logger logger)
    {
        _dpapiStore = dpapiStore;
        _logger = logger;
    }

    public IReadOnlyCollection<string> Load(string path)
    {
        var data = _dpapiStore.LoadBytes(path);
        if (data is null)
        {
            return Array.Empty<string>();
        }

        try
        {
            var json = System.Text.Encoding.UTF8.GetString(data);
            var list = JsonSerializer.Deserialize<List<string>>(json, JsonOptions);
            return list ?? new List<string>();
        }
        catch (Exception ex)
        {
            _logger.Error("Failed to decode installed thumbprints", ex);
            return Array.Empty<string>();
        }
    }

    public void Save(string path, IEnumerable<string> thumbprints)
    {
        var json = JsonSerializer.Serialize(thumbprints, JsonOptions);
        _dpapiStore.SaveBytes(path, System.Text.Encoding.UTF8.GetBytes(json));
        _logger.Info("Installed thumbprints updated.");
    }
}
