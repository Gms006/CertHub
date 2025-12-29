namespace Certhub.Agent.Models;

public sealed class AgentConfig
{
    public const int DefaultPollingIntervalSecondsIdle = 30;
    public const int DefaultPollingIntervalSecondsActive = 5;

    public string ApiBaseUrl { get; set; } = string.Empty;
    public string DeviceId { get; set; } = string.Empty;
    public string? PortalUrl { get; set; }
    public int PollingIntervalSecondsIdle { get; set; } = DefaultPollingIntervalSecondsIdle;
    public int PollingIntervalSecondsActive { get; set; } = DefaultPollingIntervalSecondsActive;
    public DateTime? LastCleanupLocalDate { get; set; }

    public bool IsValid() =>
        !string.IsNullOrWhiteSpace(ApiBaseUrl)
        && !string.IsNullOrWhiteSpace(DeviceId)
        && PollingIntervalSecondsIdle > 0
        && PollingIntervalSecondsActive > 0;
}
