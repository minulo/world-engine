<#
.SYNOPSIS
Open the World Engine control panel (Windows): a window that shows whether the world engine runs, with buttons to start,
stop, open, upgrade and delete it.

.DESCRIPTION
The panel runs on the Python that the launcher run.ps1 would use (Python 3.13, else 3.12 or 3.14), with tkinter, and
without a console window (pythonw). From cmd, or by a double-click, run scripts\panel.cmd, which starts this script.

.EXAMPLE
scripts\panel.cmd
Open the panel.
.EXAMPLE
scripts\panel.cmd -InstallShortcut
Put "World Engine" on the Desktop and in the Start menu, with its icon; open it from there from now on.
.EXAMPLE
scripts\panel.cmd -InstallShortcut -ShortcutDir C:\some\folder
Make the shortcut in that folder instead (the workflow uses this).
#>
[CmdletBinding()]
param(
    [switch]$InstallShortcut,
    [string]$ShortcutDir = "",
    [string]$Python = "",
    [switch]$SelfTest
)
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$Panel = Join-Path $Root "panel\world_engine_panel.py"

function Get-Answer([string[]]$Command, [string]$Code) {
    # As in run.ps1: the last line a short Python program prints, or $null if the command does not run. No double
    # quotes in the code: Windows PowerShell 5.1 does not pass them on to native programs.
    $exe = $Command[0]; $rest = @($Command | Select-Object -Skip 1)
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { return $null }
    try { $out = & $exe @rest -c $Code 2>$null } catch { return $null }
    if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
    return ("" + ($out | Select-Object -Last 1)).Trim()
}

# The Python, found as run.ps1 finds it, which must also have tkinter.
$Version = "import sys; print('%d.%d' % sys.version_info[:2])"
$WithTk = "import sys, tkinter; print(sys.executable)"
$NoTk = $null
if ($Python) {
    $found = Get-Answer @($Python) $WithTk
    if (-not $found) { $NoTk = $Python }
    $Python = $found
} else {
    :search foreach ($v in "3.13", "3.12", "3.14") {
        foreach ($c in @("py -$v", "python$v", "python3", "python")) {
            $cmd = $c -split " "
            if ((Get-Answer $cmd $Version) -ne $v) { continue }
            $exe = Get-Answer $cmd $WithTk
            if ($exe) { $Python = $exe; break search }
            if (-not $NoTk) { $NoTk = Get-Answer $cmd "import sys; print(sys.executable)" }
        }
    }
}
if (-not $Python) {
    if ($NoTk) {
        [Console]::Error.WriteLine("The Python $NoTk has no tkinter, which the panel needs. Run the Python installer again,")
        [Console]::Error.WriteLine("choose Modify, tick 'tcl/tk and IDLE', and finish; or install Python 3.13 with: winget install Python.Python.3.13")
    } else {
        [Console]::Error.WriteLine("No Python 3.13 (nor 3.12 or 3.14) was found. Install it, open a new window, and run this again:")
        [Console]::Error.WriteLine("  winget install Python.Python.3.13")
        [Console]::Error.WriteLine("Or name one: scripts\panel.cmd -Python C:\path\to\python.exe")
    }
    exit 3
}

if ($InstallShortcut) {
    $extra = @(); if ($ShortcutDir) { $extra = @("--dest", $ShortcutDir) }
    & $Python $Panel --install-shortcut @extra
    exit $LASTEXITCODE
}
if ($SelfTest) {
    & $Python $Panel --self-test
    exit $LASTEXITCODE
}
# The window, without a console: pythonw.exe beside python.exe.
$PythonW = Join-Path (Split-Path -Parent $Python) "pythonw.exe"
if (-not (Test-Path $PythonW)) { $PythonW = $Python }
Start-Process -FilePath $PythonW -ArgumentList ('"' + $Panel + '"') -WorkingDirectory $Root
exit 0
