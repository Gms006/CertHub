using System.Diagnostics;
using Certhub.Agent.Services;
using Certhub.Agent.Tray;

namespace Certhub.Agent;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        ApplicationConfiguration.Initialize();

        var logger = new Logger();
        var configStore = new AgentConfigStore(logger);
        var secretStore = new DpapiStore(logger);
        var installedThumbprintsStore = new InstalledThumbprintsStore(secretStore, logger);
        var cleanupService = new CertificateCleanupService(configStore, installedThumbprintsStore, logger);

        if (args.Any(arg => string.Equals(arg, "--cleanup", StringComparison.OrdinalIgnoreCase)))
        {
            return RunCleanup(args, configStore, secretStore, cleanupService, logger);
        }

        var scheduledTaskService = new ScheduledCleanupTaskService(logger);
        var exePath = Environment.ProcessPath ?? Application.ExecutablePath;
        scheduledTaskService.EnsureDailyCleanupTask(exePath);

        var agentLoop = new AgentLoop(
            configStore,
            secretStore,
            installedThumbprintsStore,
            cleanupService,
            scheduledTaskService,
            exePath,
            logger);

        var context = new TrayAppContext(configStore, secretStore, agentLoop, logger);
        Application.Run(context);
        return 0;
    }

    private static int RunCleanup(
        string[] args,
        AgentConfigStore configStore,
        DpapiStore secretStore,
        CertificateCleanupService cleanupService,
        Logger logger)
    {
        var exePath = Environment.ProcessPath ?? Application.ExecutablePath;
        var whoami = GetWhoami();
        logger.Info(
            $"Starting cleanup. Mode={ParseCleanupMode(args)}, ExePath={exePath}, User={Environment.UserName}, WhoAmI={whoami}");

        var config = configStore.Load();
        if (config is null || !config.IsValid())
        {
            logger.Error("Cleanup aborted: invalid or missing config.");
            return 1;
        }

        var deviceToken = secretStore.LoadString(configStore.SecretsPath);
        if (string.IsNullOrWhiteSpace(deviceToken))
        {
            logger.Error("Cleanup aborted: device token missing.");
            return 1;
        }

        var mode = ParseCleanupMode(args);
        CleanupResult result;
        try
        {
            result = cleanupService.Run(mode);
        }
        catch (Exception ex)
        {
            logger.Error("Cleanup failed with exception.", ex);
            return 1;
        }

        if (result.Success)
        {
            config.LastCleanupLocalDate = DateTime.Now.Date;
            configStore.Save(config);
        }

        try
        {
            var client = new AgentClient(config.ApiBaseUrl, logger);
            client.UpdateCredentials(config.DeviceId, deviceToken);
            client.AuthenticateAsync(config.DeviceId, deviceToken, CancellationToken.None).GetAwaiter().GetResult();

            var response = client.PostCleanupAsync(new AgentClient.CleanupEvent
            {
                RemovedCount = result.RemovedCount,
                FailedCount = result.FailedCount,
                RemovedThumbprints = result.RemovedThumbprints.ToList(),
                FailedThumbprints = result.FailedThumbprints.ToList(),
                SkippedCount = result.SkippedCount,
                SkippedThumbprints = result.SkippedThumbprints.ToList(),
                Mode = result.Mode.ToString().ToLowerInvariant(),
                RanAtLocal = result.RanAtLocal.ToString("o"),
            }, CancellationToken.None).GetAwaiter().GetResult();

            if (!response.IsSuccessStatusCode)
            {
                logger.Warn($"Cleanup audit failed: {(int)response.StatusCode} {response.ReasonPhrase}");
                return 1;
            }
        }
        catch (Exception ex)
        {
            logger.Error("Cleanup audit failed with exception.", ex);
            return 1;
        }

        return result.Success ? 0 : 1;
    }

    private static CleanupMode ParseCleanupMode(string[] args)
    {
        var modeArg = args.FirstOrDefault(arg =>
            arg.StartsWith("--cleanup-mode", StringComparison.OrdinalIgnoreCase) ||
            arg.StartsWith("--mode", StringComparison.OrdinalIgnoreCase));
        if (modeArg is null)
        {
            return CleanupMode.Scheduled;
        }

        var parts = modeArg.Split('=', 2, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (parts.Length == 2)
        {
            if (string.Equals(parts[1], "keep_until", StringComparison.OrdinalIgnoreCase))
            {
                return CleanupMode.KeepUntil;
            }

            if (Enum.TryParse<CleanupMode>(parts[1], true, out var parsed))
            {
                return parsed;
            }
        }

        return CleanupMode.Scheduled;
    }

    private static string GetWhoami()
    {
        try
        {
            var startInfo = new ProcessStartInfo("whoami.exe")
            {
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            using var process = Process.Start(startInfo);
            if (process is null)
            {
                return "unknown";
            }

            var output = process.StandardOutput.ReadToEnd().Trim();
            process.WaitForExit();
            return string.IsNullOrWhiteSpace(output) ? "unknown" : output;
        }
        catch
        {
            return "unknown";
        }
    }
}
