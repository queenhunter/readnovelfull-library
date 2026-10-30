import os
import re
import time
import requests
from bs4 import BeautifulSoup
from glob import glob, escape as glob_escape
from pathlib import Path
import uuid
from urllib.parse import urljoin
import zipfile
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape

# ====== CONFIG ======
# The GUI can set READNOVEL_OUTPUT_DIR; the command-line version keeps its original default.
BASE_DIR = os.path.abspath(os.path.expanduser(
    os.environ.get("READNOVEL_OUTPUT_DIR", os.path.join(os.getcwd(), "readnovelfull"))
))
HTML_DIR = os.path.join(BASE_DIR, "html")
TXT_DIR = os.path.join(BASE_DIR, "chapters")
MERGED_DIR = os.path.join(BASE_DIR, "merged")
FAILED_DIR = os.path.join(BASE_DIR, "failed")
CLEAN_DIR = os.path.join(BASE_DIR, "clean_novel")
EPUB_DIR = os.path.join(BASE_DIR, "epub")
COVER_DIR = os.path.join(BASE_DIR, "cover")

BASE_URL = 'https://readnovelfull.com'

# ====== SETUP FOLDERS ======
for folder in [BASE_DIR, HTML_DIR, TXT_DIR, MERGED_DIR, FAILED_DIR, CLEAN_DIR, EPUB_DIR, COVER_DIR]:
    os.makedirs(folder, exist_ok=True)

# ====== FETCH NOVEL ID FROM URL ======
def fetch_novel_id_from_url(url, headers):
    print(f"   Fetching page: {url}")
    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f"   Status: {r.status_code}")
        if r.status_code != 200:
            print(f"   ❌ Could not fetch page.")
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        # Method 1: data-novel-id attribute
        tag = soup.find(attrs={"data-novel-id": True})
        if tag:
            novel_id = tag["data-novel-id"].strip()
            print(f"✅ Found Novel ID via data-novel-id: {novel_id}")
            return int(novel_id)

        # Method 2: JavaScript variable novelId or novel_id
        script_tags = soup.find_all("script")
        for script in script_tags:
            if script.string:
                m = re.search(r'(?:novelId|novel_id)\s*[=:]\s*(\d+)', script.string)
                if m:
                    novel_id = m.group(1)
                    print(f"✅ Found Novel ID via JS variable: {novel_id}")
                    return int(novel_id)

        # Method 3: hidden input field
        hidden = soup.find("input", {"name": re.compile(r'novel.?id', re.I)})
        if hidden and hidden.get("value"):
            novel_id = hidden["value"].strip()
            print(f"✅ Found Novel ID via hidden input: {novel_id}")
            return int(novel_id)

        print("   ❌ Could not find Novel ID in page. Try entering it manually.")
        return None

    except Exception as e:
        print(f"   ❌ Error fetching URL: {e}")
        return None

# ====== NOVEL ID SELECTION ======
def select_novel_id():
    saved_id_file = os.path.join(BASE_DIR, "novel_id.txt")
    saved_id = None

    if os.path.exists(saved_id_file):
        with open(saved_id_file, "r") as f:
            saved_id = f.read().strip()

    print("\n" + "="*50)
    print("         READNOVELFULL DOWNLOADER")
    print("="*50)

    if saved_id:
        print(f"  Saved Novel ID: {saved_id}")
        print("  [1] Keep saved ID")
        print("  [2] Paste a novel URL")
        print("  [3] Enter ID manually")
        print("="*50)
        while True:
            choice = input("Select (1, 2 or 3): ").strip()
            if choice == "1":
                print(f"✅ Using saved Novel ID: {saved_id}\n")
                return int(saved_id)
            elif choice in ("2", "3"):
                break
            else:
                print("❌ Invalid choice. Enter 1, 2 or 3.")
    else:
        print("  [1] Paste a novel URL")
        print("  [2] Enter ID manually")
        print("="*50)
        while True:
            choice = input("Select (1 or 2): ").strip()
            if choice in ("1", "2"):
                # remap to consistent values for code below
                choice = "2" if choice == "1" else "3"
                break
            else:
                print("❌ Invalid choice. Enter 1 or 2.")

    # Temporary headers just for the URL fetch
    temp_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }

    if choice == "2":
        # URL mode
        while True:
            url = input("Paste novel URL: ").strip()
            if not url.startswith("http"):
                print("❌ Please paste a valid URL starting with http.")
                continue
            # Strip fragment (#tab-description-title etc.)
            url = url.split("#")[0]
            novel_id = fetch_novel_id_from_url(url, temp_headers)
            if novel_id:
                with open(saved_id_file, "w") as f:
                    f.write(str(novel_id))
                print(f"✅ Novel ID {novel_id} saved.\n")
                return novel_id
            else:
                retry = input("Could not get ID from URL. Try again? (y/n): ").strip().lower()
                if retry != "y":
                    print("Falling back to manual entry.")
                    break

    # Manual entry (choice == "3" or fallback)
    while True:
        try:
            novel_id = int(input("Enter Novel ID: ").strip())
            with open(saved_id_file, "w") as f:
                f.write(str(novel_id))
            print(f"✅ Novel ID {novel_id} saved.\n")
            return novel_id
        except ValueError:
            print("❌ Please enter a valid number.")

# ====== STEP 0: Get novel title dynamically with fallback ======
def get_novel_title(novel_id, chapter_list_url):
    print("📡 Fetching novel title...")
    global HEADERS
    novel_url = f'{BASE_URL}/novel-{novel_id}.html'
    novel_title = f"Novel ID {novel_id}"
    
    r = None
    try:
        print(f"   Attempting: {novel_url}")
        r = requests.get(novel_url, headers=HEADERS, timeout=10)
        print(f"   Status: {r.status_code}")
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            title_tag = soup.find("title") or soup.find("h1")
            if title_tag:
                raw_title = title_tag.get_text(strip=True)
                novel_title = raw_title.split(" - ")[0] if " - " in raw_title else raw_title
                print(f"✅ Novel Title: {novel_title}")
            else:
                print("   No title/h1 tag found in HTML.")
                print(f"   HTML snippet: {r.text[:200]}...")
        else:
            print(f"   Failed with status {r.status_code}. HTML snippet: {r.text[:200]}...")
    except Exception as e:
        print(f"   ❌ Novel page error: {e}")
    
    if "Novel ID" in novel_title:
        try:
            print("   Falling back to chapter list for title hint...")
            r = requests.get(chapter_list_url, headers=HEADERS, timeout=10)
            print(f"   Chapter list status: {r.status_code}")
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                first_link = soup.select_one("ul.list-chapter li a")
                if first_link and first_link.get("href"):
                    href = first_link["href"]
                    slug = href.split("/")[1].replace("-chapter-", "").replace(".html", "")
                    if slug and len(slug) > 5:
                        novel_title = slug.title().replace("-", " ")
                        print(f"✅ Fallback Title Hint: {novel_title}")
                    else:
                        print("   No useful slug in chapter links.")
                else:
                    print("   No chapter links found.")
            else:
                print(f"   Chapter list failed with status {r.status_code}.")
        except Exception as e:
            print(f"   ❌ Fallback error: {e}")
    
    title_file = os.path.join(BASE_DIR, "novel_title.txt")
    with open(title_file, "w", encoding="utf-8") as f:
        f.write(novel_title)
    print(f"💾 Saved title to: {title_file}")
    
    if r is not None and r.status_code == 200:
        HEADERS['Referer'] = novel_url
    
    return novel_title

# ====== STEP 1: Get chapter links ======
def get_chapter_links(chapter_list_url):
    print("📡 Fetching chapter list...")
    r = requests.get(chapter_list_url, headers=HEADERS)
    print(f"   Status: {r.status_code}")
    soup = BeautifulSoup(r.text, "html.parser")
    links = [BASE_URL + a["href"] for a in soup.select("ul.list-chapter li a")]
    links = links[::-1]
    print(f"✅ Found {len(links)} chapters.")
    return links

# ====== STEP 2: Download chapters ======
def download_chapters(links):
    print("⬇️ Downloading chapters...")
    for i, url in enumerate(links):
        filename = os.path.join(HTML_DIR, f"raw_{i+1:04d}.html")
        if os.path.exists(filename):
            continue
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            print(f"   Chapter {i+1} status: {r.status_code}")
            with open(filename, "w", encoding="utf-8") as f:
                f.write(r.text)
            print(f"✅ Saved: raw_{i+1:04d}.html")
            time.sleep(2)
        except Exception as e:
            print(f"❌ Failed to download {url}: {e}")
            if 'r' in locals():
                with open(os.path.join(FAILED_DIR, f"failed_{i+1:04d}.html"), "w", encoding="utf-8") as f:
                    f.write(r.text)

# ====== STEP 3: Rename from latest to earliest ======
def rename_html_files():
    print("🔀 Renaming HTML files (latest → earliest)...")
    html_files = sorted(glob(os.path.join(HTML_DIR, "raw_*.html")))
    html_files = html_files[::-1]

    renamed = {}
    for i, path in enumerate(html_files, start=1):
        new_name = os.path.join(HTML_DIR, f"chapter_{i:04d}.html")
        os.rename(path, new_name)
        renamed[i] = new_name

    print(f"✅ Renamed {len(renamed)} files.")
    return renamed

# ====== STEP 4: Convert HTML to TXT with simple chapter titles ======
def convert_html_to_txt(renamed_html):
    print("🧼 Converting HTML to clean TXT...")
    txt_paths = {}
    for i, html_path in renamed_html.items():
        with open(html_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        content_tag = (
            soup.select_one("div.chapter-c") or
            soup.select_one("div.chapter-content") or
            soup.find("div", class_="content") or
            soup.find("div", id="content") or
            soup.find("div")
        )

        if not content_tag:
            print(f"⚠️ Skipped chapter_{i:04d} — content missing.")
            with open(os.path.join(FAILED_DIR, f"chapter_{i:04d}_skipped.html"), "w", encoding="utf-8") as f:
                f.write(str(soup))
            continue

        title = f"Chapter {i}"  # Simple chapter title
        content = content_tag.get_text(separator="\n").strip()

        output_txt = os.path.join(TXT_DIR, f"chapter_{i:04d}.txt")
        with open(output_txt, "w", encoding="utf-8") as out:
            out.write(f"{title}\n\n{content}\n")

        txt_paths[i] = output_txt

    print(f"✅ Converted {len(txt_paths)} chapters.")
    return txt_paths

# ====== STEP 5: Merge into batches of 100 with novel title at top ======
def merge_txt_files(txt_paths, novel_title):
    print("📚 Merging into 100-chapter batches...")
    keys = sorted(txt_paths.keys())
    batch_size = 100
    safe_title = "".join(c for c in novel_title if c not in r'\/:*?"<>|').strip()

    for i in range(0, len(keys), batch_size):
        batch = keys[i:i+batch_size]
        start = batch[0]
        end = batch[-1]

        merged_file = os.path.join(MERGED_DIR, f"{safe_title} {start:04d}-{end:04d}.txt")
        with open(merged_file, "w", encoding="utf-8") as out:
            out.write(f"{novel_title}\n\n")
            for idx in batch:
                with open(txt_paths[idx], "r", encoding="utf-8") as f:
                    out.write(f.read().strip() + "\n\n")
        print(f"✅ Merged: {safe_title} {start:04d}-{end:04d}.txt")

# ====== STEP 6: Cleanup HTML and TXT files ======
def cleanup_files():
    print("🗑️ Cleaning up HTML and TXT files...")

    html_files = glob(os.path.join(HTML_DIR, "*.html"))
    for f in html_files:
        os.remove(f)
    print(f"   Deleted {len(html_files)} HTML files.")

    txt_files = glob(os.path.join(TXT_DIR, "*.txt"))
    for f in txt_files:
        os.remove(f)
    print(f"   Deleted {len(txt_files)} TXT files.")

    print("✅ Cleanup done. Only merged files kept.")

# ====== STEP 7: Clean merged files ======

NAV_PREV = "Prev Chapter"
NAV_NEXT = "Next Chapter"
STRIP_CHARS = "<>*#"
REPEAT_CHECK_WINDOW = 5
FOREIGN_LINE_THRESHOLD = 0.3
FOREIGN_SCRIPT_RE = re.compile(
    r'[\u4e00-\u9fff\u3040-\u30ff\u30a0-\u30ff\uac00-\ud7af'
    r'\u0400-\u04ff\u0600-\u06ff\u0900-\u097f\u0e00-\u0e7f]'
)
CHAPTER_NUM_RE = re.compile(r'Chapter\s+(\d+)', re.IGNORECASE)
CHAPTER_TITLE_LINE_RE = re.compile(r'^Chapter\s+\d+\s*[:\-–]\s*(?:\d+\s*[:\-–]\s*)?(.*)$', re.IGNORECASE)

def looks_foreign(line):
    letters = [c for c in line if c.isalpha()]
    if not letters:
        return False
    foreign = len(FOREIGN_SCRIPT_RE.findall(line))
    return (foreign / len(letters)) > FOREIGN_LINE_THRESHOLD

def clean_line(line):
    line = line.replace("\xa0", " ")
    for ch in STRIP_CHARS:
        line = line.replace(ch, "")
    line = FOREIGN_SCRIPT_RE.sub("", line)
    line = re.sub(r'[\(\[\{（【]\s*[\)\]\}）】]', '', line)
    line = re.sub(r' {2,}', ' ', line)
    return line.strip()

def clean_block(raw_lines):
    out = []
    prev_blank = False
    recent_lines = []
    for raw in raw_lines:
        cleaned = clean_line(raw)
        if not cleaned:
            if prev_blank:
                continue
            prev_blank = True
            out.append("")
            continue
        if looks_foreign(cleaned):
            continue
        if cleaned in recent_lines:
            continue
        prev_blank = False
        out.append(cleaned)
        recent_lines.append(cleaned)
        if len(recent_lines) > REPEAT_CHECK_WINDOW:
            recent_lines.pop(0)
    return out

def find_nav_pairs(lines):
    pairs = []
    for i in range(len(lines) - 1):
        if lines[i].strip() == NAV_PREV and lines[i + 1].strip() == NAV_NEXT:
            pairs.append(i)
    return pairs

def extract_chapters(lines):
    pairs = find_nav_pairs(lines)
    if len(pairs) < 2:
        return
    chapter_index = 1
    for k in range(0, len(pairs) - 1, 2):
        before = pairs[k]
        after = pairs[k + 1]
        content_start = before + 2
        content_end = after
        if content_start >= content_end:
            continue
        raw_block = lines[content_start:content_end]
        cleaned = clean_block(raw_block)
        num = None
        title = ""
        if cleaned:
            m = CHAPTER_TITLE_LINE_RE.match(cleaned[0])
            if m:
                title = m.group(1).strip()
                num_m = CHAPTER_NUM_RE.search(cleaned[0])
                if num_m:
                    num = num_m.group(1)
                cleaned = cleaned[1:]
        if num is None:
            for j in range(max(0, before - 6), before):
                m = CHAPTER_NUM_RE.search(lines[j])
                if m:
                    num = m.group(1)
                    break
        if num is None:
            num = str(chapter_index)
        body = "\n".join(cleaned).strip()
        if body or title:
            yield num, title, body
        chapter_index += 1

def general_clean(lines):
    return "\n".join(clean_block(lines)).strip() + "\n"

def clean_file(src):
    raw = Path(src).read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    chapters = list(extract_chapters(lines))
    if chapters:
        parts = []
        for num, title, body in chapters:
            header = f"Chapter {num}: {title}" if title else f"Chapter {num}"
            parts.append(f"{header}\n\n{body}" if body else header)
        return "\n\n\n".join(parts) + "\n", len(chapters), "chapters"
    return general_clean(lines), 0, "general"

def novel_clean_dir(novel_title):
    """clean_novel/<Novel Title>/ — created on demand."""
    safe_title = "".join(c for c in novel_title if c not in r'\/:*?"<>|').strip() or "novel"
    folder = os.path.join(CLEAN_DIR, safe_title)
    os.makedirs(folder, exist_ok=True)
    return folder

def clean_merged_files(novel_title):
    print("✨ Cleaning merged files...")
    safe_title = "".join(c for c in novel_title if c not in r'\/:*?"<>|').strip()
    # only this novel's merged files (named "<Title> 0001-0100.txt")
    txt_files = sorted(glob(os.path.join(glob_escape(MERGED_DIR), glob_escape(safe_title) + " [0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9].txt")))
    out_dir = novel_clean_dir(novel_title)

    if not txt_files:
        print("⚠️ No merged files found to clean.")
        return

    total_chapters = 0
    general_files = []
    for f in txt_files:
        cleaned, n_chapters, mode = clean_file(f)
        out_path = os.path.join(out_dir, os.path.basename(f))
        with open(out_path, "w", encoding="utf-8") as out:
            out.write(cleaned)
        if mode == "chapters":
            total_chapters += n_chapters
            print(f"   {os.path.basename(f)}: {n_chapters} chapter(s) cleaned")
        else:
            general_files.append(os.path.basename(f))
            print(f"   {os.path.basename(f)}: no site markers found — ran general cleanup")

    print(f"✅ Cleaning done. {total_chapters} chapter(s) cleaned.")
    if general_files:
        print(f"   {len(general_files)} file(s) used general cleanup (may already be clean).")

# ====== STEP 8: Build EPUB from cleaned files ======
EPUB_HEADER_RE = re.compile(r'^Chapter\s+\d+', re.IGNORECASE)

def collect_epub_chapters(novel_title):
    """Read this novel's cleaned files (in order) and return a list of (title, body) tuples."""
    chapters = []
    for f in sorted(glob(os.path.join(glob_escape(novel_clean_dir(novel_title)), "*.txt"))):
        text = Path(f).read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            continue
        for block in re.split(r'\n{3,}', text):
            block = block.strip()
            if not block:
                continue
            lines = block.splitlines()
            if EPUB_HEADER_RE.match(lines[0]):
                title = lines[0].strip()
                body = "\n".join(lines[1:]).strip()
            else:
                title = Path(f).stem
                body = block
            chapters.append((title, body))
    return chapters

def body_to_xhtml(body):
    paras = [p.strip() for p in re.split(r'\n\s*\n', body) if p.strip()]
    if len(paras) <= 1 and body.count("\n") > 0:
        # no blank-line paragraphs -> treat every line as a paragraph
        paras = [l.strip() for l in body.splitlines() if l.strip()]
    out = []
    for p in paras:
        inner = "<br/>".join(xml_escape(l.strip()) for l in p.splitlines() if l.strip())
        out.append(f"<p>{inner}</p>")
    return "\n".join(out)

def sniff_image_ext(data):
    """Detect the real image type from the file's first bytes (not from the URL / header)."""
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"GIF8":
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None

def build_epub(novel_title, cover_path=None):
    print("📖 Building EPUB...")
    chapters = collect_epub_chapters(novel_title)
    if not chapters:
        print("⚠️ No cleaned chapters found — EPUB not created.")
        return None

    safe_title = "".join(c for c in novel_title if c not in r'\/:*?"<>|').strip() or "novel"
    epub_path = os.path.join(EPUB_DIR, f"{safe_title}.epub")
    book_id = f"urn:uuid:{uuid.uuid4()}"
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    t_esc = xml_escape(novel_title)

    # ---- cover image (optional) ----
    cover_bytes, cover_name, cover_mime = None, None, None
    if cover_path and os.path.exists(cover_path):
        with open(cover_path, "rb") as cf:
            cover_bytes = cf.read()
        ext = sniff_image_ext(cover_bytes)
        if ext is None:
            print("   ⚠️ Cover file is not a valid image — EPUB will have no cover.")
            cover_bytes = None
        elif ext in (".webp", ".gif"):
            # Many e-readers can't show WebP -> convert to JPEG (needs Pillow)
            try:
                from PIL import Image
                import io
                buf = io.BytesIO()
                Image.open(io.BytesIO(cover_bytes)).convert("RGB").save(buf, "JPEG", quality=92)
                cover_bytes, ext = buf.getvalue(), ".jpg"
            except Exception:
                print("   ⚠️ Could not convert cover to JPEG (install Pillow: pip install pillow).")
        if cover_bytes:
            cover_mime = {".jpg": "image/jpeg", ".png": "image/png",
                          ".gif": "image/gif", ".webp": "image/webp"}[ext]
            cover_name = f"cover{ext}"
            print(f"   Using cover image: {os.path.basename(cover_path)} ({len(cover_bytes)//1024} KB, {cover_mime})")
    if not cover_bytes:
        print("   No usable cover image — EPUB will have no cover.")

    css = (
        "body { font-family: serif; line-height: 1.5; margin: 5%; }\n"
        "h1 { text-align: center; margin: 1.5em 0 1em; font-size: 1.4em; }\n"
        "p { margin: 0 0 0.9em; text-align: justify; }\n"
    )

    def chapter_xhtml(title, body):
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
            f'<head><meta charset="utf-8"/><title>{xml_escape(title)}</title>'
            '<link rel="stylesheet" type="text/css" href="style.css"/></head>\n'
            f'<body><h1>{xml_escape(title)}</h1>\n{body_to_xhtml(body)}\n</body></html>'
        )

    cover_xhtml = (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
        f'<head><meta charset="utf-8"/><title>{t_esc}</title>'
        '<style>html,body{margin:0;padding:0;height:100%;text-align:center;}'
        'img{max-width:100%;max-height:100%;height:auto;}</style></head>\n'
        f'<body epub:type="cover"><img src="{cover_name}" alt="Cover"/></body></html>'
    ) if cover_bytes else None

    manifest, spine, nav_items, ncx_points = [], [], [], []
    if cover_bytes:
        manifest.append(f'<item id="cover-image" href="{cover_name}" media-type="{cover_mime}" properties="cover-image"/>')
        manifest.append('<item id="cover-page" href="cover.xhtml" media-type="application/xhtml+xml"/>')
        spine.append('<itemref idref="cover-page" linear="yes"/>')
    for n, (title, body) in enumerate(chapters, start=1):
        fid = f"ch{n:05d}"
        manifest.append(f'<item id="{fid}" href="{fid}.xhtml" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="{fid}"/>')
        nav_items.append(f'<li><a href="{fid}.xhtml">{xml_escape(title)}</a></li>')
        ncx_points.append(
            f'<navPoint id="np{n}" playOrder="{n}"><navLabel><text>{xml_escape(title)}</text></navLabel>'
            f'<content src="{fid}.xhtml"/></navPoint>'
        )

    nav_xhtml = (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">\n'
        f'<head><meta charset="utf-8"/><title>{t_esc}</title></head>\n'
        '<body><nav epub:type="toc" id="toc"><h1>Table of Contents</h1><ol>\n'
        + "\n".join(nav_items) + '\n</ol></nav>'
        + ('<nav epub:type="landmarks" hidden="hidden"><ol><li><a epub:type="cover" href="cover.xhtml">Cover</a></li></ol></nav>' if cover_bytes else '')
        + '</body></html>'
    )

    toc_ncx = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
        f'<head><meta name="dtb:uid" content="{book_id}"/><meta name="dtb:depth" content="1"/>'
        '<meta name="dtb:totalPageCount" content="0"/><meta name="dtb:maxPageNumber" content="0"/></head>\n'
        f'<docTitle><text>{t_esc}</text></docTitle>\n<navMap>\n'
        + "\n".join(ncx_points) + '\n</navMap></ncx>'
    )

    content_opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">\n'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        f'<dc:identifier id="bookid">{book_id}</dc:identifier>\n'
        f'<dc:title>{t_esc}</dc:title>\n<dc:language>en</dc:language>\n'
        f'<meta property="dcterms:modified">{modified}</meta>\n'
        + ('<meta name="cover" content="cover-image"/>\n' if cover_bytes else '')
        + '</metadata>\n<manifest>\n'
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>\n'
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>\n'
        '<item id="css" href="style.css" media-type="text/css"/>\n'
        + "\n".join(manifest) + '\n</manifest>\n<spine toc="ncx">\n'
        + "\n".join(spine) + '\n</spine>\n'
        + ('<guide><reference type="cover" title="Cover" href="cover.xhtml"/></guide>\n' if cover_bytes else '')
        + '</package>'
    )

    container_xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
        '</rootfiles></container>'
    )

    with zipfile.ZipFile(epub_path, "w") as z:
        # mimetype must be first and uncompressed
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container_xml, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", content_opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", nav_xhtml, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/toc.ncx", toc_ncx, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/style.css", css, compress_type=zipfile.ZIP_DEFLATED)
        if cover_bytes:
            z.writestr(f"OEBPS/{cover_name}", cover_bytes, compress_type=zipfile.ZIP_STORED)
            z.writestr("OEBPS/cover.xhtml", cover_xhtml, compress_type=zipfile.ZIP_DEFLATED)
        for n, (title, body) in enumerate(chapters, start=1):
            z.writestr(f"OEBPS/ch{n:05d}.xhtml", chapter_xhtml(title, body), compress_type=zipfile.ZIP_DEFLATED)

    print(f"✅ EPUB created: {epub_path} ({len(chapters)} chapters)")
    return epub_path

# ====== STEP 9: Download novel cover picture ======
def find_cover_urls(soup, page_url):
    """Return every plausible cover image URL from the novel page, best guess first."""
    candidates = []

    for attrs in ({"property": "og:image"}, {"name": "twitter:image"}, {"itemprop": "image"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            candidates.append(tag["content"])

    imgs = []
    for selector in ("div.book img", "div.info-holder img", "div.books img", "img[itemprop=image]"):
        imgs += soup.select(selector)
    # any other image whose URL looks like a novel cover
    for img in soup.find_all("img"):
        blob = " ".join(str(img.get(a, "")) for a in ("src", "data-src", "data-cfsrc", "data-original"))
        if re.search(r'/(media|cover|covers|novel|thumb)', blob, re.I):
            imgs.append(img)
    for img in imgs:
        for attr in ("src", "data-src", "data-cfsrc", "data-original"):
            if img.get(attr):
                candidates.append(img[attr])

    urls, seen = [], set()
    for c in candidates:
        c = c.strip()
        if not c or c.startswith("data:"):
            continue
        full = urljoin(page_url, c)
        if full not in seen:
            seen.add(full)
            urls.append(full)
    return urls

def download_cover(novel_id, novel_title):
    print("🖼️ Downloading novel cover...")
    novel_url = f"{BASE_URL}/novel-{novel_id}.html"
    safe_title = "".join(c for c in novel_title if c not in r'\/:*?"<>|').strip() or f"novel_{novel_id}"
    img_headers = {
        'User-Agent': HEADERS['User-Agent'],
        'Referer': novel_url,
        'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
    }
    try:
        r = requests.get(novel_url, headers=img_headers, timeout=15)
        print(f"   Novel page status: {r.status_code}")
        if r.status_code != 200:
            print("   ❌ Could not open novel page — cover skipped.")
            return None

        soup = BeautifulSoup(r.text, "html.parser")
        urls = find_cover_urls(soup, novel_url)
        if not urls:
            print("   ❌ No cover image found on the page.")
            return None

        for cover_url in urls:
            print(f"   Trying: {cover_url}")
            try:
                img = requests.get(cover_url, headers=img_headers, timeout=20)
            except Exception as e:
                print(f"     ❌ Request error: {e}")
                continue
            ctype = img.headers.get("Content-Type", "")
            ext = sniff_image_ext(img.content) if img.content else None
            print(f"     Status {img.status_code}, type '{ctype}', {len(img.content)} bytes")
            if img.status_code != 200 or ext is None:
                print("     ❌ Not a valid image — trying next candidate.")
                continue
            # remove older cover files for this title so only the new one remains
            for old in glob(os.path.join(COVER_DIR, f"{safe_title}.*")):
                os.remove(old)
            cover_path = os.path.join(COVER_DIR, f"{safe_title}{ext}")
            with open(cover_path, "wb") as f:
                f.write(img.content)
            print(f"✅ Cover saved: {cover_path}")
            return cover_path

        print("   ❌ None of the candidate URLs gave a valid image.")
        return None
    except Exception as e:
        print(f"   ❌ Cover download error: {e}")
        return None

# ====== MAIN RUN ======
if __name__ == "__main__":
    NOVEL_ID = select_novel_id()
    CHAPTER_LIST_URL = f'https://readnovelfull.com/ajax/chapter-archive?novelId={NOVEL_ID}'
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': f'https://readnovelfull.com/novel-{NOVEL_ID}.html',
        'X-Requested-With': 'XMLHttpRequest'
    }

    print("How many chapters to download? (Enter 0 for all)")
    while True:
        try:
            chapter_limit = int(input("Number of chapters: ").strip())
            if chapter_limit < 0:
                print("❌ Please enter 0 or a positive number.")
                continue
            break
        except ValueError:
            print("❌ Please enter a valid number.")

    novel_title = get_novel_title(NOVEL_ID, CHAPTER_LIST_URL)
    links = get_chapter_links(CHAPTER_LIST_URL)

    if chapter_limit > 0:
        links = links[:chapter_limit]
        print(f"⏹️ Limit set: will download {len(links)} chapters.")

    download_chapters(links)
    renamed = rename_html_files()
    txts = convert_html_to_txt(renamed)
    merge_txt_files(txts, novel_title)
    cleanup_files()
    clean_merged_files(novel_title)
    cover_path = download_cover(NOVEL_ID, novel_title)
    build_epub(novel_title, cover_path)
    print(f"\n🎉 Done! Downloaded '{novel_title}' (ID {NOVEL_ID}). Check the 'readnovelfull' folder for results.")
