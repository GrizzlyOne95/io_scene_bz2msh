param(
	[string]$InstallDir = "$env:APPDATA\Blender Foundation\Blender\4.5\extensions\user_default\io_scene_bz2msh",
	[switch]$NoBackup
)

$ErrorActionPreference = "Stop"

$repoDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Test-Path $InstallDir)) {
	throw "Install directory not found: $InstallDir"
}

$files = @(
	"__init__.py",
	"blender_manifest.toml",
	"bz2msh.py",
	"bz2pak.py",
	"msh_blender_importer.py",
	"softimage_pic.py",
	"README.md"
)

if (-not $NoBackup) {
	$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
	$backupDir = "$InstallDir.backup_$stamp"
	Copy-Item $InstallDir $backupDir -Recurse
	Write-Host "Backup created: $backupDir"
}

foreach ($file in $files) {
	$source = Join-Path $repoDir $file
	$target = Join-Path $InstallDir $file
	if (-not (Test-Path $source)) {
		throw "Missing source file: $source"
	}
	Copy-Item $source $target -Force
	Write-Host "Synced $file"
}

Write-Host "Extension sync complete: $InstallDir"
