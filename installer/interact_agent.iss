;====================================================
; InterAct Desktop Agent Installer
; Version 1.0.0
;====================================================

#define MyAppName "InterAct Desktop Agent"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "InterAct"
#define MyAppURL "https://github.com/Giriz-3407/InterAct-Agent"
#define MyAppExeName "InterActDesktopAgent.exe"

[Setup]

; IMPORTANT:
; Never change this GUID after the first public release.
AppId={{78599F81-BB21-4199-ACC1-FBF11370679A}}

AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}

AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

DefaultDirName={autopf}\InterAct Agent
DefaultGroupName=InterAct

OutputDir=output
OutputBaseFilename=InterAct-Desktop-Agent-{#MyAppVersion}-Setup

Compression=lzma2
SolidCompression=yes
WizardStyle=modern

PrivilegesRequired=admin

ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

UsePreviousAppDir=yes
UsePreviousGroup=yes

DisableProgramGroupPage=yes

UninstallDisplayIcon={app}\{#MyAppExeName}

VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=InterAct Desktop Agent Installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

;----------------------------------------------------
; Branding (Enable after assets are created)
;----------------------------------------------------

;SetupIconFile=..\assets\icons\interact.ico
;WizardImageFile=..\assets\installer\wizard.bmp
;WizardSmallImageFile=..\assets\installer\wizard_small.bmp
;LicenseFile=license.txt

[Languages]

Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]

Name: "desktopicon"; Description: "Create a Desktop Shortcut"; GroupDescription: "Additional Tasks:"; Flags: unchecked

[Files]

Source: "..\dist\InterActDesktopAgent.exe"; DestDir: "{app}"; Flags: ignoreversion

Source: "..\config\agent.cfg"; DestDir: "{app}"; Flags: onlyifdoesntexist

[Icons]

Name: "{group}\InterAct Desktop Agent"; Filename: "{app}\{#MyAppExeName}"

Name: "{autodesktop}\InterAct Desktop Agent"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]

Filename: "{app}\{#MyAppExeName}"; \
Description: "Launch InterAct Desktop Agent"; \
Flags: nowait postinstall skipifsilent