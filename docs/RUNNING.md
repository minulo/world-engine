# Running the world engine on your computer

Every operation, for every system, in one place: [install](#1-install), [open](#2-open-the-app),
[close](#3-close-the-app), [upgrade](#4-upgrade), [delete](#5-delete), and [when something goes wrong](#6-when-something-goes-wrong).
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

A world built on one computer opens on another, but the same seed does not give exactly the same world on different
machines: the numbers differ in many fields (README, "Worlds from another system").
