namespace Certhub.Agent.Services;

public sealed class ScheduledCleanupTaskService
{
    private const string TaskName = "CertHub Agent Cleanup 18h";
    private const string TaskDescription = "Remove temporary CertHub certificates daily at 18:00";

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
            action.Arguments = "--cleanup";
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
}
