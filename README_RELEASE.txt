ReadNovelFull Library for Windows

Quick start
1. Download the ZIP from the GitHub Release and extract the entire folder.
2. Double-click ReadNovelFull.exe in the extracted folder.
3. Browse to a novel's main page on readnovelfull.com, select a chapter limit if wanted, and click Download this novel.

The release contains the Python runtime, Python packages, and Qt WebEngine browser runtime. You do not need to install Python or download dependencies on first launch. Internet access is needed to browse and retrieve pages. The ZIP includes THIRD_PARTY_NOTICES.txt with upstream licensing links for bundled components.

Output location
Files are saved under Documents\ReadNovelFull by default. Use the Output folder button to choose another location. The EPUB is in the epub subfolder and cleaned text is in clean_novel.

Build on Windows
Install Python 3.12 with the Python Launcher, then double-click build_windows.bat. It creates release\ReadNovelFull-Windows-x64.zip. The build machine downloads the dependencies; people running the packaged app do not.

Publish a GitHub Release
1. Push the project source to a GitHub repository.
2. Create and push a version tag, for example:
   git tag v1.0.0
   git push origin v1.0.0
3. GitHub Actions builds the Windows ZIP and attaches it to a GitHub Release. Check the Actions run and release asset after it finishes.

Running the workflow manually from the Actions tab creates a downloadable workflow artifact; it only publishes a GitHub Release when triggered by a v-prefixed tag.

Keep the repository limited to source code, build configuration, and documentation. Do not commit downloaded novels, chapter HTML, EPUBs, or cover images unless you have permission to redistribute them. Use the website only in ways permitted by its terms and applicable rights. The app does not bypass sign-in, access controls, or site restrictions.
