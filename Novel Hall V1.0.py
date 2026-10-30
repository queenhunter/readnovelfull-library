import os
import re
import time
import requests
from bs4 import BeautifulSoup
from glob import glob
from pathlib import Path
from urllib.parse import urlparse, urljoin

# ====== CONFIG ======
BASE_DIR = os.path.abspath(os.path.expanduser(
    os.environ.get("NOVELHALL_OUTPUT_DIR", os.path.join(os.getcwd(), "novelhall"))
))
HTML_DIR = os.path.join(BASE_DIR, "html")
TXT_DIR = os.path.join(BASE_DIR, "chapters")
MERGED_DIR = os.path.join(BASE_DIR, "merged")
FAILED_DIR = os.path.join(BASE_DIR, "failed")
CLEAN_DIR = os.path.join(BASE_DIR, "clean_novel")

BASE_URL = 'https://www.novelhall.com'

# ====== SETUP FOLDERS ======
for folder in [BASE_DIR, HTML_DIR, TXT_DIR, MERGED_DIR, FAILED_DIR, CLEAN_DIR]:
    os.makedirs(folder, exist_ok=True)

# ====== FETCH NOVEL SLUG FROM URL ======
def extract_novel_slug(url):
    """Extract novel slug from URL like /the-youngest-son-of-sunyang-9672/"""
    try:
        # Remove query params and fragments
        url = url.split("?")[0].split("#")[0]
        # Extract slug from path
        parts = url.rstrip('/').split('/')
        for part in parts:
            if part and '-' in part and any(c.isdigit() for c in part):
                return part
        return None
    except:
        return None

# ====== NOVEL SLUG SELECTION ======
def select_novel_url():
    saved_url_file = os.path.join(BASE_DIR, "novel_url.txt")
    saved_url = None

    if os.path.exists(saved_url_file):
        with open(saved_url_file, "r") as f:
            saved_url = f.read().strip()

    print("\n" + "="*50)
    print("         NOVELHALL DOWNLOADER")
    print("="*50)

    if saved_url:
        print(f"  Saved URL: {saved_url}")
        print("  [1] Keep saved URL")
        print("  [2] Enter new URL")
        print("="*50)
        while True:
            choice = input("Select (1 or 2): ").strip()
            if choice == "1":
                print(f"✅ Using saved URL: {saved_url}\n")
                return saved_url
            elif choice == "2":
                break
            else:
                print("❌ Invalid choice. Enter 1 or 2.")
    else:
        print("  Paste a novel URL from novelhall.com")
        print("="*50)

    # Get URL
    while True:
        url = input("Paste novel URL: ").strip()
        if not url.startswith("http"):
            print("❌ Please paste a valid URL starting with http.")
            continue
        
        # Strip fragment
        url = url.split("#")[0]
        
        slug = extract_novel_slug(url)
        if slug:
            with open(saved_url_file, "w") as f:
                f.write(url)
            print(f"✅ URL saved: {url}\n")
            return url
        else:
            print("❌ Could not extract novel info from URL. Make sure it's a valid novelhall.com URL.")
            retry = input("Try again? (y/n): ").strip().lower()
            if retry != "y":
                print("Exiting.")
                exit(1)

# ====== STEP 0: Get novel title from page ======
def get_novel_title(novel_url, headers):
    print("📡 Fetching novel title...")
    novel_title = "Novel"
    
    try:
        print(f"   Attempting: {novel_url}")
        r = requests.get(novel_url, headers=headers, timeout=10)
        print(f"   Status: {r.status_code}")
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            # Look for title in various places
            title_tag = soup.find("h1") or soup.find("title")
            if title_tag:
                raw_title = title_tag.get_text(strip=True)
                # Clean up title
                novel_title = raw_title.split(" read novel")[0].split(" - ")[0].strip()
                if novel_title and len(novel_title) > 2:
                    print(f"✅ Novel Title: {novel_title}")
                    return novel_title
        else:
            print(f"   Failed with status {r.status_code}")
    except Exception as e:
        print(f"   ❌ Error fetching page: {e}")
    
    # Fallback: extract from URL
    slug = extract_novel_slug(novel_url)
    if slug:
        novel_title = slug.rsplit('-', 1)[0].replace('-', ' ').title()
        print(f"✅ Fallback title from URL: {novel_title}")
    
    title_file = os.path.join(BASE_DIR, "novel_title.txt")
    with open(title_file, "w", encoding="utf-8") as f:
        f.write(novel_title)
    print(f"💾 Saved title to: {title_file}")
    
    return novel_title

# ====== STEP 1: Get chapter links ======
def get_chapter_links(novel_url, headers):
    print("📡 Fetching chapter list...")
    r = requests.get(novel_url, headers=headers, timeout=10)
    print(f"   Status: {r.status_code}")
    
    soup = BeautifulSoup(r.text, "html.parser")
    links = []
    
    # Find chapter links inside the novel's catalog when available.
    catalog_section = (
        soup.find("div", class_="catalog") or
        soup.find("div", id="catalog") or
        soup.select_one("#chapter-list, .chapter-list, .list-chapter, .chapters")
    )
    if catalog_section:
        chapter_links = catalog_section.find_all("a", href=True)
    else:
        # NovelHall chapter links share the novel path and have a numeric HTML filename.
        chapter_links = []
        novel_path = urlparse(novel_url).path.rstrip("/") + "/"
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            full_url = urljoin(BASE_URL, href)
            parsed = urlparse(full_url)
            if parsed.hostname not in {"novelhall.com", "www.novelhall.com"}:
                continue
            if parsed.path.startswith(novel_path) and re.search(r"/\d+\.html$", parsed.path):
                chapter_links.append(a)
    
    for a in chapter_links:
        href = a.get("href", "").strip()
        if href and ("chapter" in href.lower() or re.search(r'\d+\.html', href)):
            full_url = urljoin(BASE_URL, href)
            if full_url not in links:
                links.append(full_url)
    
    # Remove duplicates while preserving the site's displayed chapter order.
    links = list(dict.fromkeys(links))
    if len(links) < 2 and links:
        # Some novels split their catalog across paginated volume pages.
        next_links = []
        for a in soup.select("a[href]"):
            text = a.get_text(" ", strip=True).lower()
            href = urljoin(BASE_URL, a.get("href", ""))
            if any(word in text for word in ("next", "下一页", "›")) and href != novel_url:
                next_links.append(href)
        for page_url in next_links[:10]:
            try:
                page = requests.get(page_url, headers=headers, timeout=10)
                page.raise_for_status()
                page_soup = BeautifulSoup(page.text, "html.parser")
                for a in page_soup.find_all("a", href=True):
                    href = urljoin(BASE_URL, a.get("href", ""))
                    parsed = urlparse(href)
                    if parsed.hostname in {"novelhall.com", "www.novelhall.com"} and parsed.path.startswith(novel_path) and re.search(r"/\d+\.html$", parsed.path):
                        links.append(href)
            except requests.RequestException:
                continue
        links = list(dict.fromkeys(links))

    print(f"✅ Found {len(links)} chapters.")
    return links

# ====== STEP 2: Download chapters ======
def download_chapters(links, chapter_limit=0, progress_callback=None):
    print("⬇️ Downloading chapters...")
    if chapter_limit > 0:
        links = links[:chapter_limit]
    total = len(links)
    for i, url in enumerate(links, start=1):
        filename = os.path.join(HTML_DIR, f"raw_{i:04d}.html")
        if progress_callback:
            progress_callback(i, total, "starting")
        r = None
        try:
            if not os.path.exists(filename):
                r = requests.get(url, headers=HEADERS, timeout=10)
                print(f"   Chapter {i} status: {r.status_code}")
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(r.text)
                print(f"✅ Saved: raw_{i:04d}.html")
                time.sleep(1)
        except Exception as e:
            print(f"❌ Failed to download chapter {i}: {e}")
            if r is not None:
                try:
                    with open(os.path.join(FAILED_DIR, f"failed_{i:04d}.html"), "w", encoding="utf-8") as f:
                        f.write(r.text)
                except OSError:
                    pass
        finally:
            if progress_callback:
                progress_callback(i, total, "finished")

# ====== STEP 3: Rename HTML files ======
def rename_html_files():
    print("🔀 Renaming HTML files...")
    html_files = sorted(glob(os.path.join(HTML_DIR, "raw_*.html")))

    renamed = {}
    for i, path in enumerate(html_files, start=1):
        new_name = os.path.join(HTML_DIR, f"chapter_{i:04d}.html")
        os.rename(path, new_name)
        renamed[i] = new_name

    print(f"✅ Renamed {len(renamed)} files.")
    return renamed

# ====== STEP 4: Convert HTML to TXT ======
def convert_html_to_txt(renamed_html):
    print("🧼 Converting HTML to clean TXT...")
    txt_paths = {}
    for i, html_path in renamed_html.items():
        with open(html_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        # Find content - try multiple selectors
        content_tag = (
            soup.find("div", class_="content") or
            soup.find("div", class_="chapter-content") or
            soup.find("div", id="content") or
            soup.find("div", class_="row") or
            soup.find("article") or
            soup.find("div", class_="container")
        )

        if not content_tag:
            print(f"⚠️ Skipped chapter_{i:04d} — content missing.")
            with open(os.path.join(FAILED_DIR, f"chapter_{i:04d}_skipped.html"), "w", encoding="utf-8") as f:
                f.write(str(soup))
            continue

        title = f"Chapter {i}"
        content = content_tag.get_text(separator="\n").strip()

        output_txt = os.path.join(TXT_DIR, f"chapter_{i:04d}.txt")
        with open(output_txt, "w", encoding="utf-8") as out:
            out.write(f"{title}\n\n{content}\n")

        txt_paths[i] = output_txt

    print(f"✅ Converted {len(txt_paths)} chapters.")
    return txt_paths

# ====== STEP 5: Merge into batches of 100 ======
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

def clean_merged_files():
    print("✨ Cleaning merged files...")
    txt_files = sorted(glob(os.path.join(MERGED_DIR, "*.txt")))

    if not txt_files:
        print("⚠️ No merged files found to clean.")
        return

    total_chapters = 0
    general_files = []
    for f in txt_files:
        cleaned, n_chapters, mode = clean_file(f)
        out_path = os.path.join(CLEAN_DIR, os.path.basename(f))
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

# ====== MAIN RUN ======
if __name__ == "__main__":
    NOVEL_URL = select_novel_url()
    
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
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

    novel_title = get_novel_title(NOVEL_URL, HEADERS)
    links = get_chapter_links(NOVEL_URL, HEADERS)

    if chapter_limit > 0:
        links_to_download = links[:chapter_limit]
        print(f"⏹️ Limit set: will download {len(links_to_download)} chapters.")
    else:
        links_to_download = links

    download_chapters(links_to_download)
    renamed = rename_html_files()
    txts = convert_html_to_txt(renamed)
    merge_txt_files(txts, novel_title)
    cleanup_files()
    clean_merged_files()
    
    slug = extract_novel_slug(NOVEL_URL)
    print(f"\n🎉 Done! Downloaded '{novel_title}' from novelhall.com. Check the 'novelhall' folder for results.")
