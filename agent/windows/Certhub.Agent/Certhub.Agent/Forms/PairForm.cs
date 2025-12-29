using Certhub.Agent.Models;

namespace Certhub.Agent.Forms;

public sealed class PairForm : Form
{
    private readonly TextBox _apiBaseTextBox = new();
    private readonly TextBox _deviceIdTextBox = new();
    private readonly TextBox _deviceTokenTextBox = new();
    private readonly TextBox _portalUrlTextBox = new();
    private readonly NumericUpDown _pollingIdleIntervalInput = new();
    private readonly NumericUpDown _pollingActiveIntervalInput = new();
    private readonly CheckBox _startWithWindows = new();

    public PairForm(AgentConfig? config, string? currentToken, bool startWithWindows)
    {
        Text = "Pair Device";
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        Width = 560;
        Height = 390;

        _deviceTokenTextBox.UseSystemPasswordChar = true;
        _pollingIdleIntervalInput.Minimum = 5;
        _pollingIdleIntervalInput.Maximum = 3600;
        _pollingIdleIntervalInput.Value = config?.PollingIntervalSecondsIdle ?? 30;
        _pollingActiveIntervalInput.Minimum = 2;
        _pollingActiveIntervalInput.Maximum = 3600;
        _pollingActiveIntervalInput.Value = config?.PollingIntervalSecondsActive ?? 5;
        _startWithWindows.Text = "Iniciar com Windows";
        _startWithWindows.Checked = startWithWindows;

        _apiBaseTextBox.Text = config?.ApiBaseUrl ?? string.Empty;
        _deviceIdTextBox.Text = config?.DeviceId ?? string.Empty;
        _portalUrlTextBox.Text = config?.PortalUrl ?? string.Empty;
        _deviceTokenTextBox.Text = currentToken ?? string.Empty;

        var layout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 2,
            RowCount = 7,
            Padding = new Padding(12)
        };

        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 35));
        layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 65));

        AddRow(layout, 0, "API Base URL (ex: http://localhost:8000/api/v1)", _apiBaseTextBox);
        AddRow(layout, 1, "Device ID", _deviceIdTextBox);
        AddRow(layout, 2, "Device Token", _deviceTokenTextBox);
        AddRow(layout, 3, "Portal URL (opcional)", _portalUrlTextBox);
        AddRow(layout, 4, "Polling idle (segundos)", _pollingIdleIntervalInput);
        AddRow(layout, 5, "Polling ativo (segundos)", _pollingActiveIntervalInput);

        layout.Controls.Add(_startWithWindows, 1, 6);

        var buttonPanel = new FlowLayoutPanel
        {
            FlowDirection = FlowDirection.RightToLeft,
            Dock = DockStyle.Bottom,
            Padding = new Padding(12)
        };

        var saveButton = new Button { Text = "Salvar", DialogResult = DialogResult.OK };
        saveButton.Click += (_, _) => OnSave();
        var cancelButton = new Button { Text = "Cancelar", DialogResult = DialogResult.Cancel };
        buttonPanel.Controls.Add(saveButton);
        buttonPanel.Controls.Add(cancelButton);

        Controls.Add(layout);
        Controls.Add(buttonPanel);
    }

    public AgentConfig? ResultConfig { get; private set; }
    public string? ResultDeviceToken { get; private set; }
    public bool StartWithWindows => _startWithWindows.Checked;

    private void OnSave()
    {
        if (string.IsNullOrWhiteSpace(_apiBaseTextBox.Text)
            || string.IsNullOrWhiteSpace(_deviceIdTextBox.Text)
            || string.IsNullOrWhiteSpace(_deviceTokenTextBox.Text))
        {
            MessageBox.Show("Preencha API Base URL, Device ID e Device Token.", "CertHub Agent");
            DialogResult = DialogResult.None;
            return;
        }

        ResultConfig = new AgentConfig
        {
            ApiBaseUrl = _apiBaseTextBox.Text.Trim(),
            DeviceId = _deviceIdTextBox.Text.Trim(),
            PortalUrl = string.IsNullOrWhiteSpace(_portalUrlTextBox.Text)
                ? null
                : _portalUrlTextBox.Text.Trim(),
            PollingIntervalSecondsIdle = (int)_pollingIdleIntervalInput.Value,
            PollingIntervalSecondsActive = (int)_pollingActiveIntervalInput.Value
        };
        ResultDeviceToken = _deviceTokenTextBox.Text.Trim();
    }

    private static void AddRow(TableLayoutPanel layout, int row, string labelText, Control input)
    {
        var label = new Label { Text = labelText, AutoSize = true, Anchor = AnchorStyles.Left };
        input.Dock = DockStyle.Fill;
        layout.Controls.Add(label, 0, row);
        layout.Controls.Add(input, 1, row);
    }
}
