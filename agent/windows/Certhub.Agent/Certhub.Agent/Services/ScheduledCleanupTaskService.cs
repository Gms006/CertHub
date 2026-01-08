using System.Diagnostics;
using System.Globalization;
using System.Threading.Tasks;

namespace Certhub.Agent.Services;

public sealed class ScheduledCleanupTaskService
{
    private const string TaskName = "CertHub Cleanup 18h";
    private const string TaskDescription = "Remove temporary CertHub certificates daily at 18:00";
    private const string KeepUntilTaskPrefix = "CertHub KeepUntil";
    private static readonly TimeSpan ProcessTimeout = TimeSpan.FromSeconds(15);

    private readonly Logger _logger;

    public ScheduledCleanupTaskService(Logger logger)
    {
        _logger = logger;
    }

    public void EnsureDailyCleanupTask(string executablePath)
    {
        try
        {
            var normalizedPath = executablePath;
            if (string.IsNullOrWhiteSpace(normalizedPath))
            {
                _logger.Warn("Cannot register cleanup task: executable path is empty.");
                return;
            }

            var serviceType = Type.GetTypeFromProgID("Schedule.Service");
            if (serviceType is null)
            {
                _logger.Warn("Task Scheduler COM service not available.");
                return;
            }

            dynamic service = Activator.CreateInstance(serviceType)!;
            service.Connect();
            dynamic rootFolder = service.GetFolder("\\");
            dynamic taskDefinition = service.NewTask(0);

            taskDefinition.RegistrationInfo.Description = TaskDescription;
            taskDefinition.Settings.Enabled = true;
            taskDefinition.Settings.StartWhenAvailable = true;
            taskDefinition.Settings.Hidden = false;
            taskDefinition.Settings.DisallowStartIfOnBatteries = false;
            taskDefinition.Settings.StopIfGoingOnBatteries = false;
            taskDefinition.Principal.LogonType = 3; // TASK_LOGON_INTERACTIVE_TOKEN
            taskDefinition.Principal.RunLevel = 1; // TASK_RUNLEVEL_LUA

            dynamic trigger = taskDefinition.Triggers.Create(2); // TASK_TRIGGER_DAILY
            var startAt = DateTime.Today.AddHours(18);
            trigger.StartBoundary = startAt.ToString("yyyy-MM-dd'T'HH:mm:ss");
            trigger.DaysInterval = 1;

            dynamic action = taskDefinition.Actions.Create(0); // TASK_ACTION_EXEC
            action.Path = normalizedPath;
            action.Arguments = "--cleanup --mode=scheduled";
            action.WorkingDirectory = Path.GetDirectoryName(normalizedPath) ?? string.Empty;

            rootFolder.RegisterTaskDefinition(
                TaskName,
                taskDefinition,
                6, // TASK_CREATE_OR_UPDATE
                null,
                null,
                3, // TASK_LOGON_INTERACTIVE_TOKEN
                null);

            _logger.Info($"Scheduled task ensured: {TaskName}");
        }
        catch (Exception ex)
        {
            _logger.Error("Failed to ensure scheduled cleanup task", ex);
        }
    }

    public void EnsureKeepUntilCleanupTask(DateTimeOffset keepUntilUtc, string executablePath)
    {
        var normalizedPath = executablePath;
        if (string.IsNullOrWhiteSpace(normalizedPath))
        {
            _logger.Warn("Cannot register keep-until cleanup task: executable path is empty.");
            return;
        }

        var localTime = keepUntilUtc.ToLocalTime();
        var scheduledTime = new DateTimeOffset(
            localTime.Year,
            localTime.Month,
            localTime.Day,
            localTime.Hour,
            localTime.Minute,
            0,
            localTime.Offset);
        if (localTime.Second > 0 || localTime.Millisecond > 0)
        {
            scheduledTime = scheduledTime.AddMinutes(1);
        }

        _logger.Info($"Keep-until requested: {localTime:O}; scheduled at minute boundary: {scheduledTime:O}");

        if (scheduledTime <= DateTimeOffset.Now)
        {
            _logger.Warn($"Keep-until time already passed ({scheduledTime:O}); skipping task creation.");
            return;
        }

        var taskName = $"{KeepUntilTaskPrefix} {scheduledTime:yyyyMMdd-HHmm}";
        var taskRun = $"\"{normalizedPath}\" --cleanup --mode=keep_until --task-name \"{taskName}\"";
        var containsPath = false;
        var containsArgs = false;
        try
        {
            var queryResult = RunSchtasks("/Query", "/TN", taskName, "/FO", "LIST", "/V");
            if (queryResult.ExitCode == 0)
            {
                containsPath = queryResult.Output.Contains(normalizedPath, StringComparison.OrdinalIgnoreCase);
                containsArgs = queryResult.Output.Contains("--cleanup --mode=keep_until", StringComparison.OrdinalIgnoreCase);
                if (containsPath && containsArgs)
                {
                    _logger.Info($"Keep-until task already exists: {taskName}");
                    return;
                }

                _logger.Warn($"Keep-until task exists with different command, updating: {taskName}");
            }

            var time = scheduledTime.ToString("HH:mm", CultureInfo.InvariantCulture);
            var currentUser = GetCurrentUser();
            var createResult = new ProcessResult(-1, string.Empty, "Keep-until task not created yet.");
            var lastCreateArgs = Array.Empty<string>();
            foreach (var dateFormat in new[] { "dd/MM/yyyy", "MM/dd/yyyy" })
            {
                var date = scheduledTime.ToString(dateFormat, CultureInfo.InvariantCulture);
                lastCreateArgs = new[]
                {
                    "/Create", "/F",
                    "/TN", taskName,
                    "/SC", "ONCE",
                    "/SD", date,
                    "/ST", time,
                    "/RU", currentUser,
                    "/NP",
                    "/TR", taskRun,
                    "/Z"
                };
                createResult = RunSchtasks(lastCreateArgs);
                if (createResult.ExitCode == 0)
                {
                    break;
                }

                _logger.Warn($"Keep-until create failed with /SD {dateFormat} (ExitCode={createResult.ExitCode}).");
            }
            if (createResult.ExitCode == 0)
            {
                _logger.Info($"Created keep-until scheduled cleanup task: {taskName}");
                var queryCreated = RunSchtasks("/Query", "/TN", taskName, "/FO", "LIST", "/V");
                if (queryCreated.ExitCode == 0)
                {
                    _logger.Info($"Keep-until task details:\n{queryCreated.Output}");
                }
            }
            else
            {
                _logger.Error(
                    $"Failed to create keep-until scheduled cleanup task {taskName}. Args: {string.Join(' ', lastCreateArgs)} Output: {createResult.Output} Error: {createResult.Error}");
            }
        }
        catch (Exception ex)
        {
            _logger.Error($"Failed to ensure keep-until cleanup task {taskName}", ex);
        }
    }

    private static string GetCurrentUser()
    {
        var whoami = RunProcess("whoami.exe");
        if (whoami.ExitCode == 0 && !string.IsNullOrWhiteSpace(whoami.Output))
        {
            return whoami.Output.Trim();
        }

        return Environment.UserName;
    }

    private static ProcessResult RunSchtasks(params string[] args)
    {
        return RunProcess("schtasks.exe", args);
    }

    private static ProcessResult RunProcess(string fileName, params string[] args)
    {
        var startInfo = new ProcessStartInfo(fileName)
        {
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            RedirectStandardInput = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };
        foreach (var arg in args)
        {
            startInfo.ArgumentList.Add(arg);
        }

        using var process = Process.Start(startInfo);
        if (process is null)
        {
            return new ProcessResult(-1, string.Empty, $"Failed to start {fileName}");
        }

        var outputTask = process.StandardOutput.ReadToEndAsync();
        var errorTask = process.StandardError.ReadToEndAsync();
        var exited = process.WaitForExit((int)ProcessTimeout.TotalMilliseconds);
        if (!exited)
        {
            try
            {
                process.Kill(true);
            }
            catch (Exception)
            {
            }

            return new ProcessResult(
                -1,
                string.Empty,
                $"Timed out after {ProcessTimeout.TotalSeconds:0}s running {fileName}.");
        }

        Task.WaitAll(outputTask, errorTask);
        return new ProcessResult(process.ExitCode, outputTask.Result.Trim(), errorTask.Result.Trim());
    }

    private readonly record struct ProcessResult(int ExitCode, string Output, string Error);
}
