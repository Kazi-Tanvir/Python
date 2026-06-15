# Media Downloader Suite v1.0

A powerful, centralized, interactive command-line media downloader for YouTube, Instagram, and Facebook. Built using Python, it leverages industry-standard libraries like `yt-dlp` and `instaloader` to retrieve media at the highest available quality, while utilizing a highly polished, interactive console UI powered by `rich`.

Additionally, the project features a dynamic **plugin registry system**, allowing you to easily add and run custom downloaders directly from the main interface.

---

## 🌟 Key Features

- 🖥️ **Centralized Console Menu**: A unified interface to run all downloaders, check system status, and manage custom downloader plugins.
- ⚡ **High-Speed YouTube Downloads**: Download videos and entire playlists with options for parallel segment fetching via `aria2c`.
- 📸 **Comprehensive Instagram Downloads**: Download single posts, reels, stories, or complete user profiles (including tagged posts and stories) with rate-limit protection.
- 👥 **Facebook HD Downloads**: Download videos at the highest HD qualities.
- 🚀 **Bulk Processing**: Supply URLs in dedicated batch files (`yt_links.txt`, `ig_links.txt`, `fb_links.txt`) to download multiple files in parallel.
- 🧩 **Plugin Architecture**: Dynamically register or remove custom downloaders using the interactive UI.
- 🛠️ **System Status Checker**: Instantly verify if environment variables, FFmpeg path, credentials, and cookies are correctly configured.

---

## 📂 Repository Structure

```
98_PYTHON/
├── downloader.py             # Central entry point and CLI menu
├── requirements.txt          # Python dependencies
├── .gitignore                # Git ignore rules (ignores download folders & secrets)
├── .env.example              # Sample configuration file
├── 01_Downloader/            # Core package directory
│   ├── __init__.py           # Package initialization
│   ├── utils.py              # Shared utilities (Rich logging, status checks, environments)
│   ├── yt_downloader.py      # YouTube downloader module
│   ├── ig_downloader.py      # Instagram downloader module
│   ├── fb_downloader.py      # Facebook downloader module
│   ├── FFMPEG_SETUP.md       # Detailed FFmpeg configuration instructions
│   ├── plugins.json          # List of registered custom plugins (created dynamically)
│   ├── yt_links.txt          # Batch URLs for YouTube bulk downloading
│   ├── ig_links.txt          # Batch URLs/usernames for Instagram bulk downloading
│   └── fb_links.txt          # Batch URLs for Facebook bulk downloading
└── downloads/                # Generated folder where media files are saved (Git-ignored)
```

> [!IMPORTANT]
> All media downloads are saved into the `downloads/` directory (inside `01_Downloader/` or custom override) by default. This directory is strictly listed in the `.gitignore` to prevent committing heavy media assets to your git history.

---

## 🚀 Script Overview

The application is modularized into dedicated scripts under `01_Downloader/`, orchestrated by `downloader.py` in the root:

### 1. Central Manager (`downloader.py`)
- Serves as the interactive CLI panel.
- Coordinates built-in scripts and registers custom downloader plugins.
- Dynamically loads modules, executes their standard `run()` functions, and manages the menu flow.

### 2. YouTube Downloader (`01_Downloader/yt_downloader.py`)
- **Engine**: Powered by `yt-dlp`.
- **Options**: Supports downloading single videos, playlists, or batch downloads from `yt_links.txt`.
- **Quality Options**: Extracts metadata to offer a list of resolutions (1080p, 720p, etc.).
- **Performance**: Integrates with `aria2c` (if available) for multi-connection accelerated downloading and `ffmpeg` for high-quality audio/video merging.

### 3. Instagram Downloader (`01_Downloader/ig_downloader.py`)
- **Engine**: Powered by `instaloader`.
- **Options**: Download by shortcode URL (post/reel), story URL, or profile URL/username.
- **Profiles**: Supports downloading profile posts, tagged posts, stories, or complete feeds.
- **Session Management**: Supports secure login credentials to access stories/private profiles, caching credentials inside `.{username}_session` files. Includes rate-limit detection to avoid Instagram bans.

### 4. Facebook Downloader (`01_Downloader/fb_downloader.py`)
- **Engine**: Powered by `yt-dlp`.
- **Options**: Single video URL downloads or bulk downloads from `fb_links.txt`.
- **Quality**: Always targets the highest video and audio streams (`bestvideo+bestaudio`) and merges them to `.mp4` using FFmpeg.

---

## 🛠️ Installation & Setup

### 1. Install Dependencies
Ensure you have Python 3.10+ installed. Install the required packages listed in `requirements.txt`:
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` in the root directory:
```bash
cp .env.example .env
```
Open `.env` and fill in the required fields:
- `IG_USERNAME` & `IG_PASSWORD`: Optional burner Instagram credentials for stories/private downloads.
- `FB_COOKIES_FILE`: Path to your exported Facebook cookies txt file for restricted videos.
- `FFMPEG_PATH`: Path to `ffmpeg.exe` if not set in your system's environment variables.
- `ARIA2C_PATH`: Path to `aria2c.exe` (optional, for faster YouTube downloads).
- `DOWNLOAD_DIR`: Absolute path to override where files are saved.
- `BULK_WORKERS`: Number of threads to use in bulk downloads (default: `4`).

### 3. FFmpeg and aria2c Setup
To merge high-definition audio and video streams correctly, FFmpeg must be installed.
For detailed instructions, check the guide in [FFMPEG_SETUP.md](file:///d:/02_CODE/98_PYTHON/01_Downloader/FFMPEG_SETUP.md).

---

## 🎮 How to Use

Simply execute `downloader.py` from the root directory:
```bash
python downloader.py
```

### Main Menu Options:
1. **YouTube Downloader**: Start downloading YouTube videos or playlists.
2. **Facebook Downloader**: Start downloading Facebook videos in HD.
3. **Instagram Downloader**: Start downloading Instagram posts, reels, stories, or profiles.
4. **Bulk Download (All Platforms)**: Trigger parallel downloads for all links entered inside `yt_links.txt`, `ig_links.txt`, and `fb_links.txt`.
5. **Settings / Status**: View system health/dependency statuses, check paths, or manage custom downloader plugins.
