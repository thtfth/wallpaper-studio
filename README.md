# Wallpaper Studio

Design a wallpaper in your browser — text layers, image layers, homework
sections — then set it as your desktop background with one click. Your previous
wallpaper is backed up automatically every time the app starts.

A web page can't change your wallpaper, so a small local server does that part.
In the packaged builds it's inside the app; nothing gets installed.

## Download

Grab the zip for your machine from
[Releases](../../releases). Nothing else is needed — Python is inside the app.

| Machine | Download | Lastest verison |
| --- | --- | --- |
| Windows 10/11 | `WallpaperStudio-Windows-x64.zip` | v0.1 |
| Mac, M1 or later | `WallpaperStudio-macOS-AppleSilicon.zip` | v0.1 |

Unzip it somewhere you'll keep it, then read the `README.txt` inside — on macOS
the first launch needs a right-click → Open, because the app isn't signed with a
paid Apple certificate.

Everything the app writes stays in its own folder: `Generated/`,
`Wallpaper Backups/` and `data/`. Delete the folder and it's fully gone.

## Running from source

If you'd rather not use a packaged build, you need Python 3.9 or newer:

* **Windows** — double-click `start.bat`
* **macOS and Linux** — double-click `start.command`

Both find Python, start the server and open the page. If Python is missing they
say so and offer to install it rather than failing silently.

## Building the release zips

The executables can't be cross-compiled: a Windows build has to happen on
Windows and a macOS build on macOS.

**With GitHub Actions (no Windows or Mac needed).** Push a tag and the workflow
builds all three zips and attaches them to a release:

```
git tag v1.0
git push origin v1.0
```

Or run it by hand from the Actions tab. Each build is smoke-tested — started,
pinged, stopped — so a bundle that compiles but can't run fails the job.

**On your own machine.** With Python 3 installed, run `build_windows.bat` on
Windows or `./build_macos.sh` on a Mac. Each produces one zip, ready to upload.

## Layout

| Path | What it is |
| --- | --- |
| `wallpaper-studio.html` | The whole editor: canvas, layers, controls |
| `wallpaper_server.py` | Local helper — wallpaper access, file storage, save states |
| `start.bat`, `start.command` | Launchers for running from source |
| `wallpaper-studio.spec` | PyInstaller recipe for the packaged builds |
| `packaging/` | The README that ships inside each zip |
