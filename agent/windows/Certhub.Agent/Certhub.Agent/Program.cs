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
        var mode = ParseCleanupMode(args);
        var taskName = ParseTaskName(args);
        var exePath = Environment.ProcessPath ?? Application.ExecutablePath;
        var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        logger.Info(
            $"Starting cleanup ({mode}). TaskName={taskName ?? "n/a"}, User={Environment.UserName}, LocalAppData={localAppData}, ExePath={exePath}");

        var exitCode = 1;
        try
        {
            var config = configStore.Load();
            if (config is null || !config.IsValid())
            {
                logger.Error("Cleanup aborted: invalid or missing config.");
                return exitCode;
            }

            var deviceToken = secretStore.LoadString(configStore.SecretsPath);
            if (string.IsNullOrWhiteSpace(deviceToken))
            {
                logger.Error("Cleanup aborted: device token missing.");
                return exitCode;
            }

            CleanupResult result;
            try
            {
                result = cleanupService.Run(mode);
            }
            catch (Exception ex)
            {
                logger.Error("Cleanup failed with exception.", ex);
                return exitCode;
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
                    Mode = FormatCleanupMode(result.Mode),
                    RanAtLocal = result.RanAtLocal.ToString("o"),
                }, CancellationToken.None).GetAwaiter().GetResult();

                if (!response.IsSuccessStatusCode)
                {
                    logger.Warn($"Cleanup audit failed: {(int)response.StatusCode} {response.ReasonPhrase}");
                    return exitCode;
                }
            }
            catch (Exception ex)
            {
                logger.Error("Cleanup audit failed with exception.", ex);
                return exitCode;
            }

            exitCode = result.Success ? 0 : 1;
            return exitCode;
        }
        finally
        {
            if (!string.IsNullOrWhiteSpace(taskName))
            {
                TryDeleteScheduledTask(taskName, logger);
            }
        }
    }

    private static CleanupMode ParseCleanupMode(string[] args)
    {
        for (var i = 0; i < args.Length; i++)
        {
            var arg = args[i];
            if (!arg.StartsWith("--cleanup-mode", StringComparison.OrdinalIgnoreCase) &&
                !arg.StartsWith("--mode", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            var parts = arg.Split('=', 2, StringSplitOptions.TrimEntries);
            var value = parts.Length == 2 ? parts[1] : null;
            if (value is null &&
                (string.Equals(arg, "--mode", StringComparison.OrdinalIgnoreCase) ||
                 string.Equals(arg, "--cleanup-mode", StringComparison.OrdinalIgnoreCase)) &&
                i + 1 < args.Length)
            {
                value = args[i + 1];
            }

            if (string.IsNullOrWhiteSpace(value))
            {
                continue;
            }

            if (string.Equals(value, "keep_until", StringComparison.OrdinalIgnoreCase))
            {
                return CleanupMode.KeepUntil;
            }

            if (Enum.TryParse<CleanupMode>(value, true, out var parsed))
            {
                return parsed;
            }
        }

        return CleanupMode.Scheduled;
    }

    private static string? ParseTaskName(string[] args)
    {
        for (var i = 0; i < args.Length; i++)
        {
            var arg = args[i];
            if (arg.StartsWith("--task-name=", StringComparison.OrdinalIgnoreCase))
            {
                var parts = arg.Split('=', 2, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
                if (parts.Length == 2)
                {
                    return parts[1].Trim('"');
                }
            }

            if (string.Equals(arg, "--task-name", StringComparison.OrdinalIgnoreCase) && i + 1 < args.Length)
            {
                return args[i + 1].Trim('"');
            }
        }

        return null;
    }

    private static string FormatCleanupMode(CleanupMode mode)
    {
        return mode == CleanupMode.KeepUntil ? "keep_until" : mode.ToString().ToLowerInvariant();
    }

    private static void TryDeleteScheduledTask(string taskName, Logger logger)
    {
        try
        {
            var startInfo = new ProcessStartInfo("schtasks.exe")
            {
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            startInfo.ArgumentList.Add("/Delete");
            startInfo.ArgumentList.Add("/TN");
            startInfo.ArgumentList.Add(taskName);
            startInfo.ArgumentList.Add("/F");

            using var process = Process.Start(startInfo);
            if (process is null)
            {
                logger.Error($"Failed to delete task {taskName}: schtasks not started.");
                return;
            }

            var output = process.StandardOutput.ReadToEnd().Trim();
            var error = process.StandardError.ReadToEnd().Trim();
            process.WaitForExit();

            if (process.ExitCode == 0)
            {
                logger.Info($"Deleted keep-until task: {taskName}");
            }
            else
            {
                logger.Error($"Failed to delete task {taskName}. Output: {output} Error: {error}");
            }
        }
        catch (Exception ex)
        {
            logger.Error($"Failed to delete task {taskName}", ex);
        }
    }
}
