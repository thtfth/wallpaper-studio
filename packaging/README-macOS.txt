Wallpaper Studio - macOS
========================

Nothing to install. Python is already inside the app.

1. Drag the "Wallpaper Studio" folder out of the zip to somewhere you'll
   keep it, such as Documents or Applications.

2. RIGHT-CLICK the "Wallpaper Studio" file and choose Open, then click
   Open again in the dialog.

   The right-click matters the first time. macOS blocks anything
   downloaded from the internet that isn't signed with a paid Apple
   developer certificate, and a plain double-click will just refuse with
   "cannot be opened because it is from an unidentified developer".
   After you've opened it once this way, double-clicking works from then on.

3. Terminal opens with the log, and your browser loads the app.

4. Press Ctrl+C in the Terminal window to stop the server.


If macOS refuses no matter what
-------------------------------
Open Terminal, type the following (with a trailing space), drag the
"Wallpaper Studio" file onto the window to fill in its path, then press
Return:

    xattr -dr com.apple.quarantine 

That removes the download quarantine flag. Then try opening it again.


Where your files go
-------------------
Everything lives in this same folder:

  Wallpaper Backups/   your previous wallpapers, 10 newest kept
  Generated/           images you generate, 10 newest kept
  data/                settings and your 5 save states

Move or delete the folder and the whole app goes with it.
