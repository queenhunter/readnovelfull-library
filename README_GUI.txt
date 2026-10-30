ReadNovelFull Library — desktop browser and downloader

For the packaged Windows app, download and run ReadNovelFull-Setup-Windows-x64.exe from GitHub Releases. It installs the app and its Qt browser runtime and does not install dependencies at launch. See README_RELEASE.txt for release setup and publishing instructions.

For source development, install Python 3.12, the Python Launcher, and Inno Setup 6, then run build_windows.bat to create the Windows installer. To run directly from source, install the packages in requirements-build.txt and launch ReadNovelFull_GUI.py with Python.

Browse to a novel's main page on readnovelfull.com, choose All · one file, All · 100 chapters/file, or Custom, then click Download this novel. The 100-chapter option creates one numbered file per batch in each selected format. A 1,000-chapter novel produces ten files per selected format. The progress panel shows the current chapter, download progress, and estimated time remaining. The app follows the Windows light or dark appearance.

Exports are saved under Documents/ReadNovelFull/<Novel Title> by default. Use Settings to choose PDF, EPUB, and/or TXT and set the output folder. Chapter HTML and processing files are kept in a private temporary folder under your Windows user AppData and removed when the download finishes.

The original command-line downloader remains available. Its output directory can be configured with READNOVEL_OUTPUT_DIR, and without that setting it retains its original default.
