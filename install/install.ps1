<#
.SYNOPSIS
    NinjaSRE installer for Windows.

.DESCRIPTION
    The same four properties the POSIX installer has, and they are properties
    rather than preferences:

    1. No elevation. Nothing here needs Administrator, and it installs to a
       per-user location so it never asks for it. A tool that needs elevation
       to install is one a managed workstation will not have.

    2. A user-local install with an exact PATH instruction. The per-user PATH
       is updated through the registry rather than the machine-wide one, and
       the command to refresh the current session is printed — a new binary
       nobody can run until they restart the terminal reads as a failed
       install.

    3. Integrity verification. The archive's SHA-256 is checked against the
       published checksum before anything is unpacked.

    4. No telemetry. This script reports nothing, anywhere.

.PARAMETER Version
    Which release to install. Defaults to the latest.

.PARAMETER InstallDir
    Where to install. Defaults to %LOCALAPPDATA%\Programs\ninjasre.
#>

[CmdletBinding()]
param(
    [string]$Version = $(if ($env:NINJASRE_VERSION) { $env:NINJASRE_VERSION } else { 'latest' }),
    [string]$InstallDir = $(Join-Path $env:LOCALAPPDATA 'Programs\ninjasre'),
    [string]$ReleaseBase = $(if ($env:NINJASRE_RELEASE_BASE) { $env:NINJASRE_RELEASE_BASE } else { 'https://get.ninjasre.dev' })
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$AppName = 'ninjasre'

function Write-Step { param([string]$Message) Write-Host $Message }
function Write-Problem { param([string]$Message) Write-Host $Message -ForegroundColor Yellow }

function Get-Platform {
    $arch = switch ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture) {
        'X64'   { 'amd64' }
        'Arm64' { 'arm64' }
        default { throw "unsupported architecture: $_. Install from source instead." }
    }
    return "windows-$arch"
}

function Assert-Checksum {
    param([string]$Archive, [string]$ChecksumFile)

    $name = Split-Path -Leaf $Archive
    $line = Select-String -Path $ChecksumFile -Pattern ([regex]::Escape("  $name")) -SimpleMatch |
        Select-Object -First 1
    if (-not $line) {
        throw "no published checksum for $name. Refusing to install."
    }

    $expected = ($line.Line -split '\s+')[0].ToLowerInvariant()
    $actual = (Get-FileHash -Path $Archive -Algorithm SHA256).Hash.ToLowerInvariant()

    if ($actual -ne $expected) {
        throw @"
checksum mismatch for $name.
  expected $expected
  got      $actual
Refusing to install. Something between the release and this machine changed it.
"@
    }
    Write-Step "verified $name"
}

function Add-ToUserPath {
    param([string]$Directory)

    # The per-user PATH, in the registry. Not the machine-wide one: that needs
    # Administrator, and needing Administrator is the thing this avoids.
    $current = [Environment]::GetEnvironmentVariable('Path', 'User')
    $entries = @()
    if ($current) { $entries = $current -split ';' | Where-Object { $_ } }

    if ($entries -contains $Directory) {
        return $false
    }

    [Environment]::SetEnvironmentVariable('Path', (@($entries) + $Directory) -join ';', 'User')
    return $true
}

function Install-NinjaSre {
    $platform = Get-Platform
    $archiveName = "$AppName-$Version-$platform.zip"
    $base = "$ReleaseBase/$Version"

    $work = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
    New-Item -ItemType Directory -Path $work -Force | Out-Null

    try {
        Write-Step "downloading $archiveName"
        # -UseBasicParsing so this works on a host with no Internet Explorer
        # engine registered, which is every Windows Server Core image.
        Invoke-WebRequest -Uri "$base/$archiveName" -OutFile (Join-Path $work $archiveName) -UseBasicParsing
        Invoke-WebRequest -Uri "$base/SHA256SUMS" -OutFile (Join-Path $work 'SHA256SUMS') -UseBasicParsing

        Assert-Checksum -Archive (Join-Path $work $archiveName) -ChecksumFile (Join-Path $work 'SHA256SUMS')

        Expand-Archive -Path (Join-Path $work $archiveName) -DestinationPath $work -Force
        $binary = Join-Path $work "$AppName.exe"
        if (-not (Test-Path $binary)) {
            throw "the archive did not contain $AppName.exe"
        }

        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
        Move-Item -Path $binary -Destination (Join-Path $InstallDir "$AppName.exe") -Force
        Write-Step "installed $(Join-Path $InstallDir "$AppName.exe")"

        if (Add-ToUserPath -Directory $InstallDir) {
            Write-Host ''
            Write-Problem "$InstallDir has been added to your PATH."
            Write-Problem 'Open a new terminal, or refresh this one:'
            Write-Host "  `$env:Path = [Environment]::GetEnvironmentVariable('Path','User') + ';' + [Environment]::GetEnvironmentVariable('Path','Machine')"
            Write-Host ''
        }

        Write-Host ''
        Write-Step "Next: $AppName onboard"
    }
    finally {
        # Cleaned up whatever happened, including a failed verification: a
        # rejected archive left in the temp directory is one somebody
        # eventually runs by hand.
        Remove-Item -Path $work -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Install-NinjaSre
