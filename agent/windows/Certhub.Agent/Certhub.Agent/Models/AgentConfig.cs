namespace Certhub.Agent.Models;

public sealed class AgentConfig
{
    public string ApiBaseUrl { get; set; } = string.Empty;
    public string DeviceId { get; set; } = string.Empty;
    public string? PortalUrl { get; set; }
    public int PollingIntervalSeconds { get; set; } = 30;

    public bool IsValid() =>
        !string.IsNullOrWhiteSpace(ApiBaseUrl)
        && !string.IsNullOrWhiteSpace(DeviceId)
        && PollingIntervalSeconds > 0;
}
