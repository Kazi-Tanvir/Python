# Python Toolkit v1.1.0

A premium, interactive CLI toolkit for media downloading, PDF generation, PowerPoint conversion, ebook parsing, and Facebook scraping. Organized into a clean, modern Python package structure and powered by a polished `rich` terminal interface.

---

## 🌟 Key Tools Included

### 1. 🖥️ Central Script Launcher (`main.py`)
* Coordinates and runs all toolkit utilities from a single terminal interface.
* Dynamically reloads scripts on execution for seamless development.
* Integrates custom script registration (`scripts.json`) directly through the TUI.
* Features a project-wide dependency checker and system status viewer.

### 2. 🎥 Media Downloader Suite (`downloader/`)
* **YouTube Downloader**: High-speed, multi-connection video/playlist downloads via `yt-dlp` and `aria2c`.
* **Facebook Downloader**: Automatically extracts and merges best quality HD streams.
* **Instagram Downloader**: Story, post, reel, and full profile downloading using `instaloader` with session credentials and rate-limiting.
* **X (Twitter) Downloader**: Download high-quality videos from X/Twitter posts.
* **Bulk Download**: Read links from batch files inside `config/` (`yt_links.txt`, `ig_links.txt`, `fb_links.txt`, `x_links.txt`) and download them in parallel.
* **Individual Link Loop**: When using "Single Video/URL" mode, you can keep entering URLs one after another until you type `0` to go back — no need to re-navigate the menu for every download.

### 3. 📖 Book to README (`pdf_tools/`)
* Converts heavy PDF books into chapter-wise structured Markdown folders.
* Parses Table of Contents outlines using `PyMuPDF` (fitz) or falls back to page-chunking.
* Generates a root `README.md` index acting as the front-matter preface and linking to all chapters.

### 4. ✂️ PDF Splitter (`pdf_tools/`)
* Splits complex PDF files into smaller documents using three flexible methods:
  * **Page Range Extraction**: Extract specific page ranges (e.g., 1-10, 15-20) into a single new PDF.
  * **Manual Chapters**: Interactively define custom chapter page ranges to generate multiple PDFs in a structured folder.
  * **Auto Chapters**: Automatically parse the PDF's embedded Table of Contents (TOC) using `PyMuPDF` to segment the entire document.

### 5. 💬 Facebook Tuition Scraper (`scraper/`)
* Scrapes public Facebook tuition/job provider feeds using Playwright and stealth headers.
* Parses tutoring posts (class, subjects, location, salary, university preferences) using high-precision regex.
* Filters posts according to preferences defined in `scraper/facebook_web_scraper.py` and exports matching results to `output/scraper/`.

### 6. 📦 Converters Suite (`converter/`)
* **CBZ → PDF**: Compiles Comic Book ZIP (.cbz) archives into high-fidelity PDFs. Now with a full **CLI mode** alongside the GUI — convert via terminal with Rich progress bars, or use the drag-and-drop Tkinter GUI.
* **Image → PDF**: Converts directories of images (PNG, JPG, BMP, WebP) into a single PDF. Uses **uniform page width normalization** — all pages are scaled to the widest image's width while preserving aspect ratio. This ensures consistent "fit to screen" reading, especially useful for manga with mixed page dimensions.
* **PPT → PDF**: Converts PowerPoint (.pptx) presentations into high-fidelity PDF files by rendering each slide as a high-DPI image and stitching them together via PyMuPDF.
* **PPT → README**: Extracts slide titles, bullet points, tables, images, and speaker notes from PowerPoint files and generates structured Markdown with a table of contents, embedded images, and formatted notes.

### 7. 🔍 OSINT Phone Lookup (`osint/`)
* Deep reverse phone number intelligence gathering and reconnaissance.
* Runs multiple intelligence modules in parallel:
  * **Basic Info & Carrier Details**: Normalizes phone formats (E.164) and retrieves carrier/geographic details.
  * **Caller ID Check**: Queries public records to resolve registered subscriber names.
  * **Data Breach Lookup**: Scans leak databases for breaches associated with the number.
  * **Messaging & Social Media Scan**: Checks profile associations on networks like WhatsApp, Telegram, Signal, and Viber.
  * **Reputation & Fraud Rating**: Analyzes fraud scores and caller reputation.
  * **Search Engine Scrapers**: Aggregates public web mentions, social media references, and custom Google searches.

---

## 📂 Repository Structure

```
python-toolkit/
├── main.py                    # Single entry point and menu
├── pyproject.toml             # Modern package config & CLI script entry
├── requirements.txt           # Pinned dependencies
├── .env.example               # Template environment configuration
├── .gitignore                 # Custom ignore rules
├── README.md                  # GitHub documentation
├── SYSTEM.md                  # Contributor and architecture guide
│
├── shared/                    # Shared utilities package
│   ├── __init__.py
│   ├── console.py             # Single source of truth for Console & Theme
│   └── config.py              # Single source of truth for PROJECT_ROOT & dotenv
│
├── downloader/                # Media downloader package
│   ├── __init__.py
│   ├── main.py                # Media downloader submenu TUI
│   ├── utils.py               # Downloader-specific path & dependency helpers
│   ├── yt_downloader.py
│   ├── ig_downloader.py
│   ├── fb_downloader.py
│   ├── x_downloader.py
│   └── FFMPEG_SETUP.md
│
├── converter/                 # Converters package
│   ├── __init__.py
│   ├── main.py                # Converters submenu TUI
│   ├── cbz_to_pdf.py          # CBZ → PDF (GUI + CLI)
│   ├── img_to_pdf.py          # Image → PDF (GUI + CLI, uniform width)
│   ├── ppt_to_pdf.py          # PPT → PDF (CLI)
│   └── ppt_to_readme.py       # PPT → Markdown README (CLI)
│
├── pdf_tools/                 # PDF Parsing package
│   ├── __init__.py
│   ├── book_to_readme.py
│   └── pdf_splitter.py
│
├── scraper/                   # Facebook Scraper package
│   ├── __init__.py
│   └── facebook_web_scraper.py
│
├── osint/                     # OSINT tools package
│   ├── __init__.py
│   └── main.py
│
├── misc/                      # Unrelated utilities folder (empty for future scripts)
│   └── __init__.py
│
├── config/                    # Configuration / batch inputs folder
│   ├── yt_links.txt           # Batch YouTube links
│   ├── ig_links.txt           # Batch Instagram links/profiles
│   ├── fb_links.txt           # Batch Facebook links
│   └── x_links.txt            # Batch X/Twitter links
│
└── output/                    # Git-ignored directory for all outputs
    ├── downloads/             # Downloaded media files
    ├── books/                 # Converted PDF chapters & readmes
    └── scraper/               # Tuition scraper json results
```

---

## 🛠️ Installation & Setup

### 1. Install Dependencies
Ensure you have Python 3.10+ installed. Install the pinned dependencies using `requirements.txt`:
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
Copy `.env.example` to `.env` in the project root:
```bash
cp .env.example .env
```
Fill out the variables inside `.env` to configure paths (FFmpeg, custom download directory, etc.) and scraper/downloader credentials. See [SYSTEM.md](file:///d:/02_CODE/98_PYTHON/SYSTEM.md) for detailed environment configuration.

---

## 🎮 How to Use

Launch the main menu simply by running:
```bash
python main.py
```
From here you can launch all built-in tools, manage custom user scripts, and check system status.

---

## 📄 Release & Versioning

This project uses a standard three-digit versioning scheme (`v{MAJOR}.{FEATURES}.{FIXES}`):
* **MAJOR (1.x.x)**: Refers to major structure/architectural reorganizations or breaking changes.
* **FEATURES (x.1.x)**: Refers to the addition of a new tool or configuration feature.
* **FIXES (x.x.1)**: Refers to bug fixes, file updates, and minor adjustments.

### Version History
* **v1.1.0** (2026-07-04)
  * **New OSINT Phone Lookup Suite**: Reverse phone intelligence gathering with modules for carrier/basic info, caller ID search, data breach analysis, messaging/social media checks, reputation rating, and search engine aggregation.
  * **New PDF Splitter Tool**: Multi-mode PDF segmenter supporting page range extraction, manual chapter ranges, and auto-chapter splitting via PDF table of contents.
  * **New X (Twitter) Downloader**: Added support for high-quality video downloading from X/Twitter posts.
  * **PPT → PDF Converter**: New tool to render PowerPoint presentations to high-fidelity PDF via slide-to-image rendering.
  * **PPT → README Converter**: New tool to extract structured Markdown from PowerPoint — titles, bullets, tables, images, and speaker notes.
  * **Image → PDF Uniform Width**: All pages are now normalized to the widest image's width, ensuring consistent "fit to screen" for manga with mixed page dimensions.
  * **CBZ → PDF CLI Mode**: Added full terminal-based conversion with Rich progress bars alongside the existing GUI.
  * **Downloader Individual Link Loop**: All downloaders (YouTube, Facebook, Instagram, X) now loop in "Single URL" mode — keep pasting links until you type `0` to go back.
  * Added `python-pptx`, `phonenumbers`, `requests`, and `beautifulsoup4` dependencies.
* **v1.0.0** (2026-06-26)
  * Complete project restructuring: Eliminated digit-prefixed package names.
  * Extracted duplications into a central `shared` package (`shared/console.py` and `shared/config.py`).
  * Created git-ignored `output/` directory and centralized links inputs into `config/`.
  * Fixed silent failure of `book_to_readme.py` and consolidated menu handlers into a single `main.py` entry point.
  * Added `SYSTEM.md` and modern `pyproject.toml` configuration.
