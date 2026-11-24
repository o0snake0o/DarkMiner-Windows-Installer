#define AppName "DarkMiner"
#define AppVersion "0.4"

[Setup]
AppId={{B74C9E30-64AC-4A90-923E-C8E620C1B574}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=DarkMiner Project
DefaultDirName={localappdata}\Programs\DarkMiner
DefaultGroupName=DarkMiner
OutputDir=output
OutputBaseFilename=DarkMiner-Setup-0.4
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\DarkMiner.exe
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "dist\DarkMiner\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "licenses\xmrig-LICENSE.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion

[Icons]
Name: "{group}\DarkMiner"; Filename: "{app}\DarkMiner.exe"
Name: "{autodesktop}\DarkMiner"; Filename: "{app}\DarkMiner.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\DarkMiner.exe"; Description: "Open DarkMiner"; Flags: nowait postinstall skipifsilent
