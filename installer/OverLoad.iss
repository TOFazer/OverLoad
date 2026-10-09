; =====================================================================
; OverLoad — script Inno Setup (STRUCTURE PRÉPARÉE, NON COMPILÉ)
;
; Ce fichier ne produit pas encore OverLoad-Setup.exe. Il prépare la
; structure de l'installateur. Il ne doit être compilé qu'après :
;   - validation de la cible Windows (décision 3 : Windows 11 64 bits) ;
;   - test sur une machine Windows propre ;
;   - ajout de la licence Inno Setup et des notices tierces dans l'installateur.
;
; Compilation prévue (non automatisée pour l'instant) :
;   ISCC.exe /DMyAppVersion=0.1.0 installer\OverLoad.iss
; =====================================================================
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0-dev"
#endif
[Setup]
AppId={{6F3B2C1E-8A4D-4F5B-9C7E-0D1A2B3C4D5E}
AppName=OverLoad
AppVersion={#MyAppVersion}
AppPublisher=TOFazer
AppPublisherURL=https://github.com/TOFazer/OverLoad
DefaultDirName={localappdata}\Programs\OverLoad
DefaultGroupName=OverLoad
DisableProgramGroupPage=yes
; Installation par utilisateur : pas de droits administrateur requis.
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=OverLoad-Setup
SetupIconFile=..\assets\overload.ico
UninstallDisplayIcon={app}\OverLoad.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Cible à confirmer (décision 3) : Windows 11 64 bits = version 10.0.22000.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.22000
LicenseFile=..\LICENSE
[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; Flags: unchecked
[Files]
Source: "..\dist\OverLoad.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_LICENSES.md"; DestDir: "{app}\licenses"; Flags: ignoreversion
[Icons]
Name: "{group}\OverLoad"; Filename: "{app}\OverLoad.exe"
Name: "{group}\Désinstaller OverLoad"; Filename: "{uninstallexe}"
Name: "{autodesktop}\OverLoad"; Filename: "{app}\OverLoad.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\OverLoad.exe"; Description: "Lancer OverLoad"; Flags: nowait postinstall skipifsilent unchecked
; Les réglages, les journaux et les téléchargements de l'utilisateur ne sont
; PAS supprimés à la désinstallation : aucune section [UninstallDelete] sur ces dossiers.
