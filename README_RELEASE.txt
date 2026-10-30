ReadNovelFull Library for Windows

Install
1. Download ReadNovelFull-Setup-Windows-x64.exe from the GitHub Release.
2. Double-click it. It installs under your Windows user profile and does not normally ask for administrator access.
3. Start ReadNovelFull Library from the Start menu. A desktop shortcut is available as an installer option.
4. Browse to a novel's main page on readnovelfull.com, choose a chapter limit if wanted, then click Download this novel.

The installer contains the app, Python runtime, Python packages, and Qt WebEngine browser runtime. You do not need to install Python or download dependencies when using the app. Internet access is needed to browse and retrieve pages.

Output location
Files are saved under Documents\ReadNovelFull by default. Use the Output folder button to choose another location. The EPUB is in the epub subfolder and cleaned text is in clean_novel.

Build locally
On Windows, install Python 3.12 with the Python Launcher and install Inno Setup 6. Then double-click build_windows.bat. It creates release\ReadNovelFull-Setup-Windows-x64.exe. The build machine downloads dependencies; users running the installer do not need Python or package downloads.

Publish a GitHub Release
1. Push the project source to a GitHub repository.
2. Create and push a version tag, for example:
   git tag v1.0.0
   git push origin v1.0.0
3. GitHub Actions builds the Windows installer and attaches it to a GitHub Release. Check the Actions run and release asset after it finishes.

Running the workflow manually from the Actions tab creates a downloadable installer artifact; it only publishes a GitHub Release when triggered by a v-prefixed tag. A manually started run asks for an installer version.

Keep the repository limited to source code, build configuration, and documentation. Do not commit downloaded novels, chapter HTML, EPUBs, or cover images unless you have permission to redistribute them. Use the website only in ways permitted by its terms and applicable rights. The app does not bypass sign-in, access controls, or site restrictions.
