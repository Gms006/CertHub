using Certhub.Agent.Models;

namespace Certhub.Agent.Forms;

public sealed class StatusForm : Form
{
    private readonly Label _apiLabel = new();
    private readonly Label _deviceLabel = new();
    private readonly Label _heartbeatLabel = new();
    private readonly Label _jobLabel = new();
    private readonly Label _pollingLabel = new();
    private readonly Label _errorLabel = new();

    public StatusForm()
    {
        Text = "CertHub Agent Status";
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        Width = 520;
        Height = 290;

        var table = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 2,
            RowCount = 6,
            Padding = new Padding(12),
            AutoSize = true
        };

        table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 35));
        table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 65));

        AddRow(table, 0, "API Base:", _apiLabel);
        AddRow(table, 1, "Device ID:", _deviceLabel);
        AddRow(table, 2, "Last Heartbeat:", _heartbeatLabel);
        AddRow(table, 3, "Last Job:", _jobLabel);
        AddRow(table, 4, "Polling:", _pollingLabel);
        AddRow(table, 5, "Last Error:", _errorLabel);

        Controls.Add(table);
    }

    public void UpdateStatus(AgentStatus status, AgentConfig? config)
    {
        _apiLabel.Text = config?.ApiBaseUrl ?? "Not configured";
        _deviceLabel.Text = config?.DeviceId ?? "Not configured";
        _heartbeatLabel.Text = status.LastHeartbeatAt?.LocalDateTime.ToString("g") ?? "-";
        _jobLabel.Text = string.IsNullOrWhiteSpace(status.LastJobId)
            ? "-"
            : $"{status.LastJobStatus} ({status.LastJobId})";
        _pollingLabel.Text = status.PollingIntervalSeconds is null
            ? "-"
            : $"{status.PollingIntervalSeconds}s ({status.PollingMode ?? "idle"})";
        _errorLabel.Text = status.LastError ?? "-";
    }

    private static void AddRow(TableLayoutPanel table, int row, string labelText, Label valueLabel)
    {
        var label = new Label { Text = labelText, AutoSize = true, Anchor = AnchorStyles.Left };
        valueLabel.AutoSize = true;
        valueLabel.Anchor = AnchorStyles.Left;
        table.Controls.Add(label, 0, row);
        table.Controls.Add(valueLabel, 1, row);
    }
}
