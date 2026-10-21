; Inno Setup script pour OverLoad-Setup.exe (Windows 11 64-bit)
; Utilisation : compiler avec Inno Setup 6 depuis Windows.
; Source : dist\OverLoad.exe généré par PyInstaller.

#define MyAppName "OverLoad"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "TOFazer"
#define MyAppURL "https://github.com/TOFazer/OverLoad"

[Setup]
AppId={{8B0E8C1A-OverLoad-40C7-9E2A-001}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=..\dist
OutputBaseFilename=OverLoad-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
UninstallDisplayIcon={app}\OverLoad.exe
SetupIconFile=..\src\overload\ui\resources\icon.ico

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\OverLoad.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_LICENSES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\OverLoad.exe"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\OverLoad.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\OverLoad.exe"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; On conserve les données utilisateur (%APPDATA%\OverLoad) lors de la désinstallation — voir docs.
