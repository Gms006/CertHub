namespace Certhub.Agent.Models;

public sealed class AgentStatus
{
    public DateTimeOffset? LastHeartbeatAt { get; set; }
    public string? LastJobId { get; set; }
    public string? LastJobStatus { get; set; }
    public int? PollingIntervalSeconds { get; set; }
    public string? PollingMode { get; set; }
    public string? LastError { get; set; }
}
