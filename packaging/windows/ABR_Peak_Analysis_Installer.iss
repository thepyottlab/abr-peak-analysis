; -- ABR_Peak_Analysis_Installer.iss --

#define buildPath "..\..\dist\pyinstaller\windows\notebook\"
#define exeName "notebook.exe"
#define appName "ABR Peak Analysis"
#define iconName "icon.ico"
#define installerMarker "..\install_modes\installer\install_mode.txt"

; Extracts the semantic version from the executable.
#define SemanticVersion() \
   GetVersionComponents(buildPath + exeName, Local[0], Local[1], Local[2], Local[3]), \
   Str(Local[0]) + "." + Str(Local[1]) + "." + Str(Local[2])

#define installerName "ABR-Peak-Analysis-Setup-" + SemanticVersion() + "-win-x64"

[Setup]
AppName={#appName}
AppVersion={#SemanticVersion()}
AppVerName={#appName} V{#SemanticVersion()}
DefaultDirName={pf}\EPL\{#appName}
OutputDir=..\..\dist\installers
DefaultGroupName=EPL
AllowNoIcons=yes
OutputBaseFilename={#installerName}
UsePreviousAppDir=no
UsePreviousGroup=no
DisableProgramGroupPage=yes
PrivilegesRequired=admin

[Files]
Source: "{#buildPath}*.*"; DestDir: "{app}"; Excludes: "*.dll.c~,\mpl-data\fonts,\mpl-data\sample_data"; Flags: replacesameversion
Source: "{#buildPath}_internal\*.*"; DestDir: "{app}\_internal"; Excludes: "*.dll.c~,\mpl-data\fonts,\mpl-data\sample_data"; Flags: replacesameversion recursesubdirs
Source: "{#installerMarker}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{commondesktop}\{#appName}"; Filename: "{app}\notebook.exe"; IconFilename: "{app}\_internal\{#iconName}"; IconIndex: 0

[Run]
Filename: "{app}\notebook.exe"; Description: "Open {#appName}"; Flags: nowait postinstall skipifsilent
