ReadNovelFull Library — desktop browser and downloader

For the packaged Windows app, open the GitHub Release ZIP, extract the entire folder, and run ReadNovelFull.exe. It includes Python packages and the Qt browser runtime; it does not install dependencies when launched. See README_RELEASE.txt for release setup and publishing instructions.

For source development, install Python 3.12 and the Python Launcher, then run build_windows.bat to create a Windows release ZIP. To run directly from source, install the packages in requirements-build.txt and launch ReadNovelFull_GUI.py with Python.

Browse to a novel's main page on readnovelfull.com, choose a chapter limit or leave it at All, then click Download this novel. Progress appears in the panel at the bottom.

Files are saved by default under Documents/ReadNovelFull. Use Output folder to choose another location. The EPUB is written to the epub subfolder; cleaned text files are in clean_novel.

The original command-line downloader remains available. Its output directory can be configured with READNOVEL_OUTPUT_DIR, and without that setting it retains its original default.
