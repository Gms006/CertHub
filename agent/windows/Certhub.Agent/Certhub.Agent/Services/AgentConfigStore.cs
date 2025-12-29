using System.Text.Json;
using Certhub.Agent.Models;

namespace Certhub.Agent.Services;

public sealed class AgentConfigStore
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = true
    };

    private readonly Logger _logger;
    private readonly string _baseDir;

    public AgentConfigStore(Logger logger)
    {
        _logger = logger;
        _baseDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "CertHubAgent");
    }

    public string BaseDirectory => _baseDir;
    public string ConfigPath => Path.Combine(_baseDir, "config.json");
    public string SecretsPath => Path.Combine(_baseDir, "secrets.dat");
    public string InstalledThumbprintsPath => Path.Combine(_baseDir, "installed_thumbprints.json");

    public AgentConfig? Load()
    {
        if (!File.Exists(ConfigPath))
        {
            return null;
        }

        try
        {
            var json = File.ReadAllText(ConfigPath);
            var config = JsonSerializer.Deserialize<AgentConfig>(json, JsonOptions);
            return config;
        }
        catch (Exception ex)
        {
            _logger.Error("Failed to load config.json", ex);
            return null;
        }
    }

    public void Save(AgentConfig config)
    {
        Directory.CreateDirectory(_baseDir);
        var json = JsonSerializer.Serialize(config, JsonOptions);
        File.WriteAllText(ConfigPath, json);
        _logger.Info("Config saved.");
    }
}
