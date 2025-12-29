using System.Security.Cryptography;
using System.Text;

namespace Certhub.Agent.Services;

public sealed class DpapiStore
{
    private readonly Logger _logger;

    public DpapiStore(Logger logger)
    {
        _logger = logger;
    }

    public void SaveString(string path, string value)
    {
        SaveBytes(path, Encoding.UTF8.GetBytes(value));
    }

    public string? LoadString(string path)
    {
        var data = LoadBytes(path);
        if (data is null)
        {
            return null;
        }

        return Encoding.UTF8.GetString(data);
    }

    public void SaveBytes(string path, byte[] data)
    {
        try
        {
            var directory = Path.GetDirectoryName(path);
            if (!string.IsNullOrWhiteSpace(directory))
            {
                Directory.CreateDirectory(directory);
            }

            var protectedBytes = ProtectedData.Protect(data, null, DataProtectionScope.CurrentUser);
            File.WriteAllBytes(path, protectedBytes);
        }
        catch (Exception ex)
        {
            _logger.Error($"Failed to protect data for {path}", ex);
            throw;
        }
    }

    public byte[]? LoadBytes(string path)
    {
        if (!File.Exists(path))
        {
            return null;
        }

        try
        {
            var protectedBytes = File.ReadAllBytes(path);
            return ProtectedData.Unprotect(protectedBytes, null, DataProtectionScope.CurrentUser);
        }
        catch (Exception ex)
        {
            _logger.Error($"Failed to unprotect data for {path}", ex);
            return null;
        }
    }
}
