# Running the world engine on your computer

Every operation, for every system, in one place: [install](#1-install), [open](#2-open-the-app),
[close](#3-close-the-app), [upgrade](#4-upgrade), [delete](#5-delete), and [when something goes wrong](#6-when-something-goes-wrong).
On Windows and macOS, a window does the same with buttons and shows whether the engine is running:
[the control panel](#the-control-panel).
Pick your system in each section. What the launcher does, the time and disk it takes, and what was tested where are
in the README, under "Run it on your computer".

| Your computer | Use |
|---|---|
| macOS on Apple silicon (M1 and later) | the launcher, `scripts/run.sh` |
| Ubuntu (or another Linux) | the launcher, `scripts/run.sh` |
| Windows 10 or 11 | the launcher, `scripts\run.cmd` |
| macOS on an Intel processor | Docker: the engine's pinned packages cannot be installed there |
| Any of these, if you prefer containers | Docker |

Until the work on the branch `claude/quirky-newton-a5zchs` is merged, `main` has no launcher: the install below
switches to that branch. Once it is merged, leave out the `git checkout` line.

## The control panel

The control panel is a small window, "World Engine", that shows whether the world engine is running and has a button
for each operation of this page. It is an alternative to the commands of sections 2 to 5, not a replacement: both work
on the same folder, and the panel also sees, and can stop, a server that was started from a terminal. Install the
engine first (section 1); the panel's first Start does the rest.

The panel needs Python with tkinter. The installers from python.org include it, on Windows and on macOS. Homebrew's
Python does not: add it with `brew install python-tk@3.13`.

### Open it

| System | The first time, in the `world-engine` folder | From then on |
|---|---|---|
| Windows | `.\scripts\panel.cmd` in PowerShell, or double-click `panel.cmd` in the `scripts` folder. Then press **Install shortcut** (or run `.\scripts\panel.cmd -InstallShortcut`) | "World Engine" on the Desktop or in the Start menu |
| macOS | `scripts/panel.command` in Terminal, or double-click it in the Finder (it opens a Terminal window, which you may close). Then press **Install app** (or run `scripts/panel.command --install-app`) | "World Engine" in the Applications folder of your home folder (`~/Applications`), or from Spotlight |

The shortcut and the app open the panel of the folder they were made from. If you move the folder, open the panel from
the folder's new place and install them again.

### The light

The panel asks the engine itself, every two seconds, whether it answers (`GET /api/world` on 127.0.0.1 at the panel's
port). The light is green only when the engine answers, whoever started it; a port that another program holds is not
taken for the engine.

| Light | Words | Meaning |
|---|---|---|
| grey | Stopped | Nothing answers on the port. |
| amber | Installing | The launcher makes `.venv` and installs the packages (the first start, or after a reset, or after an upgrade that changed `requirements.lock`). |
| amber | Building the world | The launcher builds the world: one to two minutes for the preview. |
| amber | Starting, Stopping, Working | The server is starting or stopping, or the panel is upgrading or deleting. |
| green | Running | The engine answers. Under the light are its address (click it to open the viewer), the world, the process number and how long it has run. |
| red | Error | The launcher stopped with an error, or another program holds the port. The reason is under the light; **Details** shows everything the launcher printed. |

### The buttons

Each button is greyed out when it makes no sense (Start while the engine runs, for example). Pointing at a button shows
what it does at the foot of the window.

| Button | What it does |
|---|---|
| **Start** | Runs the launcher of section 2 without a browser (`scripts/run.sh --no-browser` on macOS, `scripts\run.ps1 -NoBrowser` on Windows), with the port and the world of the settings. Its output appears under **Details** and in `.worldengine/launcher.log`. |
| **Stop** | Stops the engine: it asks the server to stop, and if the server does not, it ends the process. This works for a server started from a terminal too. In the middle of a build it warns first: the world being built is thrown away, because a world is written to disk only at the very end. At most a folder `<world>.partial` is left, which the next build removes. |
| **Open in browser** | Opens the viewer. |
| **Upgrade…** | Asks first. It stops the engine if it runs and fetches the newest code of the version chosen under **Version**: of the version this copy is on already with `git pull --ff-only`, of another one by switching to it (`git fetch`, then `git checkout`). If the code changed, it deletes the default world `worlds/first.zarr`, so that the next start builds it with the new engine (section 4 says why). Other worlds are kept. If Git is missing, the repository cannot be reached, or your copy has changes or commits of its own that stand in the way, it says so and changes nothing. Afterwards it offers to start; if the panel's own code changed, it offers to open the panel again instead, so that the new panel is the one you use. |
| **Rebuild world…** | Asks first. It deletes the selected world and starts, which builds the world again. |
| **Reset environment…** | Asks first. It deletes `.venv` (about 450 MB); the next start makes it again and downloads the packages. Use it when the packages are broken. |
| **Open folder** | Shows the `world-engine` folder in Explorer or the Finder. |
| **Install shortcut** (Windows), **Install app** (macOS) | Makes the shortcuts or the app described above. |
| **Delete…** | Asks first, with the list of what it removes: `.venv`, `worlds/`, `.worldengine/` (the panel's settings and logs) and the shortcuts or the app it installed. It does not remove the `world-engine` folder itself, Python or Git. After the panel has closed, delete the folder as section 5 says. |
| **Details**, **Copy log**, **Open log** | Show the launcher's output, copy it (to send to someone who helps), or open its file. |
| Settings: **Port**, **World** | The port (8765 unless you change it) and the world to serve: one of the worlds in `worlds/`, or a new name, which Start builds. The panel keeps them in `.worldengine/panel.json`. They can be changed while the engine is stopped. |
| Settings: **Version**, **Check for new** | The version of the engine to run: one of the branches of the repository this copy was cloned from, the newest first, each with the date of its newest commit. The line below says which version this copy is on, at which commit, and whether a newer commit is there. Choosing one changes nothing by itself: **Upgrade…** then switches to it. The panel asks the repository for its versions once when it opens (`git fetch`, which changes no file of the engine); **Check for new** asks again. Without a network the list is the one the copy had. |

### Choosing a version

A version is a branch of the repository: a line of work with a name, such as `main`, or a branch that holds a
feature that has not been merged yet. Until now, running such a feature meant typing `git fetch` and `git checkout`
in a terminal. The panel does it:

1. Open the panel. Under **Settings**, open the **Version** list (press **Check for new** first if the version you
   want is not there).
2. Choose the version. The line below shows what its newest commit says.
3. Press **Upgrade…** and confirm. The panel stops the engine, switches the folder to that version, and deletes the
   default world if the code changed.
4. If it offers to open the panel again, say yes: the new version may have a newer panel. Then press **Start**; the
   world is built again with the new engine.

The same steps bring you back to the version you had. A switch either happens as a whole or not at all: the panel
refuses, and changes nothing, when the chosen version is not in the repository (any more), when files of the engine
that you changed in the folder would be overwritten, when your copy has a branch of that name with commits of its
own, or when the repository cannot be reached. Worlds other than the default one are kept, also those that another
version built; a world built by other code is served with a warning that the engine's code has changed since.

A copy whose panel has no **Version** list yet gets it with one ordinary **Upgrade…**, if the version it is on has
the list by now; close the panel and open it again afterwards. Otherwise leave that version once by hand (section 4,
"To another version").

When you close the panel while the engine runs, it asks whether to leave it running. **Keep running** closes the window
and the engine goes on serving (open the panel again to stop it); **Stop and quit** stops it first.

### How it knows, and what was checked

While it runs, `serve` writes `.worldengine/server-<port>.json`: its process number, address, world, start time and
engine version, and a token with which the panel asks it to stop (`POST /api/stop`, which the server refuses without
that token). It removes the file when it stops on Ctrl+C, on SIGTERM, on the panel's request or at the end of
`--check`. A file left by a server that was killed is recognised (its process has gone, or nothing answers on its
port) and removed. A server of an older engine writes no such file: the panel shows it as running, but it can be
stopped only where it was started.

On Linux, where the panel was written, it ran with Tk 9.0 on a virtual screen: its self-test showed every state, and a
real Start from the window made `.venv`, built the preview world and served it; the server went on running after the
window was closed with "Keep running", and a newly opened panel then stopped it [MEASURED on 2026-11-02 with Python 3.13.14 of python-build-standalone and Tk 9.0.3 under Xvfb: Start to Installing 1 s, to Building the world 39 s, to Running 187 s; python.org and setup-python ship Tk 8.6, which was not run here]. The
workflow `.github/workflows/local-run.yml` runs the following on Windows and macOS: the self-test of the window with
setup-python's Python; Start, Running and Stop through the panel's control layer with the real launcher; the stop of a
server started as from a terminal; the shortcut on Windows (made into a folder of the runner); and on macOS the app,
whose Info.plist is checked with `plutil -lint` and which is then opened with `open`. Every one of these steps passed
on windows-latest (Tk 8.6.15, the vista theme) and macos-latest [MEASURED: GitHub Actions run 41530268296, 2026-11-02].
The first run on Windows found that a closed port of the same computer is refused only after about 2 s there, which
the panel's Stop then took for a server still running; the panel now waits long enough. Nobody has used the panel
by hand on Windows or on a Mac.

The **Version** list was checked on Linux [MEASURED on 2026-11-12: Python 3.13.14 of python-build-standalone, Tk 9.0.3
under Xvfb, git 2.43.0]. Six tests of `tests/test_panel.py` move real Git repositories to another version, on along
it, and back, and through each refusal, where they check that nothing changed. In a fresh clone of this repository the
window itself, with a later version chosen and both of its questions answered with yes, switched the folder, deleted
the default world, kept another world, and opened the later version's panel while the old window closed. The first
such run showed that the closing window still read its queue once more and printed an error; it no longer does. On
Windows and macOS the workflow runs the same tests and the self-test of the window, which shows a made-up list of
versions; nobody has chosen a version by hand there.

Two things about the macOS app were not checked by hand:

- Gatekeeper. macOS checks an app when it is first opened if the app carries the quarantine attribute, which the
  program that downloaded it sets [DOCUMENTED: Apple, WWDC 2019 session 701, "Advances in macOS Security"; Howard
  Oakley, "Quarantine and the quarantine flag", eclecticlight.co, 2020; both seen through a search, not read in full].
  The panel writes the app's files itself and downloads nothing, so the app should carry no such attribute and open
  without a prompt, although it is not signed [INFERRED; the workflow checks that the attribute is absent]. If macOS
  does ask, right-click the app, choose Open, and confirm once.
- The app runs the panel with the Python that installed it, so the Dock and the menu bar may show "Python" rather than
  "World Engine" [UNVERIFIED].

## 1. Install

You do this once. The first time you open the app (section 2) it also downloads about 100 MB of packages and builds
the default world, which takes a few minutes.

### macOS (Apple silicon)

Needs [Homebrew](https://brew.sh); the installer from python.org works as well.

```
brew install python@3.13 git
git clone https://github.com/minulo/world-engine.git
cd world-engine
git checkout claude/quirky-newton-a5zchs
```

### Ubuntu 25.04 or 25.10

```
sudo apt update
sudo apt install -y git python3.13 python3.13-venv
git clone https://github.com/minulo/world-engine.git
cd world-engine
git checkout claude/quirky-newton-a5zchs
```

### Ubuntu 22.04, 24.04 or 26.04

Python 3.13 is not in these releases' own archive; the deadsnakes archive has it.

```
sudo apt update
sudo apt install -y git software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.13 python3.13-venv
git clone https://github.com/minulo/world-engine.git
cd world-engine
git checkout claude/quirky-newton-a5zchs
```

### Windows 10 or 11 (PowerShell)

```
winget install -e --id Python.Python.3.13
winget install -e --id Git.Git
```

Close PowerShell and open a new window, so that it finds Python and Git. Then:

```
git clone https://github.com/minulo/world-engine.git
cd world-engine
git checkout claude/quirky-newton-a5zchs
```

Clone into a folder that OneDrive does not keep in step (Documents and Desktop often are), and keep the folder's path
short (under about 120 characters).

### Docker (Intel Macs, or any system)

Install Docker Desktop (macOS, Windows) or Docker Engine (Linux), then:

```
git clone https://github.com/minulo/world-engine.git
cd world-engine
git checkout claude/quirky-newton-a5zchs
docker compose build
```

If the repository is private, `git clone` asks you to sign in to GitHub: a personal access token works as the
password, or sign in first with `gh auth login` (GitHub's command-line tool).

## 2. Open the app

In the `world-engine` folder:

| System | Command |
|---|---|
| macOS, Ubuntu | `scripts/run.sh` |
| Windows, PowerShell | `.\scripts\run.cmd` |
| Windows, Explorer | double-click `run.cmd` in the `scripts` folder |
| Docker | `docker compose up` |

The browser opens the viewer at **http://127.0.0.1:8765/** (with Docker, open http://localhost:8765/ yourself).
If no browser opens, type the address in. The first time, the launcher makes `.venv`, installs the packages and
builds `worlds/first.zarr` before it serves; later it opens at once.

In the viewer: choose a field, drag to turn the globe, scroll to zoom, click a cell for its values and its "why"
answer. The day slider under "Storms and weather" steps through the days.

Options (on Windows the same with one dash and a capital: `-Port`, `-Seed`, `-World`, `-Profile`, `-NoBrowser`):

```
scripts/run.sh --port 9000                  # another port, if 8765 is taken
scripts/run.sh --seed 7                     # another planet: built once into worlds/preview-seed7.zarr
scripts/run.sh --profile standard           # the large world: 6.7 GB of memory, an hour or more to build
scripts/run.sh --no-browser                 # serve without opening a browser
scripts/run.sh --check                      # install, build, check that it serves, and stop
```

## 3. Close the app

| How you opened it | How to close it |
|---|---|
| `scripts/run.sh`, or `.\scripts\run.cmd` in PowerShell | press **Ctrl+C** in that terminal |
| `run.cmd` by double-click | press **Ctrl+C** in its window (answer `Y` if cmd asks "Terminate batch job"), or close the window |
| `docker compose up` | press **Ctrl+C**, or run `docker compose down` from another terminal in the folder |

Closing the browser tab does not stop the server; closing the terminal does. Nothing is lost either way: the
world is kept on disk, and the next open serves it again.

## 4. Upgrade

Close the app first. Then, in the `world-engine` folder:

### macOS, Ubuntu

```
git pull
rm -rf worlds/first.zarr
scripts/run.sh
```

### Windows (PowerShell)

```
git pull
Remove-Item -Recurse -Force worlds\first.zarr
.\scripts\run.cmd
```

### Docker

```
git pull
docker compose down -v
docker compose build
docker compose up
```

To another version (a branch), and not only to the newest code of the one you have, put these two lines in the place
of `git pull`, with the name of the version (`git branch -r` lists them after the fetch). The control panel does the
same with its **Version** list ("Choosing a version" above).

```
git fetch origin "+refs/heads/*:refs/remotes/origin/*"
git checkout -B NAME --track origin/NAME
```

`git pull` fetches the new engine. The launcher installs the packages again by itself when `requirements.lock`
has changed. It does not rebuild a world that is already there, so deleting the world (the second line) makes it
build the default world with the new engine; keep the old one instead and the viewer serves it with a warning that
the engine's code has changed since it was built. Worlds you built with `--seed` or `--world` are kept until you
delete them the same way. In Docker, `down -v` deletes the volume that holds the world.

If the upgrade went wrong, delete the environment as well and open the app again: it is made afresh.

```
rm -rf .venv                                # macOS, Ubuntu
Remove-Item -Recurse -Force .venv           # Windows
```

## 5. Delete

Everything the app made lives inside the `world-engine` folder (the environment `.venv`, about 450 MB, and the worlds
in `worlds/`, about 37 MB each), so deleting the folder removes it all. Close the app first, then from the folder
that holds `world-engine`:

```
rm -rf world-engine                                 # macOS, Ubuntu
Remove-Item -Recurse -Force world-engine            # Windows (PowerShell)
```

With Docker, remove the container, its world volume and the image before deleting the folder:

```
cd world-engine
docker compose down -v --rmi all
docker volume rm worldengine-worlds                 # only if you also ran it with plain "docker run"
cd ..
rm -rf world-engine
```

Python and Git stay installed; remove them only if nothing else of yours uses them:

```
brew uninstall python@3.13                          # macOS
sudo apt remove python3.13 python3.13-venv          # Ubuntu
winget uninstall -e --id Python.Python.3.13         # Windows
```

## 6. When something goes wrong

| What you see | What to do |
|---|---|
| `No Python 3.13 (nor 3.12 or 3.14) was found` | install Python (section 1), open a new terminal, run again; or name one with `--python /path/to/python3.13` |
| `This is an Intel Mac ...` | use Docker (section 1) |
| `refused: cannot listen on 127.0.0.1 port 8765` | the app is already open in another window, or another program holds the port: close that, or use `--port 9000` |
| The browser shows nothing | open http://127.0.0.1:8765/ yourself; the terminal prints the address the server uses |
| `git clone` asks for a password | use a GitHub personal access token, or `gh auth login` first |
| Windows: the window closes at once after a double-click | open PowerShell in the folder and run `.\scripts\run.cmd` to read the message |
| Anything else after an upgrade | delete `.venv` and the world (section 4) and open the app again |
| The panel: `This Python has no tkinter` | macOS with Homebrew: `brew install python-tk@3.13`; or install Python 3.13 from python.org, which includes tkinter. Windows: run the Python installer again, choose Modify, tick "tcl/tk and IDLE" |
| The panel shows Running, but Stop is greyed out ("started without a run file") | a server of an older engine, or of another folder: stop it with Ctrl+C where it was started |
| The panel says another program uses the port | close that program, or choose another port in the panel's settings |
| The macOS app says the folder is gone | the `world-engine` folder was moved: open the panel from its new place (`scripts/panel.command`) and press **Install app** again |

A world built on one computer opens on another, but the same seed does not give exactly the same world on different
machines: the numbers differ in many fields (README, "Worlds from another system").
