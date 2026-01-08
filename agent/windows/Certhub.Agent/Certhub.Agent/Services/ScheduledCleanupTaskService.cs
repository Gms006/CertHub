namespace Certhub.Agent.Services;

public sealed class ScheduledCleanupTaskService
{
    private const string TaskName = "CertHub Cleanup 18h";
    private const string TaskDescription = "Remove temporary CertHub certificates daily at 18:00";
    private const string KeepUntilTaskPrefix = "CertHub KeepUntil";
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
            var taskFolder = GetOrCreateTaskFolder(service);
            if (taskFolder is null)
            {
                _logger.Warn("Cannot register cleanup task: task folder unavailable.");
                return;
            }
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

            taskFolder.RegisterTaskDefinition(
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

        try
        {
            var taskName = $"{KeepUntilTaskPrefix} {scheduledTime:yyyyMMdd-HHmm}";
            var args = $"--cleanup --mode=keep_until --task-name \"{taskName}\"";
            var serviceType = Type.GetTypeFromProgID("Schedule.Service");
            if (serviceType is null)
            {
                _logger.Warn("Task Scheduler COM service not available.");
                return;
            }

            dynamic service = Activator.CreateInstance(serviceType)!;
            service.Connect();
            var taskFolder = GetOrCreateTaskFolder(service);
            if (taskFolder is null)
            {
                _logger.Warn("Cannot register keep-until cleanup task: task folder unavailable.");
                return;
            }
            dynamic taskDefinition = service.NewTask(0);

            taskDefinition.RegistrationInfo.Description = $"CertHub keep-until cleanup at {scheduledTime:O}";
            taskDefinition.Settings.Enabled = true;
            taskDefinition.Settings.StartWhenAvailable = true;
            taskDefinition.Settings.Hidden = false;
            taskDefinition.Settings.DisallowStartIfOnBatteries = false;
            taskDefinition.Settings.StopIfGoingOnBatteries = false;
            taskDefinition.Settings.DeleteExpiredTaskAfter = "PT10M";
            taskDefinition.Principal.LogonType = 3; // TASK_LOGON_INTERACTIVE_TOKEN
            taskDefinition.Principal.RunLevel = 1; // TASK_RUNLEVEL_LUA

            dynamic trigger = taskDefinition.Triggers.Create(1); // TASK_TRIGGER_TIME
            var startLocal = scheduledTime.DateTime;
            trigger.StartBoundary = startLocal.ToString("yyyy-MM-dd'T'HH:mm:ss");
            trigger.EndBoundary = startLocal.AddMinutes(10).ToString("yyyy-MM-dd'T'HH:mm:ss");
            trigger.Enabled = true;

            dynamic action = taskDefinition.Actions.Create(0); // TASK_ACTION_EXEC
            action.Path = normalizedPath;
            action.Arguments = args;
            action.WorkingDirectory = Path.GetDirectoryName(normalizedPath) ?? string.Empty;

            taskFolder.RegisterTaskDefinition(
                taskName,
                taskDefinition,
                6, // TASK_CREATE_OR_UPDATE
                null,
                null,
                3, // TASK_LOGON_INTERACTIVE_TOKEN
                null);

            _logger.Info($"Created keep-until scheduled cleanup task (COM): {taskName}");
        }
        catch (Exception ex)
        {
            _logger.Error("Failed to ensure keep-until cleanup task (COM).", ex);
        }
    }

    private dynamic? GetOrCreateTaskFolder(dynamic service)
    {
        dynamic rootFolder = service.GetFolder("\\");
        dynamic? certHubFolder = null;
        const string certHubPath = "\\CertHub";
        try
        {
            certHubFolder = service.GetFolder(certHubPath);
        }
        catch (Exception ex)
        {
            try
            {
                certHubFolder = rootFolder.CreateFolder("CertHub");
            }
            catch (Exception createEx)
            {
                _logger.Error("Failed to access or create Task Scheduler folder \\CertHub.", createEx);
                _logger.Warn($"Original error: {ex.Message}");
                return null;
            }
        }

        var userName = Environment.UserName;
        if (string.IsNullOrWhiteSpace(userName))
        {
            return certHubFolder;
        }

        var userFolderPath = $"\\CertHub\\{userName}";
        try
        {
            return service.GetFolder(userFolderPath);
        }
        catch (Exception ex)
        {
            try
            {
                return certHubFolder.CreateFolder(userName);
            }
            catch (Exception createEx)
            {
                _logger.Warn($"Failed to access or create Task Scheduler folder {userFolderPath}. Falling back to \\CertHub.", createEx);
                _logger.Warn($"Original error: {ex.Message}");
                return certHubFolder;
            }
        }
    }

}
