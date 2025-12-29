using Certhub.Agent.Services;
using Certhub.Agent.Tray;

namespace Certhub.Agent;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();

        var logger = new Logger();
        var configStore = new AgentConfigStore(logger);
        var secretStore = new DpapiStore(logger);
        var installedThumbprintsStore = new InstalledThumbprintsStore(secretStore, logger);
        var agentLoop = new AgentLoop(configStore, secretStore, installedThumbprintsStore, logger);

        var context = new TrayAppContext(configStore, secretStore, agentLoop, logger);
        Application.Run(context);
    }
}
