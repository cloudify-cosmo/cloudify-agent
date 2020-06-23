#define AppName "Cloudify Windows Agent"
#define AppVersion GetEnv('VERSION')
#define AppMilestone GetEnv('PRERELEASE')
#define AppBuild GetEnv('BUILD')
#define AppPublisher "Cloudify Platform Ltd."
#define AppURL "https://cloudify.co/"

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
; Do not use the same AppId value in installers for other applications.
; (To generate a new GUID, click Tools | Generate GUID inside the IDE.)
AppId={{94B9D938-5123-4AC5-AA99-68F07F773DE2}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={commonpf}\Cloudify
DisableProgramGroupPage=yes
OutputBaseFilename=cloudify-windows-agent_{#AppVersion}-{#AppMilestone}
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64 arm64 ia64
ArchitecturesAllowed=x64 arm64 ia64
LicenseFile=source\license.txt
MinVersion=6.0
SetupIconFile=source\icons\Cloudify.ico
UninstallDisplayIcon={app}\Cloudify.ico
OutputDir=output\

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "C:\Program Files\Cloudify Agent\*"; DestDir: "{app}"; Excludes: "*.pyc,\__pycache__\*"; Flags: createallsubdirs recursesubdirs
Source: "source\icons\Cloudify.ico"; DestDir: "{app}"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon";

[Icons]
Name: "{commondesktop}\Cloudify Agent"; Filename: "{cmd}"; Parameters: "/k ""{app}\Scripts\activate.bat"""; WorkingDir: "{app}"; IconFilename: "{app}\Cloudify.ico"; Tasks: "desktopicon";
