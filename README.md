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


## Layout

| Path | What it is |
| --- | --- |
| `wallpaper-studio.html` | The whole editor: canvas, layers, controls |
| `wallpaper_server.py` | Local helper — wallpaper access, file storage, save states |
| `start.bat`, `start.command` | Launchers for running from source |
| `wallpaper-studio.spec` | PyInstaller recipe for the packaged builds |
| `packaging/` | The README that ships inside each zip |
