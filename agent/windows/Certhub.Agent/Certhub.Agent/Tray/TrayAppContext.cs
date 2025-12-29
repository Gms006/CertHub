using System.Diagnostics;
using Certhub.Agent.Forms;
using Certhub.Agent.Models;
using Certhub.Agent.Services;

namespace Certhub.Agent.Tray;

public sealed class TrayAppContext : ApplicationContext
{
    private readonly AgentConfigStore _configStore;
    private readonly DpapiStore _dpapiStore;
    private readonly AgentLoop _agentLoop;
    private readonly Logger _logger;
    private readonly NotifyIcon _notifyIcon;
    private StatusForm? _statusForm;

    public TrayAppContext(
        AgentConfigStore configStore,
        DpapiStore dpapiStore,
        AgentLoop agentLoop,
        Logger logger)
    {
        _configStore = configStore;
        _dpapiStore = dpapiStore;
        _agentLoop = agentLoop;
        _logger = logger;

        _notifyIcon = new NotifyIcon
        {
            Icon = SystemIcons.Application,
            Text = "CertHub Agent",
            Visible = true,
            ContextMenuStrip = BuildMenu()
        };
        _notifyIcon.DoubleClick += (_, _) => ShowStatus();

        _agentLoop.StatusChanged += () => _statusForm?.UpdateStatus(_agentLoop.Status, LoadConfig());

        var config = LoadConfig();
        if (config is not null && config.IsValid())
        {
            var deviceToken = _dpapiStore.LoadString(_configStore.SecretsPath);
            if (!string.IsNullOrWhiteSpace(deviceToken))
            {
                _agentLoop.Start();
            }
        }
    }

    private ContextMenuStrip BuildMenu()
    {
        var menu = new ContextMenuStrip();
        menu.Items.Add("Status", null, (_, _) => ShowStatus());
        menu.Items.Add("Pair device", null, (_, _) => ShowPairing());
        menu.Items.Add("Open Portal", null, (_, _) => OpenPortal());
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add("Exit", null, (_, _) => Exit());
        return menu;
    }

    private void ShowStatus()
    {
        if (_statusForm is null || _statusForm.IsDisposed)
        {
            _statusForm = new StatusForm();
        }

        _statusForm.UpdateStatus(_agentLoop.Status, LoadConfig());
        _statusForm.Show();
        _statusForm.BringToFront();
    }

    private void ShowPairing()
    {
        var config = LoadConfig();
        var currentToken = _dpapiStore.LoadString(_configStore.SecretsPath);
        var startWithWindows = config is null ? true : RegistryAutoStart.IsEnabled();
        using var form = new PairForm(config, currentToken, startWithWindows);
        if (form.ShowDialog() == DialogResult.OK && form.ResultConfig is not null)
        {
            _configStore.Save(form.ResultConfig);
            if (!string.IsNullOrWhiteSpace(form.ResultDeviceToken))
            {
                _dpapiStore.SaveString(_configStore.SecretsPath, form.ResultDeviceToken);
            }

            if (form.StartWithWindows)
            {
                RegistryAutoStart.Enable();
            }
            else
            {
                RegistryAutoStart.Disable();
            }

            _agentLoop.Restart();
        }
    }

    private void OpenPortal()
    {
        var config = LoadConfig();
        var url = PortalUrlHelper.ResolvePortalUrl(config);
        if (string.IsNullOrWhiteSpace(url))
        {
            MessageBox.Show("Configure a Portal URL in the Pair Device screen.", "CertHub Agent");
            return;
        }

        try
        {
            Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
        }
        catch (Exception ex)
        {
            _logger.Error("Failed to open portal", ex);
            MessageBox.Show("Failed to open portal URL.", "CertHub Agent");
        }
    }

    private void Exit()
    {
        _notifyIcon.Visible = false;
        _agentLoop.Stop();
        ExitThread();
    }

    private AgentConfig? LoadConfig() => _configStore.Load();
}
