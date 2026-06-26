# Python Toolkit v1.0.0

A premium, interactive CLI toolkit for media downloading, PDF generation, ebook parsing, and Facebook scraping. Organized into a clean, modern Python package structure and powered by a polished `rich` terminal interface.

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

### 3. 📖 Book to README (`pdf_tools/`)
* Converts heavy PDF books into chapter-wise structured Markdown folders.
* Parses Table of Contents outlines using `PyMuPDF` (fitz) or falls back to page-chunking.
* Generates a root `README.md` index acting as the front-matter preface and linking to all chapters.

### 4. 💬 Facebook Tuition Scraper (`scraper/`)
* Scrapes public Facebook tuition/job provider feeds using Playwright and stealth headers.
* Parses tutoring posts (class, subjects, location, salary, university preferences) using high-precision regex.
* Filters posts according to preferences defined in `scraper/facebook_web_scraper.py` and exports matching results to `output/scraper/`.

### 5. 📦 CBZ & Image Converters (`converter/`)
* **CBZ → PDF**: Compiles Comic Book ZIP (.cbz) archives into high-fidelity PDFs. Uses fitz to stream images efficiently.
* **Image → PDF**: Converts directories of images (PNG, JPG, BMP, WebP) into a single PDF.
* Both tools support Tkinter GUIs with native drag-and-drop support (via `tkinterdnd2`) alongside fallback file explorers and standard CLI mode.

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
│   └── FFMPEG_SETUP.md
│
├── converter/                 # PDF Converters package
│   ├── __init__.py
│   ├── main.py                # PDF Converter submenu TUI
│   ├── cbz_to_pdf.py
│   └── img_to_pdf.py
│
├── pdf_tools/                 # PDF Parsing package
│   ├── __init__.py
│   └── book_to_readme.py
│
├── scraper/                   # Facebook Scraper package
│   ├── __init__.py
│   └── facebook_web_scraper.py
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
* **v1.0.0** (2026-06-26)
  * Complete project restructuring: Eliminated digit-prefixed package names.
  * Extracted duplications into a central `shared` package (`shared/console.py` and `shared/config.py`).
  * Created git-ignored `output/` directory and centralized links inputs into `config/`.
  * Fixed silent failure of `book_to_readme.py` and consolidated menu handlers into a single `main.py` entry point.
  * Added `SYSTEM.md` and modern `pyproject.toml` configuration.
