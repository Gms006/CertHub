using Certhub.Agent.Models;

namespace Certhub.Agent.Services;

public static class PortalUrlHelper
{
    public static string? ResolvePortalUrl(AgentConfig? config)
    {
        if (config is null)
        {
            return null;
        }

        if (!string.IsNullOrWhiteSpace(config.PortalUrl))
        {
            return config.PortalUrl;
        }

        if (string.IsNullOrWhiteSpace(config.ApiBaseUrl))
        {
            return null;
        }

        if (!Uri.TryCreate(config.ApiBaseUrl, UriKind.Absolute, out var apiUri))
        {
            return null;
        }

        var baseUri = apiUri.AbsoluteUri.TrimEnd('/');
        if (baseUri.EndsWith("/api/v1", StringComparison.OrdinalIgnoreCase))
        {
            baseUri = baseUri[..^"/api/v1".Length];
        }

        return baseUri;
    }
}
