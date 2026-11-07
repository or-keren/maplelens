# MapleLens

An open-source overlay for **MapleStory Classic** that keeps you in the game.
Instead of alt-tabbing to price sites, class guides and route finders, MapleLens
reads what's on your screen and shows what you need on top of the game window.

> **Status: Phase 2: path arrow.** The EXP meter (EXP/min, time to level, History window)
> is built, and so is the path arrow: pick a destination on the Path tab and an arrow over
> your character points the way, map by map.
>
> Map and portal data adapted from [meowdb](https://meowdb.com/msclassic).
> Minimap pictures and portal types from [OSMS Data Explorer](https://osmsdataexplorer.com).

## The promise: screen-reading only

MapleLens is **screen-reading only**. It may capture pixels of the game
window and draw its own separate window on top. It must never:

- read or write game process memory, or inject into / attach to the process
- read, modify, or hook game files or the client's network traffic
- send input (keys/clicks) to the game — no automation of any kind

Every change is checked by `scripts/check_screen_only.py` in CI. That script is
a speed bump against honest mistakes, not a security boundary. The rule itself
is what matters, and pull requests that break it are not accepted.

## Requirements

- Windows 10/11, or macOS with MapleStory Classic from Nexon's Mac launcher
- The game running **windowed or borderless** (windowed only on the Mac). True fullscreen hides overlay windows.
- On the Mac, the first run asks for Screen Recording for the app you start MapleLens from (Terminal, say).

## Download (Windows)

1. Open the [latest release](https://github.com/or-keren/maplelens/releases/latest) and
   download `MapleLens-Setup-X.Y.Z.exe` under **Assets**. If your browser says the file
   isn't commonly downloaded, choose to keep it.
2. Run it. The installer isn't signed yet, so Windows may show "Windows protected your
   PC". Click **More info**, then **Run anyway**. It installs for your user only and
   doesn't ask for admin rights.
3. Start MapleStory Classic **windowed or borderless**.
4. Start MapleLens from the Start menu (or leave "Launch MapleLens" ticked on the last
   setup page). It finds the game window by itself. If the box says "Looking for
   MapleStory…", right-click the box, choose **Pick game window…** and pick the game.
5. Drag the box where you want it. History opens the per-map table.

**Updating:** when a new version is out, the box says "Update to X.Y.Z: right-click".
Right-click the box and choose **Update to X.Y.Z…**. MapleLens downloads the setup,
checks it against the SHA-256 checksum GitHub publishes for it, saves your session and
closes. Setup then installs the new version without asking anything and starts it again.
Your settings and EXP history are kept. You can also download the newer setup and run it
yourself. It installs over the old version, and if MapleLens is running, Setup offers to
close it.

**The update check talks to GitHub:** a few seconds after it starts and then once a day,
MapleLens sends one HTTPS request to GitHub's API for the latest release. The request
carries `MapleLens/<version>` as its User-Agent and nothing about you or the game; the
update itself is downloaded from GitHub too. To turn the check off, right-click the box
and untick **Check for updates automatically**. **Check for updates now** still works
when you want it. Only the installed Windows app checks; running from source never does.

**Uninstalling:** Settings → Apps → MapleLens. Your settings and history stay in
`%APPDATA%\MapleLens`; delete that folder to remove them too. If something goes wrong,
attach `%APPDATA%\MapleLens\maplelens.log` (MapleLens writes its errors there) to a bug
report.

## Roadmap

1. **EXP meter:** EXP/min, time to level, and history per map.
2. **Path arrow:** routes drawn as an arrow over the game.
3. **Class helper:** the guide's advice for your level (gear, training spots, AP/SP).
4. **Prices:** market lookups without leaving the game.

## Run from source (macOS, developers)

You need [uv](https://docs.astral.sh/uv/). Start the game windowed or borderless, then:

```
git clone https://github.com/or-keren/maplelens.git
cd maplelens
uv sync
uv run maplelens
```

MapleLens looks for the window titled `MapleStory`. If yours is called something else,
right-click the box and use **Pick game window…**. The choice is saved.

## Development

Run the tests with `uv run pytest`. See [CONTRIBUTING.md](CONTRIBUTING.md) for the
checks, the workflow and how releases are made.

## Disclaimer

Unofficial fan project; not affiliated with Nexon. MapleStory is a trademark of
Nexon. Use at your own risk.

## License

[MIT](LICENSE)
