# FFmpeg Setup Guide

FFmpeg is required for merging separate video and audio streams into a single file.
Without it, downloads may be lower quality (single-stream only) or have no audio.

---

## Why FFmpeg is Needed

YouTube, Facebook, and many platforms serve high-quality video and audio as
**separate streams** (DASH format). To combine them into a single `.mp4` file,
you need FFmpeg.

**Without FFmpeg:**
- Videos may download without audio
- Quality may be limited to 720p or lower (single-stream fallback)
- Some formats won't be available

**With FFmpeg:**
- Full quality video + audio merged into .mp4
- Access to all available resolutions (including 4K)
- Proper subtitle embedding and format conversion

---

## Installation (Windows)

### Option 1: Manual Download (Recommended)

1. Go to: https://www.gyan.dev/ffmpeg/builds/
2. Download **ffmpeg-release-essentials.zip** (under "Release builds")
3. Extract the ZIP to a permanent location, e.g.:
   ```
   C:\ffmpeg\
   ```
4. Inside the extracted folder, find the `bin` directory containing:
   - `ffmpeg.exe`
   - `ffprobe.exe`
   - `ffplay.exe`

5. **Add to System PATH:**
   - Press `Win + S`, search "Environment Variables"
   - Click "Edit the system environment variables"
   - Click "Environment Variables..."
   - Under "System variables", find `Path` and click "Edit..."
   - Click "New" and add: `C:\ffmpeg\bin`
   - Click OK on all dialogs

6. **Verify** — Open a new terminal and run:
   ```
   ffmpeg -version
   ```
   You should see version info if it's set up correctly.

### Option 2: Using .env (Alternative)

If you don't want to modify your system PATH, set the FFmpeg location
in your `.env` file:

```env
FFMPEG_PATH=C:\ffmpeg\bin\ffmpeg.exe
```

The downloader will use this path automatically.

### Option 3: Package Managers

**Using Chocolatey:**
```
choco install ffmpeg
```

**Using Scoop:**
```
scoop install ffmpeg
```

**Using winget:**
```
winget install Gyan.FFmpeg
```

---

## aria2c Setup (Optional — Faster Downloads)

aria2c is a multi-connection download accelerator. When available, the YouTube
downloader uses it to download video fragments in parallel (up to 16 connections),
which can significantly speed up downloads.

### Installation

1. Go to: https://github.com/aria2/aria2/releases
2. Download the Windows build (e.g., `aria2-x.x.x-win-64bit-build1.zip`)
3. Extract to a permanent location, e.g.:
   ```
   C:\aria2\
   ```
4. Add `C:\aria2\` to your system PATH (same steps as FFmpeg above)

**Or using a package manager:**
```
choco install aria2
```
```
scoop install aria2
```

5. **Verify:**
   ```
   aria2c --version
   ```

### Alternative: Using .env

```env
ARIA2C_PATH=C:\aria2\aria2c.exe
```

---

## Verification

After setup, run the downloader and check "Settings / Status" from the main menu.
Both FFmpeg and aria2c should show as "Available" with their paths.

---

## Troubleshooting

**"ffmpeg is not recognized"**
- Make sure you added the `bin` folder (not the parent folder) to PATH
- Open a NEW terminal after changing PATH
- Try restarting your computer

**Videos still download without audio**
- Check that ffprobe.exe is also in the same directory as ffmpeg.exe
- Make sure the PATH points to the correct folder

**aria2c not detected**
- Same PATH troubleshooting as FFmpeg
- Or set ARIA2C_PATH in .env
