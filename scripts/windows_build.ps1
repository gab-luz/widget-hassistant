param(
    [string]$PythonCommand = 'py -3',
    [string]$DistRelative = 'dist\windows',
    [string]$InnoSetupCompiler = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
)

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$distRoot = Join-Path $projectRoot $DistRelative
$portableDir = Join-Path $distRoot 'portable'
$setupDir = Join-Path $distRoot 'setup'
$venvPath = Join-Path $projectRoot '.venv-build-windows'

if (Test-Path $venvPath) {
    Remove-Item -Recurse -Force $venvPath
}

Write-Host "[windows-build] Creating virtual environment"
& $PythonCommand -m venv $venvPath

$pipExe = Join-Path $venvPath 'Scripts\pip.exe'
$pyinstallerExe = Join-Path $venvPath 'Scripts\pyinstaller.exe'

& $pipExe install --upgrade pip | Out-Null
& $pipExe install -r (Join-Path $projectRoot 'requirements.txt') pyinstaller | Out-Null

if (Test-Path $portableDir) {
    Remove-Item -Recurse -Force $portableDir
}
if (Test-Path $setupDir) {
    Remove-Item -Recurse -Force $setupDir
}

Write-Host "[windows-build] Building portable executable"
& $pyinstallerExe --clean --noconfirm --windowed --onefile --name hassistant-widget `
    --distpath $portableDir `
    (Join-Path $projectRoot 'main.py')

Write-Host "[windows-build] Building onedir application for installer"
& $pyinstallerExe --clean --noconfirm --windowed --name hassistant-widget `
    --distpath $setupDir `
    (Join-Path $projectRoot 'main.py')

$oneDir = Join-Path $setupDir 'hassistant-widget'
if (-not (Test-Path $oneDir)) {
    throw "Expected PyInstaller output at $oneDir"
}

if (-not (Test-Path $InnoSetupCompiler)) {
    throw "Inno Setup compiler not found at $InnoSetupCompiler"
}

$pyprojectPath = Join-Path $projectRoot 'pyproject.toml'
$version = '0.0.0'
if (Test-Path $pyprojectPath) {
    $match = Select-String -Path $pyprojectPath -Pattern '^\s*version\s*=\s*"([^"]+)"' -AllMatches | Select-Object -First 1
    if ($match -and $match.Matches.Count -gt 0) {
        $version = $match.Matches[0].Groups[1].Value
    }
}

if (-not (Test-Path $distRoot)) {
    New-Item -ItemType Directory -Force -Path $distRoot | Out-Null
}

$resolvedDist = (Resolve-Path $distRoot).Path
$installerOutput = Join-Path $resolvedDist 'hassistant-widget-setup.exe'
$issPath = Join-Path $setupDir 'installer.iss'

$escapedSource = $oneDir.Replace('\', '\\')
$escapedOutputDir = $resolvedDist.Replace('\', '\\')

$issContent = @"
[Setup]
AppId={{EAED061B-6B1A-4D69-82A1-7B992E8F1F59}}
AppName=Home Assistant Tray Widget
AppVersion=$version
AppPublisher=Widget Hassistant
DefaultDirName={pf}\Home Assistant Tray Widget
DisableProgramGroupPage=yes
OutputDir=$escapedOutputDir
OutputBaseFilename=hassistant-widget-setup
Compression=lzma
SolidCompression=yes

[Files]
Source: "$escapedSource\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Home Assistant Tray Widget"; Filename: "{app}\hassistant-widget.exe"

[Run]
Filename: "{app}\hassistant-widget.exe"; Description: "Launch Home Assistant Tray Widget"; Flags: nowait postinstall skipifsilent
"@

Set-Content -Path $issPath -Value $issContent -Encoding UTF8

Write-Host "[windows-build] Running Inno Setup compiler"
& $InnoSetupCompiler $issPath

Write-Host "[windows-build] Portable executable: $(Join-Path $portableDir 'hassistant-widget.exe')"
Write-Host "[windows-build] Installer executable: $installerOutput"
