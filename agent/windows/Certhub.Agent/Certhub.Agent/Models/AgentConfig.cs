namespace Certhub.Agent.Models;

public sealed class AgentConfig
{
    public string ApiBaseUrl { get; set; } = string.Empty;
    public string DeviceId { get; set; } = string.Empty;
    public string? PortalUrl { get; set; }
    public int PollingIntervalSecondsIdle { get; set; } = 30;
    public int PollingIntervalSecondsActive { get; set; } = 5;

    public bool IsValid() =>
        !string.IsNullOrWhiteSpace(ApiBaseUrl)
        && !string.IsNullOrWhiteSpace(DeviceId)
        && PollingIntervalSecondsIdle > 0
        && PollingIntervalSecondsActive > 0;
}
