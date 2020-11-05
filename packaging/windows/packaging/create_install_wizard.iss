#define AppName "Cloudify Windows Agent"
#define AppVersion GetEnv('VERSION')
#define AppMilestone GetEnv('PRERELEASE')
#define AppBuild GetEnv('BUILD')
#define AppPublisher "Cloudify Platform Ltd."
#define AppURL "https://cloudify.co/"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={commonpf}\Cloudify {#AppVersion}-{#AppMilestone} Agents
DisableProgramGroupPage=yes
DisableDirPage=yes
OutputBaseFilename=cloudify-windows-agent_{#AppVersion}-{#AppMilestone}
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64 arm64 ia64
ArchitecturesAllowed=x64 arm64 ia64
MinVersion=6.0
SetupIconFile=source\icons\Cloudify.ico
UninstallDisplayIcon={app}\Cloudify.ico
OutputDir=output\

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "C:\Program Files\Cloudify {#AppVersion}-{#AppMilestone} Agents\*"; DestDir: "{app}"; Excludes: "\__pycache__\*"; Flags: createallsubdirs recursesubdirs
Source: "source\icons\Cloudify.ico"; DestDir: "{app}"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon";

[Icons]
Name: "{commondesktop}\Cloudify {#AppVersion}-{#AppMilestone} Agents"; Filename: "%WINDIR%\System32\WindowsPowerShell\v1.0\powershell.exe";  Parameters: "-NoExit -Command $env:Path=\""{app}\Scripts\;$env:Path\""; function prompt {{\""[Cloudify {#AppVersion}-{#AppMilestone} Agents] $($executionContext.SessionState.Path.CurrentLocation)>\""}"; WorkingDir: "{app}"; IconFilename: "{app}\Cloudify.ico"; Tasks: "desktopicon";
