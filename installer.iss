#define AppName "ReadNovelFull Library"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppPublisher "ReadNovelFull Library"
#define AppExeName "ReadNovelFull.exe"

[Setup]
AppId={{763AE754-A6D5-4F70-AB30-7F56A5D92C0D}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\ReadNovelFull
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=release
OutputBaseFilename=ReadNovelFull-Setup-Windows-x64
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
SetupLogging=yes
UninstallDisplayIcon={app}\{#AppExeName}
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "dist\ReadNovelFull\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "README_RELEASE.txt"; DestDir: "{app}"; DestName: "README.txt"; Flags: ignoreversion
Source: "THIRD_PARTY_NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\ReadNovelFull Library"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\ReadNovelFull Library"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch ReadNovelFull Library"; Flags: postinstall nowait skipifsilent
