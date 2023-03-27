#define AppDisplayName GetEnv('DISPLAY_NAME')
#define AppVersion GetEnv('VERSION')
#define AppBuild GetEnv('BUILD')
#define AppPublisher "Cloudify Platform Ltd."
#define AppURL "https://cloudify.co/"

[Setup]
AppName={#AppDisplayName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={commonpf}\Cloudify Agents\agent-{#AppDisplayName}
DisableProgramGroupPage=yes
DisableDirPage=yes
OutputBaseFilename=cloudify-windows-agent_{#AppDisplayName}
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
Source: "C:\Program Files\Cloudify Agents\agent-{#AppDisplayName}\*"; DestDir: "{app}"; Excludes: "\__pycache__\*"; Flags: createallsubdirs recursesubdirs
Source: "source\icons\Cloudify.ico"; DestDir: "{app}"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon";

[Icons]
Name: "{commondesktop}\Cloudify Agents\agent-{#AppDisplayName}"; Filename: "%WINDIR%\System32\WindowsPowerShell\v1.0\powershell.exe";  Parameters: "-NoExit -Command $env:Path=\""{app}\Scripts\;$env:Path\""; function prompt {{\""[Cloudify {#AppDisplayName} Agents] $($executionContext.SessionState.Path.CurrentLocation)>\""}"; WorkingDir: "{app}"; IconFilename: "{app}\Cloudify.ico"; Tasks: "desktopicon";
