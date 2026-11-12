<#
.SYNOPSIS
Install the world engine, build the default world once, and open it in the browser (Windows; PowerShell 7 elsewhere).

.DESCRIPTION
Each step is skipped when it is done already: the environment .venv, the packages of requirements.lock (installed
again only when the lock changes) and the world (built only if its folder is missing). Ctrl+C stops the server.
From cmd, or by a double-click, run scripts\run.cmd, which starts this script with the same options.

.EXAMPLE
scripts\run.cmd
The first run installs and builds: a few minutes.
.EXAMPLE
scripts\run.cmd -Port 9000 -World worlds\other.zarr -Profile preview -Seed 7
.EXAMPLE
scripts\run.cmd -NoBrowser
Serve without opening a browser.
.EXAMPLE
scripts\run.cmd -Check
Install, build, serve, fetch the page and /api/world, stop (for CI).
#>
[CmdletBinding()]
param(
    [string]$World = "",
    [Alias("Profile")][string]$BuildProfile = "preview",
    [string]$Seed = "",
    [int]$Port = 8765,
    [Alias("Host")][string]$ListenHost = "127.0.0.1",
    [string]$Python = "",
    [switch]$NoBrowser,
    [switch]$Check
)
# Not "Stop": Windows PowerShell 5.1 turns a native program's lines on stderr into errors when its output is redirected
# (as in CI), and "Stop" would end the script at pip's first warning. Each native step is judged by its exit code.
$ErrorActionPreference = "Continue"
$OnWindows = ($PSVersionTable.PSEdition -eq "Desktop") -or $IsWindows
$Root = Split-Path -Parent $PSScriptRoot
if ($World -and -not [System.IO.Path]::IsPathRooted($World)) { $World = Join-Path (Get-Location).Path $World }  # taken from where it was run
Set-Location $Root -ErrorAction Stop
if (-not $World) {
    if ($BuildProfile -eq "preview" -and -not $Seed) { $World = Join-Path "worlds" "first.zarr" }
    else { $World = Join-Path "worlds" ("$BuildProfile" + $(if ($Seed) { "-seed$Seed" } else { "" }) + ".zarr") }
}

function Say([string]$Text) { Write-Host ""; Write-Host "== $Text" }
function Stop-With([int]$Code, [string[]]$Lines) { foreach ($l in $Lines) { [Console]::Error.WriteLine($l) }; exit $Code }
function Get-Answer([string[]]$Command, [string]$Code) {
    # The output of a short Python program, or $null if the command does not run (the Microsoft Store's stand-in for
    # python.exe answers with exit code 9009). Python code given to native commands here holds no double quotes: Windows
    # PowerShell 5.1 does not pass them on.
    $exe = $Command[0]; $rest = @($Command | Select-Object -Skip 1)
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { return $null }
    try { $out = & $exe @rest -c $Code 2>$null } catch { return $null }
    if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
    return ("" + ($out | Select-Object -Last 1)).Trim()
}

# 1. The environment .venv, made once, with Python 3.13, for which the lock was made; else 3.12 or 3.14, on which the
#    same pins install but were not tested.
$Version = "import sys; print('%d.%d' % sys.version_info[:2])"
if ($OnWindows) { $VPy = Join-Path $Root ".venv\Scripts\python.exe" } else { $VPy = Join-Path $Root ".venv/bin/python" }
if ((Test-Path .venv) -and -not (Get-Answer @($VPy) "print(1)")) {
    Say "The environment .venv does not run; making it again"; Remove-Item -Recurse -Force .venv -ErrorAction Stop
}
if (Test-Path .venv) {
    if ($Python -and ((Get-Answer @($Python) $Version) -ne (Get-Answer @($VPy) $Version))) {
        Write-Host "note: .venv was made with Python $(Get-Answer @($VPy) $Version); -Python counts only when .venv is made. Delete .venv to make it with $Python."
    }
} else {
    if (-not $Python) {
        :search foreach ($v in "3.13", "3.12", "3.14") {
            $candidates = @("python$v", "python3", "python")
            if ($OnWindows) { $candidates = @("py -$v") + $candidates }
            foreach ($c in $candidates) {
                $cmd = $c -split " "
                if ((Get-Answer $cmd $Version) -eq $v) { $Python = Get-Answer $cmd "import sys; print(sys.executable)"; break search }
            }
        }
    }
    if (-not $Python) {
        Stop-With 3 @(
            "No Python 3.13 (nor 3.12 or 3.14) was found. Install Python 3.13, open a new terminal window, and run this again:",
            "  winget install Python.Python.3.13",
            "  or the installer from https://www.python.org/downloads/windows/ (64-bit), or Python 3.13 from the Microsoft Store.",
            "Or name one: scripts\run.cmd -Python C:\path\to\python.exe")
    }
    $PyV = Get-Answer @($Python) $Version
    if (-not $PyV) { Stop-With 3 @("$Python does not run.") }
    if ($PyV -ne "3.13") {
        Write-Host "note: using Python $PyV. requirements.lock was made and tested with 3.13; its pins install on 3.12 and 3.14 too, but nothing was tested there and a world may differ in its last digits."
    }
    if ((Get-Answer @($Python) "import struct; print(struct.calcsize('P') * 8)") -ne "64") {
        Stop-With 3 @("$Python is a 32-bit Python; the pinned packages exist for 64-bit Python only. Install the 64-bit one.")
    }
    Say "Making the environment .venv with $Python (Python $PyV)"
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Remove-Item -Recurse -Force .venv -ErrorAction SilentlyContinue; Stop-With 3 @("Could not make the environment .venv.") }
}

# 2. The pinned packages.
$Stamp = Get-Answer @($VPy) "import hashlib, sys; print(hashlib.sha256(b''.join(open(f, 'rb').read().replace(b'\r\n', b'\n') for f in ('requirements.lock', 'pyproject.toml'))).hexdigest(), sys.version.split()[0])"
$StampFile = Join-Path ".venv" "worldengine-installed"
$Installed = $null
if (Test-Path $StampFile) { $Installed = ("" + (Get-Content $StampFile -Raw)).Trim() }
if ($Installed -ne $Stamp) {
    Say "Installing the pinned packages of requirements.lock (90 to 120 MB to download the first time)"
    & $VPy -m pip install --disable-pip-version-check --only-binary=:all: -r requirements.lock
    if ($LASTEXITCODE -eq 0) { & $VPy -m pip install --disable-pip-version-check --quiet --no-deps -e . }
    if ($LASTEXITCODE -ne 0) {
        Stop-With 4 @("The packages did not install (above: why). The lock needs Python 3.12 to 3.14 on 64-bit Windows, Linux or an Apple-silicon Mac.")
    }
    Set-Content -Path $StampFile -Value $Stamp -Encoding ascii -ErrorAction Stop
} else {
    Write-Host "The environment .venv holds the pinned packages already."
}

# 3. The world, once.
if (Test-Path $World) {
    Write-Host "The world $World exists; it is served as it is."
} else {
    Say "Building the $BuildProfile world into ${World}: one to two minutes for the preview, 40 to 80 for the standard one"
    $seedArgs = @(); if ($Seed) { $seedArgs = @("--seed", $Seed) }
    & $VPy -m worldengine build --profile $BuildProfile @seedArgs --out $World
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

# 4. Serve it.
Say "Serving $World"
$flags = @()
if ($Check) { $flags += "--check" } elseif (-not $NoBrowser) { $flags += "--open" }
& $VPy -m worldengine serve $World --port $Port --host $ListenHost @flags
exit $LASTEXITCODE
