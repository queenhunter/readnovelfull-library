"""Desktop browser and GUI for Read_Novel_Full_V2_8.py.

Install dependencies with: python -m pip install PySide6 requests beautifulsoup4
Run with: python ReadNovelFull_GUI.py
"""
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from PySide6.QtCore import QObject, QThread, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QSpinBox, QStatusBar, QTabWidget, QVBoxLayout, QWidget,
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
NOVELHALL_DOWNLOADER_FILE = RESOURCE_DIR / "Novel Hall V1.0.py"
DEFAULT_OUTPUT_DIR = Path.home() / "Documents" / "ReadNovelFull"
DEFAULT_SITE = "https://readnovelfull.com/"
NOVELHALL_SITE = "https://www.novelhall.com/"
APP_VERSION = "1.0.3"
GITHUB_REPOSITORY = "queenhunter/readnovelfull-library"
GITHUB_LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
SETTINGS_FILE = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "ReadNovelFull" / "settings.json"
DEFAULT_SETTINGS = {
    "output_dir": str(DEFAULT_OUTPUT_DIR),
    "formats": ["EPUB", "TXT"],
    "download_mode": 0,
    "check_updates": True,
}


def load_settings():
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        settings = dict(DEFAULT_SETTINGS)
        settings.update(data if isinstance(data, dict) else {})
        settings["formats"] = [fmt for fmt in settings.get("formats", []) if fmt in {"EPUB", "TXT", "PDF"}]
        if not settings["formats"]:
            settings["formats"] = ["EPUB", "TXT"]
        try:
            settings["download_mode"] = min(2, max(0, int(settings.get("download_mode", 0))))
        except (TypeError, ValueError):
            settings["download_mode"] = 0
        return settings
    except (OSError, ValueError, TypeError):
        return dict(DEFAULT_SETTINGS)


def save_settings(settings):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def version_tuple(value):
    match = re.search(r"(\d+(?:\.\d+)+)", str(value))
    return tuple(int(part) for part in match.group(1).split(".")) if match else (0,)


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


def load_script(path, module_name):
    import importlib.util

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Couldn't load downloader script: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_clean_chapters(txt_paths):
    """Read cleaned files as ordered chapter title/body pairs."""
    heading = re.compile(r"(?im)^\s*(Chapter\s+\d+\b[^\r\n]*)\s*$")
    chapters = []
    for txt_path in sorted(txt_paths):
        text = Path(txt_path).read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            continue
        matches = list(heading.finditer(text))
        if matches:
            for index, match in enumerate(matches):
                end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
                chapters.append((match.group(1).strip(), text[match.end():end].strip()))
            continue
        blocks = [part.strip() for part in re.split(r"\n{3,}", text) if part.strip()]
        for block in blocks:
            lines = block.splitlines()
            chapters.append((f"Chapter {len(chapters) + 1}", block if len(lines) == 1 else "\n".join(lines[1:]).strip()))
    if not chapters:
        raise RuntimeError("No cleaned chapters were available to export.")
    return chapters


def render_chapters(novel_title, chapters):
    parts = [novel_title.strip(), ""]
    for title, body in chapters:
        parts.extend([title.strip(), "", body.strip(), ""])
    return "\n".join(parts).rstrip() + "\n"


def read_cover_image(cover_path):
    """Return validated cover bytes, filename, and media type for an image file."""
    if not cover_path:
        return None
    path = Path(cover_path)
    try:
        data = path.read_bytes()
    except OSError:
        return None
    signatures = (
        (b"\xff\xd8\xff", ".jpg", "image/jpeg"),
        (b"\x89PNG\r\n\x1a\n", ".png", "image/png"),
        (b"GIF8", ".gif", "image/gif"),
        (b"RIFF", ".webp", "image/webp"),
    )
    for signature, extension, media_type in signatures:
        if data.startswith(signature):
            if extension == ".webp" and data[8:12] != b"WEBP":
                continue
            return data, f"cover{extension}", media_type
    return None


def make_epub_from_chapters(novel_title, chapters, destination, cover_path=None):
    """Create an EPUB 3 batch with its cover image when available."""
    from datetime import datetime, timezone
    from xml.sax.saxutils import escape
    import uuid
    import zipfile

    uid = f"urn:uuid:{uuid.uuid4()}"
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>']
    spine, nav, chapter_files = [], [], []
    cover = read_cover_image(cover_path)
    if cover:
        cover_bytes, cover_name, cover_media_type = cover
        manifest.append(f'<item id="cover-image" href="{cover_name}" media-type="{cover_media_type}" properties="cover-image"/>')
        manifest.append('<item id="cover-page" href="cover.xhtml" media-type="application/xhtml+xml"/>')
        spine.append('<itemref idref="cover-page" linear="yes"/>')
        cover_xhtml = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
            f'<head><title>{escape(novel_title)}</title></head>'
            f'<body epub:type="cover"><img src="{cover_name}" alt="{escape(novel_title)} cover"/></body></html>'
        )
        chapter_files.append((f"OEBPS/{cover_name}", cover_bytes))
        chapter_files.append(("OEBPS/cover.xhtml", cover_xhtml))
    for index, (title, text) in enumerate(chapters, 1):
        name = f"ch{index:05d}.xhtml"
        manifest.append(f'<item id="ch{index}" href="{name}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="ch{index}"/>')
        nav.append(f'<li><a href="{name}">{escape(title)}</a></li>')
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        if not paragraphs:
            paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
        body = "".join("<p>" + "<br/>".join(escape(line) for line in p.splitlines()) + "</p>" for p in paragraphs)
        chapter_files.append((f"OEBPS/{name}",
            f'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>{escape(title)}</title></head><body><h1>{escape(title)}</h1>{body}</body></html>'))
    package = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="bookid">{uid}</dc:identifier><dc:title>{escape(novel_title)}</dc:title>'
        '<dc:language>en</dc:language>'
        f'<meta property="dcterms:modified">{modified}</meta></metadata><manifest>'
        + "".join(manifest) + '</manifest><spine>' + "".join(spine) + '</spine></package>'
    )
    nav_doc = ('<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
        f'<head><title>{escape(novel_title)}</title></head><body><nav epub:type="toc"><h1>Contents</h1><ol>'
        + "".join(nav) + '</ol></nav></body></html>')
    container = ('<?xml version="1.0" encoding="UTF-8"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
    with zipfile.ZipFile(destination, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("OEBPS/content.opf", package)
        archive.writestr("OEBPS/nav.xhtml", nav_doc)
        for name, content in chapter_files:
            archive.writestr(name, content)
    return str(destination)


def make_pdf_from_chapters(novel_title, chapters, destination, cover_path=None):
    import io

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Image as ReportLabImage, PageBreak, Paragraph, SimpleDocTemplate, Spacer
        from xml.sax.saxutils import escape
    except ImportError as exc:
        raise RuntimeError("PDF export needs ReportLab. Install reportlab and rebuild the app.") from exc
    from reportlab.lib.units import inch

    doc = SimpleDocTemplate(str(destination), pagesize=A4, title=novel_title)
    styles = getSampleStyleSheet()
    story = []
    cover = read_cover_image(cover_path)
    if cover:
        cover_bytes, _cover_name, _cover_media_type = cover
        cover_image = ReportLabImage(io.BytesIO(cover_bytes), width=4.2 * inch, height=5.8 * inch, kind="proportional")
        cover_image.hAlign = "CENTER"
        story.extend([cover_image, Spacer(1, 16), Paragraph(escape(novel_title), styles["Title"]), PageBreak()])
    else:
        story.extend([Paragraph(escape(novel_title), styles["Title"]), Spacer(1, 16)])
    for index, (title, text) in enumerate(chapters):
        story.append(Paragraph(escape(title), styles["Heading2"]))
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        if not paragraphs:
            paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
        for paragraph in paragraphs:
            story.append(Paragraph("<br/>".join(escape(line) for line in paragraph.splitlines()), styles["BodyText"]))
            story.append(Spacer(1, 7))
        if index + 1 < len(chapters):
            story.append(PageBreak())
    doc.build(story)
    return str(destination)


class BrowserPage(QWebEnginePage):
    """Open links in the same browser view instead of an unhandled popup."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.newWindowRequested.connect(self._open_requested_url)

    @Slot(object)
    def _open_requested_url(self, request):
        request.openIn(self)


class DownloadWorker(QObject):
    progress = Signal(int, int, str, str)
    status = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, source, novel_url, chapter_limit, output_dir, formats, batch_size):
        super().__init__()
        self.source = source
        self.novel_url = novel_url
        self.novel_id = novel_url
        self.chapter_limit = chapter_limit
        self.output_dir = Path(output_dir)
        self.formats = list(formats)
        self.batch_size = batch_size

    @staticmethod
    def _download_novelhall_cover(novel_url, novel_title, headers, work_dir):
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError:
            return None
        response = requests.get(novel_url, headers=headers, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        image_url = None
        for selector in (
            'meta[property="og:image"]',
            'meta[name="og:image"]',
            ".novel-cover img",
            ".book-cover img",
            "img.cover",
            "img[src]",
        ):
            node = soup.select_one(selector)
            if not node:
                continue
            candidate = node.get("content") or node.get("data-src") or node.get("src")
            if candidate and not candidate.startswith("data:"):
                image_url = urljoin(novel_url, candidate)
                if selector != "img[src]":
                    break
                alt = (node.get("alt") or "").lower()
                if any(word in alt for word in ("cover", "novel", "book")):
                    break
                image_url = None
        if not image_url:
            return None
        image = requests.get(image_url, headers=headers, timeout=20)
        image.raise_for_status()
        destination = work_dir / "novel-cover"
        destination.write_bytes(image.content)
        return str(destination) if read_cover_image(destination) else None

    @Slot()
    def run(self):
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        old_output_dir = os.environ.get("READNOVEL_OUTPUT_DIR")
        old_novelhall_dir = os.environ.get("NOVELHALL_OUTPUT_DIR")
        old_cwd = Path.cwd()
        old_novelhall_base_dir = None
        work_dir = None
        work_parent = None

        class QuietWriter:
            def write(self, text):
                return len(str(text))

            def flush(self):
                pass

            def isatty(self):
                return False

        quiet_writer = QuietWriter()
        result_path = None
        error_message = None
        try:
            # Keep all intermediate chapter and conversion files out of the visible folder.
            local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            if os.name == "nt" and local_app_data.drive.upper() != "C:":
                profile_name = os.environ.get("USERNAME", Path.home().name)
                local_app_data = Path("C:/Users") / profile_name / "AppData" / "Local"
            work_parent = local_app_data / "ReadNovelFull" / "work"
            work_parent.mkdir(parents=True, exist_ok=True)
            sys.stdout = quiet_writer
            sys.stderr = quiet_writer
            work_dir = Path(tempfile.mkdtemp(prefix=f"novel-{self.novel_id}-", dir=work_parent))
            os.environ["READNOVEL_OUTPUT_DIR"] = str(work_dir)
            os.environ["NOVELHALL_OUTPUT_DIR"] = str(work_dir)
            if self.source == "novelhall":
                module = load_script(NOVELHALL_DOWNLOADER_FILE, "novelhall_downloader")
                old_novelhall_base_dir = module.BASE_DIR
                module.BASE_DIR = str(work_dir)
                module.HTML_DIR = str(work_dir / "html")
                module.TXT_DIR = str(work_dir / "chapters")
                module.MERGED_DIR = str(work_dir / "merged")
                module.FAILED_DIR = str(work_dir / "failed")
                module.CLEAN_DIR = str(work_dir / "clean_novel")
                for folder in (module.HTML_DIR, module.TXT_DIR, module.MERGED_DIR, module.FAILED_DIR, module.CLEAN_DIR):
                    Path(folder).mkdir(parents=True, exist_ok=True)
                module.BASE_URL = "https://www.novelhall.com"
                module.HEADERS = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
                }
                novel_id = self.novel_url.split("#", 1)[0].split("?", 1)[0]
                if (urlparse(novel_id).hostname or "").lower() not in {"www.novelhall.com", "novelhall.com"}:
                    raise ValueError("Open a novel page on novelhall.com before downloading.")
                self.status.emit("Finding chapters…")
                novel_title = module.get_novel_title(novel_id, module.HEADERS)
                links = module.get_chapter_links(novel_id, module.HEADERS)
                cover_path = self._download_novelhall_cover(novel_id, novel_title, module.HEADERS, work_dir)
                clean_dir = Path(module.CLEAN_DIR)
            else:
                module = load_downloader()
                match = re.search(r"/novel-(\d+)(?:\.html)?", self.novel_url, flags=re.I)
                novel_id = int(match.group(1)) if match else self.novel_url
                module.NOVEL_ID = novel_id
                module.CHAPTER_LIST_URL = f"{module.BASE_URL}/ajax/chapter-archive?novelId={novel_id}"
                module.HEADERS = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                    "Referer": f"{module.BASE_URL}/novel-{novel_id}.html",
                    "X-Requested-With": "XMLHttpRequest",
                }
                self.status.emit("Finding chapters…")
                novel_title = module.get_novel_title(novel_id, module.CHAPTER_LIST_URL)
                links = module.get_chapter_links(module.CHAPTER_LIST_URL)
                cover_path = module.download_cover(novel_id, novel_title)
                clean_dir = None
            if self.chapter_limit > 0:
                links = links[:self.chapter_limit]
            if not links:
                raise RuntimeError("No chapters were found for this novel. Check the page and try again.")

            start_time = time.monotonic()
            last_completed = 0

            def report_progress(current, total, event):
                nonlocal last_completed
                elapsed = time.monotonic() - start_time
                if event == "finished":
                    last_completed = current
                remaining = max(0, total - last_completed)
                eta = (elapsed / last_completed * remaining) if last_completed else None
                self.progress.emit(
                    last_completed, total, "" if eta is None else str(int(eta)), str(current)
                )

            if self.source == "novelhall":
                module.download_chapters(links, chapter_limit=0, progress_callback=report_progress)
                self.status.emit("Preparing text files…")
                renamed = module.rename_html_files()
                txts = module.convert_html_to_txt(renamed)
                module.merge_txt_files(txts, novel_title)
                module.cleanup_files()
                module.clean_merged_files()
                epub_path = None
                clean_dir = Path(module.CLEAN_DIR)
            else:
                module.download_chapters(links, progress_callback=report_progress)
                self.status.emit("Preparing text files…")
                renamed = module.rename_html_files()
                txts = module.convert_html_to_txt(renamed)
                module.merge_txt_files(txts, novel_title)
                module.cleanup_files()
                module.clean_merged_files(novel_title)
                epub_path = None
                clean_dir = Path(module.novel_clean_dir(novel_title))

            safe_title = "".join(c for c in novel_title if c not in r'\\/:*?"<>|').strip() or "novel"
            novel_output = self.output_dir / safe_title
            novel_output.mkdir(parents=True, exist_ok=True)
            copied = []
            txt_paths = sorted(clean_dir.glob("*.txt"))
            chapters = read_clean_chapters(txt_paths)
            batch_size = self.batch_size if self.batch_size > 0 else len(chapters)
            batches = [chapters[index:index + batch_size] for index in range(0, len(chapters), batch_size)]
            total_batches = len(batches)

            # Remove stale exports from prior runs using the same output naming scheme.
            for existing in novel_output.iterdir():
                if not existing.is_file():
                    continue
                if existing.name.casefold() in {f"{safe_title}.txt".casefold(), f"{safe_title}.epub".casefold(), f"{safe_title}.pdf".casefold()}:
                    existing.unlink()
                elif re.fullmatch(rf"{re.escape(safe_title)} Chapters \d{{4}}-\d{{4}}\.(?:txt|epub|pdf)", existing.name, flags=re.I):
                    existing.unlink()

            for batch_index, batch in enumerate(batches, start=1):
                start_chapter = (batch_index - 1) * batch_size + 1
                end_chapter = start_chapter + len(batch) - 1
                range_label = f"Chapters {start_chapter:04d}-{end_chapter:04d}"
                if total_batches == 1 and self.batch_size == 0:
                    file_stem = safe_title
                else:
                    file_stem = f"{safe_title} {range_label}"

                if "TXT" in self.formats:
                    txt_output = novel_output / f"{file_stem}.txt"
                    txt_output.write_text(render_chapters(novel_title, batch), encoding="utf-8")
                    copied.append(txt_output)
                if "EPUB" in self.formats:
                    self.status.emit(f"Creating EPUB {batch_index} of {total_batches}…")
                    epub_output = novel_output / f"{file_stem}.epub"
                    make_epub_from_chapters(novel_title, batch, epub_output, cover_path)
                    copied.append(epub_output)
                if "PDF" in self.formats:
                    self.status.emit(f"Creating PDF {batch_index} of {total_batches}…")
                    pdf_output = novel_output / f"{file_stem}.pdf"
                    make_pdf_from_chapters(novel_title, batch, pdf_output, cover_path)
                    copied.append(pdf_output)

            if not copied:
                raise RuntimeError("No files were created. Select at least one supported format.")
            result_path = str(novel_output)
        except Exception as exc:
            error_message = str(exc)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            try:
                os.chdir(old_cwd)
            except OSError:
                pass
            if old_output_dir is None:
                os.environ.pop("READNOVEL_OUTPUT_DIR", None)
            else:
                os.environ["READNOVEL_OUTPUT_DIR"] = old_output_dir
            if old_novelhall_dir is None:
                os.environ.pop("NOVELHALL_OUTPUT_DIR", None)
            else:
                os.environ["NOVELHALL_OUTPUT_DIR"] = old_novelhall_dir
            if old_novelhall_base_dir is not None:
                try:
                    module.BASE_DIR = old_novelhall_base_dir
                    module.HTML_DIR = os.path.join(old_novelhall_base_dir, "html")
                    module.TXT_DIR = os.path.join(old_novelhall_base_dir, "chapters")
                    module.MERGED_DIR = os.path.join(old_novelhall_base_dir, "merged")
                    module.FAILED_DIR = os.path.join(old_novelhall_base_dir, "failed")
                    module.CLEAN_DIR = os.path.join(old_novelhall_base_dir, "clean_novel")
                except Exception:
                    pass
            if work_dir and work_dir.exists():
                try:
                    shutil.rmtree(work_dir)
                except Exception:
                    error_message = "The output may have been created, but temporary files could not be removed. Close apps using the download folder and retry."
            if work_parent and work_parent.exists():
                try:
                    work_parent.rmdir()
                    work_parent.parent.rmdir()
                except OSError:
                    pass
        if error_message:
            self.failed.emit(error_message)
        elif result_path:
            self.finished.emit(result_path)


class UpdateCheckWorker(QObject):
    result = Signal(str, str)

    @Slot()
    def run(self):
        request = urllib.request.Request(
            GITHUB_LATEST_RELEASE_API,
            headers={"User-Agent": "ReadNovelFull-Library", "Accept": "application/vnd.github+json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                release = json.loads(response.read().decode("utf-8"))
            tag = str(release.get("tag_name", "")).strip()
            release_url = str(release.get("html_url", "")).strip()
            if tag and release_url and version_tuple(tag) > version_tuple(APP_VERSION):
                self.result.emit(tag, release_url)
            else:
                self.result.emit("", "")
        except Exception:
            # Update checks are optional; network or API failures must not stop app startup.
            self.result.emit("", "")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ReadNovelFull Library")
        self.resize(1360, 880)
        self._download_thread = None
        self._worker = None
        self._update_thread = None
        self._update_worker = None
        self.settings = load_settings()
        self._build_ui()
        QApplication.styleHints().colorSchemeChanged.connect(self._apply_style)
        self.browser.setUrl(QUrl(DEFAULT_SITE))
        self.novelhall_browser.setUrl(QUrl(NOVELHALL_SITE))
        if self.settings.get("check_updates", True):
            self._check_for_updates_async()

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
        self.browser_tabs = QTabWidget()
        self.browser_tabs.setDocumentMode(True)
        controls.addWidget(self.back_button)
        controls.addWidget(self.forward_button)
        controls.addWidget(self.reload_button)

        self.address = QLineEdit()
        self.address.setPlaceholderText("Enter a ReadNovelFull or NovelHall page address")
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
        self.download_mode = QComboBox()
        self.download_mode.addItems(["All · one file", "All · 100 chapters/file", "Custom"])
        self.download_mode.setCurrentIndex(self.settings.get("download_mode", 0))
        self.download_mode.setFixedWidth(196)
        self.download_mode.currentIndexChanged.connect(self._download_mode_changed)
        self.download_mode.setToolTip("Choose one complete file, batches of 100 chapters, or a custom chapter count.")
        actions.addWidget(self.download_mode)
        self.chapter_limit = QSpinBox()
        self.chapter_limit.setRange(1, 100000)
        self.chapter_limit.setValue(20)
        self.chapter_limit.setFixedWidth(100)
        self.chapter_limit.setPrefix("First ")
        self.chapter_limit.setSuffix(" ch.")
        self.chapter_limit.setToolTip("Number of chapters to download when Custom is selected.")
        self.chapter_limit.setEnabled(self.download_mode.currentIndex() == 2)
        actions.addWidget(self.chapter_limit)
        self.open_folder_button = self._button("Output folder", "QuietButton")
        self.open_folder_button.clicked.connect(self.choose_output_dir)
        actions.addWidget(self.open_folder_button)
        self.output_label = QLabel(self.settings.get("output_dir", str(DEFAULT_OUTPUT_DIR)))
        self.output_label.setObjectName("pathLabel")
        self.output_label.setTextInteractionFlags(self.output_label.textInteractionFlags())
        self.output_label.setToolTip(self.output_label.text())
        actions.addWidget(self.output_label, 1)
        self.settings_button = self._button("Settings", "QuietButton")
        self.settings_button.clicked.connect(self.open_settings)
        actions.addWidget(self.settings_button)
        bar.addLayout(actions)

        self.browser = QWebEngineView()
        self.browser.setPage(BrowserPage(self.browser))
        self.novelhall_browser = QWebEngineView()
        self.novelhall_browser.setPage(BrowserPage(self.novelhall_browser))
        self.browser_tabs.addTab(self.browser, "ReadNovelFull")
        self.browser_tabs.addTab(self.novelhall_browser, "NovelHall")
        self.browser_tabs.currentChanged.connect(self._source_tab_changed)
        self.browser.urlChanged.connect(lambda url: self._url_changed(url, self.browser))
        self.novelhall_browser.urlChanged.connect(lambda url: self._url_changed(url, self.novelhall_browser))
        self.browser.loadStarted.connect(lambda: self.site_note.setText("Loading page…"))
        self.novelhall_browser.loadStarted.connect(lambda: self.site_note.setText("Loading NovelHall…"))
        self.browser.loadFinished.connect(self._load_finished)
        self.novelhall_browser.loadFinished.connect(self._load_finished)

        progress_panel = QWidget()
        progress_panel.setObjectName("progressPanel")
        progress_layout = QVBoxLayout(progress_panel)
        progress_layout.setContentsMargins(24, 14, 24, 16)
        progress_layout.setSpacing(8)
        progress_header = QHBoxLayout()
        self.progress_text = QLabel("Ready to download")
        self.progress_text.setObjectName("progressText")
        progress_header.addWidget(self.progress_text)
        progress_header.addStretch(1)
        self.eta_label = QLabel("")
        self.eta_label.setObjectName("etaLabel")
        progress_header.addWidget(self.eta_label)
        progress_layout.addLayout(progress_header)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("downloadProgress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(9)
        self.progress_bar.setInvertedAppearance(QApplication.layoutDirection() == Qt.LayoutDirection.RightToLeft)
        progress_layout.addWidget(self.progress_bar)

        page.addWidget(top)
        page.addWidget(self.browser_tabs, 1)
        page.addWidget(progress_panel)
        self.setCentralWidget(root)
        status = QStatusBar()
        self.setStatusBar(status)
        status.showMessage("Ready")
        self._apply_style()

    def _check_for_updates_async(self):
        if self._update_thread is not None:
            return
        self._update_thread = QThread(self)
        self._update_worker = UpdateCheckWorker()
        self._update_worker.moveToThread(self._update_thread)
        self._update_thread.started.connect(self._update_worker.run)
        self._update_worker.result.connect(self._update_check_finished)
        self._update_worker.result.connect(self._update_thread.quit)
        self._update_thread.finished.connect(self._update_worker.deleteLater)
        self._update_thread.finished.connect(self._update_thread_finished)
        self._update_thread.start()

    @Slot(str, str)
    def _update_check_finished(self, version, release_url):
        if not version or not release_url:
            return
        answer = QMessageBox.question(
            self,
            "Update available",
            f"ReadNovelFull Library {version} is available. Your current version is {APP_VERSION}.\\n\\nOpen the GitHub release page?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            webbrowser.open(release_url)

    @Slot()
    def _update_thread_finished(self):
        self._update_thread = None
        self._update_worker = None

    @staticmethod
    def _button(text, object_name, tooltip=None):
        button = QPushButton(text)
        button.setObjectName(object_name)
        if tooltip:
            button.setToolTip(tooltip)
        return button

    def _apply_style(self):
        palette = QApplication.palette()
        scheme = QApplication.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Unknown:
            dark = palette.color(QPalette.ColorRole.Window).lightness() < 128
        else:
            dark = scheme == Qt.ColorScheme.Dark
        if dark:
            colors = {
                "window": "#1d2527", "panel": "#252f31", "text": "#e4ece8",
                "muted": "#a6b7b1", "line": "#39494a", "field": "#182123",
                "quiet": "#344446", "quiet_hover": "#405556", "accent": "#5bb69a",
                "accent_hover": "#73c9ac", "track": "#39494a", "status": "#252f31",
            }
        else:
            colors = {
                "window": "#e9edf0", "panel": "#f8faf9", "text": "#193438",
                "muted": "#607579", "line": "#d6e0dc", "field": "#ffffff",
                "quiet": "#e8efed", "quiet_hover": "#d9e7e1", "accent": "#246a5d",
                "accent_hover": "#1c594f", "track": "#d5e1dc", "status": "#dfe7e3",
            }
        self.setStyleSheet(f"""
            QMainWindow {{ background: {colors['window']}; color: {colors['text']}; }}
            QWidget#topbar, QWidget#progressPanel {{ background: {colors['panel']}; }}
            QTabWidget::pane {{ border: 0; }}
            QTabBar::tab {{ color: {colors['muted']}; background: {colors['quiet']}; padding: 9px 16px; }}
            QTabBar::tab:selected {{ color: {colors['text']}; background: {colors['panel']}; }}
            QLabel#title {{ color: {colors['text']}; font: 700 23px 'Segoe UI'; }}
            QLabel#subtitle, QLabel#siteNote, QLabel#etaLabel {{ color: {colors['muted']}; font: 13px 'Segoe UI'; }}
            QLabel#progressText {{ color: {colors['text']}; font: 600 13px 'Segoe UI'; }}
            QWidget#rule {{ background: {colors['line']}; }}
            QLabel#pathLabel {{ color: {colors['muted']}; font: 11px 'Segoe UI'; }}
            QLineEdit, QSpinBox, QComboBox {{ background: {colors['field']}; color: {colors['text']};
                border: 1px solid {colors['line']}; border-radius: 5px; padding: 9px 11px;
                selection-background-color: {colors['accent']}; }}
            QComboBox::drop-down {{ border: 0; width: 22px; }}
            QPushButton {{ border: 0; border-radius: 5px; padding: 9px 13px; font: 600 12px 'Segoe UI'; }}
            QPushButton#QuietButton {{ color: {colors['text']}; background: {colors['quiet']}; }}
            QPushButton#QuietButton:hover {{ background: {colors['quiet_hover']}; }}
            QPushButton#PrimaryButton {{ color: #ffffff; background: {colors['accent']}; padding-left: 17px; padding-right: 17px; }}
            QPushButton#PrimaryButton:hover {{ background: {colors['accent_hover']}; }}
            QPushButton:disabled {{ color: {colors['muted']}; background: {colors['quiet']}; }}
            QProgressBar#downloadProgress {{ background: {colors['track']}; border: 0; border-radius: 4px; }}
            QProgressBar#downloadProgress::chunk {{ background: {colors['accent']}; border-radius: 4px; }}
            QStatusBar {{ background: {colors['status']}; color: {colors['muted']}; }}
        """)

    def _active_browser(self):
        return self.novelhall_browser if self.browser_tabs.currentIndex() == 1 else self.browser

    def _source_tab_changed(self, index):
        browser = self._active_browser()
        self.address.setText(browser.url().toString())
        self.site_note.setText("NovelHall browser ready" if index == 1 else "Browser ready")

    def _url_changed(self, url, browser=None):
        if browser is None or browser is self._active_browser():
            self.address.setText(url.toString())

    def _load_finished(self, ok):
        self.site_note.setText("Page ready" if ok else "Page could not load")

    def navigate(self):
        text = self.address.text().strip()
        if not text:
            return
        if not re.match(r"^https?://", text, flags=re.I):
            text = "https://" + text
        browser = self._active_browser()
        parsed = urlparse(text)
        host = (parsed.hostname or "").lower()
        if self.browser_tabs.currentIndex() == 0 and host.endswith("novelhall.com"):
            self.browser_tabs.setCurrentIndex(1)
            browser = self.novelhall_browser
        elif self.browser_tabs.currentIndex() == 1 and host.endswith("readnovelfull.com"):
            self.browser_tabs.setCurrentIndex(0)
            browser = self.browser
        browser.setUrl(QUrl(text))

    def browser_back(self):
        self._active_browser().back()

    def browser_forward(self):
        self._active_browser().forward()

    def browser_reload(self):
        self._active_browser().reload()

    def _novel_id_from_current_url(self):
        url = self._active_browser().url().toString()
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

    def _download_mode_changed(self, index):
        self.chapter_limit.setEnabled(index == 2)
        if hasattr(self, "settings"):
            self.settings["download_mode"] = index
            save_settings(self.settings)

    def choose_output_dir(self):
        start = self.output_label.text()
        folder = QFileDialog.getExistingDirectory(self, "Choose download folder", start)
        if folder:
            self.output_label.setText(folder)
            self.output_label.setToolTip(folder)
            self.settings["output_dir"] = folder
            save_settings(self.settings)

    def open_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        directory = QLineEdit(self.settings.get("output_dir", str(DEFAULT_OUTPUT_DIR)))
        browse = self._button("Browse…", "QuietButton")
        browse.clicked.connect(lambda: self._browse_settings_folder(directory))
        folder_row = QHBoxLayout()
        folder_row.addWidget(directory, 1)
        folder_row.addWidget(browse)
        form.addRow("Download folder", folder_row)
        layout.addLayout(form)
        layout.addWidget(QLabel("Export formats"))
        formats = {}
        for fmt in ("PDF", "EPUB", "TXT"):
            checkbox = QCheckBox(fmt)
            checkbox.setChecked(fmt in self.settings.get("formats", []))
            formats[fmt] = checkbox
            layout.addWidget(checkbox)
        update_check = QCheckBox("Notify me when a new app update is available")
        update_check.setChecked(bool(self.settings.get("check_updates", True)))
        layout.addWidget(update_check)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = self._button("Cancel", "QuietButton")
        cancel.clicked.connect(dialog.reject)
        save = self._button("Save settings", "PrimaryButton")
        save.clicked.connect(dialog.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        chosen_formats = [fmt for fmt, checkbox in formats.items() if checkbox.isChecked()]
        if not chosen_formats:
            QMessageBox.warning(self, "Choose a format", "Select at least one export format.")
            return
        output_dir = directory.text().strip() or str(DEFAULT_OUTPUT_DIR)
        self.settings.update({
            "output_dir": output_dir,
            "formats": chosen_formats,
            "check_updates": update_check.isChecked(),
        })
        save_settings(self.settings)
        self.output_label.setText(output_dir)
        self.output_label.setToolTip(output_dir)

    def _browse_settings_folder(self, line_edit):
        folder = QFileDialog.getExistingDirectory(self, "Choose download folder", line_edit.text())
        if folder:
            line_edit.setText(folder)

    def begin_download(self):
        if self._download_thread and self._download_thread.isRunning():
            return
        try:
            novel_url = self._active_browser().url().toString()
            source = "novelhall" if (urlparse(novel_url).hostname or "").lower().endswith("novelhall.com") else "readnovelfull"
            if source == "novelhall":
                if not re.search(r"/[^/]+-\d+/?$", urlparse(novel_url).path):
                    raise ValueError("Open a NovelHall novel page before downloading.")
                novel_id = novel_url
            else:
                novel_id = self._novel_id_from_current_url()
        except Exception as exc:
            QMessageBox.warning(self, "Can't start download", str(exc))
            return
        output_dir = self.output_label.text().strip()
        mode = self.download_mode.currentIndex()
        chapter_limit = self.chapter_limit.value() if mode == 2 else 0
        batch_size = 100 if mode == 1 else 0
        formats = list(self.settings.get("formats", ["EPUB", "TXT"]))
        if not formats:
            QMessageBox.warning(self, "Choose an export format", "Select at least one format in Settings.")
            return
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_text.setText("Finding chapters…")
        self.eta_label.clear()
        self.download_button.setEnabled(False)
        self.download_mode.setEnabled(False)
        self.chapter_limit.setEnabled(False)
        self.open_folder_button.setEnabled(False)
        self.settings_button.setEnabled(False)
        self.site_note.setText("Preparing download…")
        self._download_thread = QThread(self)
        self._worker = DownloadWorker(source, novel_url, chapter_limit, output_dir, formats, batch_size)
        self._worker.moveToThread(self._download_thread)
        self._download_thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._update_progress)
        self._worker.status.connect(self._update_status)
        self._worker.finished.connect(self._download_finished)
        self._worker.failed.connect(self._download_failed)
        self._worker.finished.connect(self._download_thread.quit)
        self._worker.failed.connect(self._download_thread.quit)
        self._download_thread.finished.connect(self._worker.deleteLater)
        self._download_thread.finished.connect(self._thread_finished)
        self._download_thread.start()

    @Slot(int, int, str, str)
    def _update_progress(self, completed, total, eta_seconds, active_chapter):
        if total <= 0:
            self.progress_bar.setValue(0)
            return
        percent = round(100 * completed / total)
        self.progress_bar.setValue(percent)
        current = min(total, int(active_chapter)) if active_chapter.isdigit() else completed
        self.progress_text.setText(f"Downloading chapter {current} of {total}")
        if eta_seconds:
            seconds = int(eta_seconds)
            if seconds >= 3600:
                estimate = f"About {seconds // 3600}h {(seconds % 3600) // 60}m left"
            elif seconds >= 60:
                estimate = f"About {seconds // 60}m left"
            else:
                estimate = f"About {seconds}s left"
            self.eta_label.setText(estimate)
        else:
            self.eta_label.setText("Estimating time…")

    @Slot(str)
    def _update_status(self, message):
        self.progress_text.setText(message)
        self.eta_label.clear()
        if message != "Finding chapters…":
            self.progress_bar.setRange(0, 0)

    @Slot(str)
    def _download_finished(self, path):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_text.setText("Download complete")
        formats = ", ".join(self.settings.get("formats", []))
        self.eta_label.setText(f"{formats} files are ready")
        self.site_note.setText("Download complete")
        self.statusBar().showMessage(f"Saved to {path}", 12000)

    @Slot(str)
    def _download_failed(self, message):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_text.setText("Download could not be completed")
        self.eta_label.clear()
        self.site_note.setText("Download failed")
        QMessageBox.critical(self, "Download failed", message.split("\n\n", 1)[0])

    @Slot()
    def _thread_finished(self):
        self.download_button.setEnabled(True)
        self.download_mode.setEnabled(True)
        self.chapter_limit.setEnabled(self.download_mode.currentIndex() == 2)
        self.open_folder_button.setEnabled(True)
        self.settings_button.setEnabled(True)
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
