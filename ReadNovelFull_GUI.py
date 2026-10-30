"""Desktop browser and GUI for Read_Novel_Full_V2_8.py.

Install dependencies with: python -m pip install PySide6 requests beautifulsoup4
Run with: python ReadNovelFull_GUI.py
"""
import os
import re
import sys
import threading
import traceback
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QObject, QThread, QUrl, Signal, Slot
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QSpinBox, QStatusBar, QTextEdit,
    QVBoxLayout, QWidget,
)
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView

if getattr(sys, "frozen", False):
    # PyInstaller keeps bundled read-only resources in its extraction/resource folder.
    APP_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(sys._MEIPASS)
else:
    APP_DIR = Path(__file__).resolve().parent
    RESOURCE_DIR = APP_DIR
DOWNLOADER_FILE = RESOURCE_DIR / "Read_Novel_Full_V2_8.py"
DEFAULT_OUTPUT_DIR = Path.home() / "Documents" / "ReadNovelFull"
DEFAULT_SITE = "https://readnovelfull.com/"


def load_downloader():
    """Load the user's existing downloader as a module without invoking its CLI."""
    import importlib.util

    if not DOWNLOADER_FILE.is_file():
        raise FileNotFoundError(f"Downloader script not found: {DOWNLOADER_FILE}")
    spec = importlib.util.spec_from_file_location("readnovelfull_downloader", DOWNLOADER_FILE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class BrowserPage(QWebEnginePage):
    """Open links in the same browser view instead of an unhandled popup."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.newWindowRequested.connect(self._open_requested_url)

    @Slot(object)
    def _open_requested_url(self, request):
        request.openIn(self)


class DownloadWorker(QObject):
    log = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, novel_id, chapter_limit, output_dir):
        super().__init__()
        self.novel_id = novel_id
        self.chapter_limit = chapter_limit
        self.output_dir = output_dir

    @Slot()
    def run(self):
        old_stdout = sys.stdout

        class SignalWriter:
            def write(inner_self, text):
                text = str(text)
                if text.strip():
                    self.log.emit(text.rstrip())
                return len(text)

            def flush(inner_self):
                pass

        try:
            # Load in the worker thread so the module's global headers and network work
            # stay isolated from the browser UI thread.
            os.environ["READNOVEL_OUTPUT_DIR"] = self.output_dir
            module = load_downloader()
            sys.stdout = SignalWriter()
            module.NOVEL_ID = self.novel_id
            module.CHAPTER_LIST_URL = (
                f"{module.BASE_URL}/ajax/chapter-archive?novelId={self.novel_id}"
            )
            module.HEADERS = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": f"{module.BASE_URL}/novel-{self.novel_id}.html",
                "X-Requested-With": "XMLHttpRequest",
            }
            novel_title = module.get_novel_title(self.novel_id, module.CHAPTER_LIST_URL)
            links = module.get_chapter_links(module.CHAPTER_LIST_URL)
            if self.chapter_limit > 0:
                links = links[:self.chapter_limit]
                print(f"Chapter limit: downloading {len(links)} chapters.")
            if not links:
                raise RuntimeError("No chapter links were found. Check the novel page and try again.")
            module.download_chapters(links)
            renamed = module.rename_html_files()
            txts = module.convert_html_to_txt(renamed)
            module.merge_txt_files(txts, novel_title)
            module.cleanup_files()
            module.clean_merged_files(novel_title)
            cover_path = module.download_cover(self.novel_id, novel_title)
            epub_path = module.build_epub(novel_title, cover_path)
            self.finished.emit(str(epub_path or module.novel_clean_dir(novel_title)))
        except Exception as exc:
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")
        finally:
            sys.stdout = old_stdout


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ReadNovelFull Library")
        self.resize(1360, 880)
        self._download_thread = None
        self._worker = None
        self._build_ui()
        self.browser.setUrl(QUrl(DEFAULT_SITE))

    def _build_ui(self):
        root = QWidget()
        page = QVBoxLayout(root)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)

        top = QWidget()
        top.setObjectName("topbar")
        bar = QVBoxLayout(top)
        bar.setContentsMargins(24, 18, 24, 18)
        bar.setSpacing(14)

        masthead = QHBoxLayout()
        identity = QVBoxLayout()
        title = QLabel("ReadNovelFull Library")
        title.setObjectName("title")
        subtitle = QLabel("Browse a novel, then save a clean reading copy.")
        subtitle.setObjectName("subtitle")
        identity.addWidget(title)
        identity.addWidget(subtitle)
        masthead.addLayout(identity)
        masthead.addStretch(1)
        self.site_note = QLabel("Browser ready")
        self.site_note.setObjectName("siteNote")
        masthead.addWidget(self.site_note)
        bar.addLayout(masthead)

        controls = QHBoxLayout()
        controls.setSpacing(9)
        self.back_button = self._button("‹", "QuietButton", "Go back")
        self.back_button.clicked.connect(self.browser_back)
        self.forward_button = self._button("›", "QuietButton", "Go forward")
        self.forward_button.clicked.connect(self.browser_forward)
        self.reload_button = self._button("Reload", "QuietButton")
        self.reload_button.clicked.connect(self.browser_reload)
        controls.addWidget(self.back_button)
        controls.addWidget(self.forward_button)
        controls.addWidget(self.reload_button)

        self.address = QLineEdit()
        self.address.setPlaceholderText("Enter a ReadNovelFull page address")
        self.address.returnPressed.connect(self.navigate)
        controls.addWidget(self.address, 1)
        self.go_button = self._button("Open", "QuietButton")
        self.go_button.clicked.connect(self.navigate)
        controls.addWidget(self.go_button)
        bar.addLayout(controls)

        divider = QWidget()
        divider.setObjectName("rule")
        divider.setFixedHeight(1)
        bar.addWidget(divider)

        actions = QHBoxLayout()
        actions.setSpacing(11)
        self.download_button = self._button("Download this novel", "PrimaryButton")
        self.download_button.clicked.connect(self.begin_download)
        actions.addWidget(self.download_button)
        limit_label = QLabel("Chapter limit")
        limit_label.setObjectName("fieldLabel")
        actions.addWidget(limit_label)
        self.chapter_limit = QSpinBox()
        self.chapter_limit.setRange(0, 100000)
        self.chapter_limit.setSpecialValueText("All")
        self.chapter_limit.setValue(0)
        self.chapter_limit.setFixedWidth(112)
        self.chapter_limit.setToolTip("Set to All for every chapter, or choose a number to download a shorter sample.")
        actions.addWidget(self.chapter_limit)
        self.open_folder_button = self._button("Output folder", "QuietButton")
        self.open_folder_button.clicked.connect(self.choose_output_dir)
        actions.addWidget(self.open_folder_button)
        self.output_label = QLabel(str(DEFAULT_OUTPUT_DIR))
        self.output_label.setObjectName("pathLabel")
        self.output_label.setTextInteractionFlags(self.output_label.textInteractionFlags())
        self.output_label.setToolTip(str(DEFAULT_OUTPUT_DIR))
        actions.addWidget(self.output_label, 1)
        bar.addLayout(actions)

        self.browser = QWebEngineView()
        self.browser.setPage(BrowserPage(self.browser))
        self.browser.urlChanged.connect(self._url_changed)
        self.browser.loadStarted.connect(lambda: self.site_note.setText("Loading page…"))
        self.browser.loadFinished.connect(self._load_finished)

        self.log = QTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Download progress and saved files will appear here.")
        self.log.setMaximumHeight(178)

        page.addWidget(top)
        page.addWidget(self.browser, 1)
        page.addWidget(self.log)
        self.setCentralWidget(root)
        status = QStatusBar()
        self.setStatusBar(status)
        status.showMessage("Ready")
        self._apply_style()

    @staticmethod
    def _button(text, object_name, tooltip=None):
        button = QPushButton(text)
        button.setObjectName(object_name)
        if tooltip:
            button.setToolTip(tooltip)
        return button

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow { background: #e9edf0; color: #17282d; }
            QWidget#topbar { background: #f8faf9; }
            QLabel#title { color: #173b3b; font: 700 23px 'Segoe UI'; }
            QLabel#subtitle { color: #607579; font: 13px 'Segoe UI'; }
            QLabel#siteNote { color: #53706e; font: 12px 'Segoe UI'; }
            QWidget#rule { background: #d6e0dc; }
            QLabel#fieldLabel { color: #435c5e; font: 600 12px 'Segoe UI'; }
            QLabel#pathLabel { color: #6a7c7d; font: 11px 'Segoe UI'; }
            QLineEdit, QSpinBox { background: #fff; color: #193438; border: 1px solid #ccd8d4;
                border-radius: 5px; padding: 9px 11px; selection-background-color: #286c60; }
            QPushButton { border: 0; border-radius: 5px; padding: 9px 13px; font: 600 12px 'Segoe UI'; }
            QPushButton#QuietButton { color: #315153; background: #e8efed; }
            QPushButton#QuietButton:hover { background: #d9e7e1; }
            QPushButton#PrimaryButton { color: #fff; background: #246a5d; padding-left: 17px; padding-right: 17px; }
            QPushButton#PrimaryButton:hover { background: #1c594f; }
            QPushButton:disabled { color: #82928f; background: #e1e7e4; }
            QTextEdit#log { background: #152b2d; color: #d3e7dc; border: 0; padding: 11px 15px;
                font: 12px 'Cascadia Mono'; }
            QStatusBar { background: #dfe7e3; color: #435b5a; }
        """)

    def _url_changed(self, url):
        self.address.setText(url.toString())

    def _load_finished(self, ok):
        self.site_note.setText("Page ready" if ok else "Page could not load")

    def navigate(self):
        text = self.address.text().strip()
        if not text:
            return
        if not re.match(r"^https?://", text, flags=re.I):
            text = "https://" + text
        self.browser.setUrl(QUrl(text))

    def browser_back(self):
        self.browser.back()

    def browser_forward(self):
        self.browser.forward()

    def browser_reload(self):
        self.browser.reload()

    def _novel_id_from_current_url(self):
        url = self.browser.url().toString()
        host = (urlparse(url).hostname or "").lower()
        if host != "readnovelfull.com" and not host.endswith(".readnovelfull.com"):
            raise ValueError("Open a novel page on readnovelfull.com before downloading.")
        match = re.search(r"/novel-(\d+)(?:\.html)?", url, flags=re.I)
        if match:
            return int(match.group(1))
        # Download pages sometimes use a title slug instead of the numerical novel ID.
        import requests
        from bs4 import BeautifulSoup
        response = requests.get(url.split("#", 1)[0], headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
        }, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        id_tag = soup.find(attrs={"data-novel-id": True})
        if id_tag and str(id_tag.get("data-novel-id", "")).isdigit():
            return int(id_tag["data-novel-id"])
        for script in soup.find_all("script"):
            if script.string:
                found = re.search(r"(?:novelId|novel_id)\s*[=:]\s*(\d+)", script.string)
                if found:
                    return int(found.group(1))
        hidden = soup.find("input", {"name": re.compile(r"novel.?id", re.I)})
        if hidden and str(hidden.get("value", "")).isdigit():
            return int(hidden["value"])
        raise ValueError("I couldn't identify the novel ID from this page. Open its main novel page and try again.")

    def choose_output_dir(self):
        start = self.output_label.text()
        folder = QFileDialog.getExistingDirectory(self, "Choose download folder", start)
        if folder:
            self.output_label.setText(folder)
            self.output_label.setToolTip(folder)

    def begin_download(self):
        if self._download_thread and self._download_thread.isRunning():
            return
        try:
            novel_id = self._novel_id_from_current_url()
        except Exception as exc:
            QMessageBox.warning(self, "Can't start download", str(exc))
            return
        output_dir = self.output_label.text().strip()
        self.log.clear()
        self.log.append(f"Starting novel ID {novel_id}…")
        self.download_button.setEnabled(False)
        self.site_note.setText(f"Downloading novel {novel_id}…")
        self._download_thread = QThread(self)
        self._worker = DownloadWorker(novel_id, self.chapter_limit.value(), output_dir)
        self._worker.moveToThread(self._download_thread)
        self._download_thread.started.connect(self._worker.run)
        self._worker.log.connect(self.log.append)
        self._worker.finished.connect(self._download_finished)
        self._worker.failed.connect(self._download_failed)
        self._worker.finished.connect(self._download_thread.quit)
        self._worker.failed.connect(self._download_thread.quit)
        self._download_thread.finished.connect(self._worker.deleteLater)
        self._download_thread.finished.connect(self._thread_finished)
        self._download_thread.start()

    @Slot(str)
    def _download_finished(self, path):
        self.log.append(f"Finished. Output: {path}")
        self.site_note.setText("Download complete")
        self.statusBar().showMessage(f"Saved to {path}", 12000)

    @Slot(str)
    def _download_failed(self, message):
        self.log.append("Download stopped with an error:")
        self.log.append(message)
        self.site_note.setText("Download failed")
        QMessageBox.critical(self, "Download failed", message.split("\n\n", 1)[0])

    @Slot()
    def _thread_finished(self):
        self.download_button.setEnabled(True)
        self._download_thread = None
        self._worker = None

    def closeEvent(self, event):
        if self._download_thread and self._download_thread.isRunning():
            QMessageBox.information(
                self, "Download running",
                "The download is still running. Wait for it to finish before closing the app.",
            )
            event.ignore()
            return
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ReadNovelFull Library")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
