using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Certhub.Agent.Services;

public sealed class AgentClient
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    private readonly HttpClient _httpClient;
    private readonly Logger _logger;
    private string? _accessToken;
    private string? _deviceId;
    private string? _deviceToken;

    public AgentClient(string baseUrl, Logger logger)
    {
        _httpClient = new HttpClient
        {
            BaseAddress = new Uri(baseUrl.TrimEnd('/') + "/")
        };
        _logger = logger;
    }

    public void UpdateCredentials(string deviceId, string deviceToken)
    {
        _deviceId = deviceId;
        _deviceToken = deviceToken;
    }

    public async Task AuthenticateAsync(string deviceId, string deviceToken, CancellationToken cancellationToken)
    {
        var payload = new { device_id = deviceId, device_token = deviceToken };
        var response = await _httpClient.PostAsync(
            "agent/auth",
            new StringContent(JsonSerializer.Serialize(payload, JsonOptions), Encoding.UTF8, "application/json"),
            cancellationToken);

        if (!response.IsSuccessStatusCode)
        {
            throw new InvalidOperationException($"Auth failed: {(int)response.StatusCode} {response.ReasonPhrase}");
        }

        var body = await response.Content.ReadAsStringAsync(cancellationToken);
        var auth = JsonSerializer.Deserialize<AuthResponse>(body, JsonOptions);
        if (auth?.AccessToken is null)
        {
            throw new InvalidOperationException("Auth response missing access token");
        }

        _accessToken = auth.AccessToken;
        _httpClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", _accessToken);
    }

    public async Task<HttpResponseMessage> PostHeartbeatAsync(string agentVersion, CancellationToken cancellationToken)
    {
        var payload = new { agent_version = agentVersion };
        return await PostWithAuthRetryAsync(
            "agent/heartbeat",
            new StringContent(JsonSerializer.Serialize(payload, JsonOptions), Encoding.UTF8, "application/json"),
            cancellationToken);
    }

    public async Task<List<InstallJob>> GetJobsAsync(CancellationToken cancellationToken)
    {
        var response = await SendWithAuthRetryAsync(() => new HttpRequestMessage(HttpMethod.Get, "agent/jobs"), cancellationToken);
        var body = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            throw new InvalidOperationException($"Jobs request failed: {(int)response.StatusCode} {response.ReasonPhrase}");
        }

        var jobs = JsonSerializer.Deserialize<List<InstallJob>>(body, JsonOptions);
        return jobs ?? new List<InstallJob>();
    }

    public async Task ClaimJobAsync(Guid jobId, CancellationToken cancellationToken)
    {
        var response = await PostWithAuthRetryAsync($"agent/jobs/{jobId}/claim", new StringContent("{}", Encoding.UTF8, "application/json"), cancellationToken);
        if (response.StatusCode == HttpStatusCode.Conflict)
        {
            throw new InvalidOperationException("Job already claimed");
        }
        if (!response.IsSuccessStatusCode)
        {
            throw new InvalidOperationException($"Claim failed: {(int)response.StatusCode} {response.ReasonPhrase}");
        }
    }

    public async Task<PayloadResponse> GetPayloadAsync(Guid jobId, CancellationToken cancellationToken)
    {
        var response = await SendWithAuthRetryAsync(() => new HttpRequestMessage(HttpMethod.Get, $"agent/jobs/{jobId}/payload"), cancellationToken);
        var body = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            throw new InvalidOperationException($"Payload request failed: {(int)response.StatusCode} {response.ReasonPhrase}");
        }

        var payload = JsonSerializer.Deserialize<PayloadResponse>(body, JsonOptions);
        if (payload is null)
        {
            throw new InvalidOperationException("Payload response invalid");
        }

        return payload;
    }

    public async Task SendResultAsync(Guid jobId, ResultUpdate update, CancellationToken cancellationToken)
    {
        var response = await PostWithAuthRetryAsync(
            $"agent/jobs/{jobId}/result",
            new StringContent(JsonSerializer.Serialize(update, JsonOptions), Encoding.UTF8, "application/json"),
            cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            _logger.Warn($"Result update failed: {(int)response.StatusCode} {response.ReasonPhrase}");
        }
    }

    private async Task<HttpResponseMessage> PostWithAuthRetryAsync(string path, HttpContent content, CancellationToken cancellationToken)
    {
        return await SendWithAuthRetryAsync(() => new HttpRequestMessage(HttpMethod.Post, path) { Content = content }, cancellationToken);
    }

    private async Task<HttpResponseMessage> SendWithAuthRetryAsync(Func<HttpRequestMessage> requestFactory, CancellationToken cancellationToken)
    {
        var response = await _httpClient.SendAsync(requestFactory(), cancellationToken);
        if (response.StatusCode != HttpStatusCode.Unauthorized)
        {
            return response;
        }

        _accessToken = null;
        if (string.IsNullOrWhiteSpace(_deviceId) || string.IsNullOrWhiteSpace(_deviceToken))
        {
            return response;
        }

        _logger.Warn("Bearer token expired. Re-authenticating.");
        await AuthenticateAsync(_deviceId, _deviceToken, cancellationToken);
        return await _httpClient.SendAsync(requestFactory(), cancellationToken);
    }

    private sealed class AuthResponse
    {
        [JsonPropertyName("access_token")]
        public string? AccessToken { get; set; }
    }

    public sealed class InstallJob
    {
        [JsonPropertyName("id")]
        public Guid Id { get; set; }

        [JsonPropertyName("status")]
        public string Status { get; set; } = string.Empty;
    }

    public sealed class PayloadResponse
    {
        [JsonPropertyName("job_id")]
        public Guid JobId { get; set; }

        [JsonPropertyName("cert_id")]
        public Guid CertId { get; set; }

        [JsonPropertyName("pfx_base64")]
        public string PfxBase64 { get; set; } = string.Empty;

        [JsonPropertyName("password")]
        public string Password { get; set; } = string.Empty;

        [JsonPropertyName("source_path")]
        public string SourcePath { get; set; } = string.Empty;

        [JsonPropertyName("generated_at")]
        public DateTimeOffset GeneratedAt { get; set; }
    }

    public sealed class ResultUpdate
    {
        [JsonPropertyName("status")]
        public string Status { get; set; } = string.Empty;

        [JsonPropertyName("thumbprint")]
        public string? Thumbprint { get; set; }

        [JsonPropertyName("error_code")]
        public string? ErrorCode { get; set; }

        [JsonPropertyName("error_message")]
        public string? ErrorMessage { get; set; }
    }
}
