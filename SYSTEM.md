# 🛠️ System Contributor Guide (`SYSTEM.md`)

This guide outlines the system architecture of the Python Toolkit, describes design patterns and conventions, and provides clear instructions on how to maintain, extend, and update the repository.

---

## 📐 Project Architecture

The toolkit functions as a lightweight, dynamic plugin orchestrator:
1. `main.py` is the single source of entry. It loads a menu registry of tools.
2. Built-in scripts are configured directly inside `main.py` in the `BUILTIN_SCRIPTS` dictionary.
3. Custom scripts are loaded from `scripts.json` (created dynamically when adding scripts).
4. Executing a script dynamically imports the package module via `importlib` and invokes its entry-point function (standardized as `run()`).
5. Common assets (console instances, styling, theme, path resolution, env loaders) are shared via the `shared/` package.

---

## 🎨 System Design Conventions

When writing new tools or packages for this repository, adhere strictly to these conventions:

### 1. CLI-First Design
* The project strongly favors Command Line Interfaces (CLI) and Terminal User Interfaces (TUI) over graphical window interfaces (GUI).
* Use the `rich` library for menu screens, progress bars, status tables, panels, and colored outputs.
* Build interactive Prompts using Rich's built-in `Prompt.ask()` and `Confirm.ask()` classes.

### 2. Package Entry Point
* Every script module must expose a single main runner function named `run()` that takes no arguments.
* Example:
  ```python
  def run() -> None:
      # Main logic here
  ```
* Avoid using `sys.exit(1)` inside modules meant to run under `main.py`, as this will terminate the entire launcher menu. Instead, return `None` or print errors gracefully.

### 3. Shared Console & Config
* Never instantiate duplicate `rich.console.Console` objects or redefine the theme color mapping.
* Never call standalone `load_dotenv()` or hardcode relative paths from `__file__`.
* Import everything from the shared package:
  ```python
  from shared.console import console, print_banner, print_success, print_error, print_info, print_warning
  from shared.config import PROJECT_ROOT, get_env
  ```

---

## 📥 Where to Put the Next Program

When you want to add a new script/utility, follow these step-by-step instructions:

### Step 1: Place the Script
Find the appropriate package directory for your tool:
* `downloader/` — Media download engines.
* `converter/` — PDF and archive builders.
* `pdf_tools/` — PDF readers, converters, and parsers.
* `scraper/` — Web scrapers and data extraction engines.
* `misc/` — General/miscellaneous scripts that don't fit the above categories.

Write your script inside the selected directory (e.g. `misc/data_analyzer.py`).

### Step 2: Implement the Entry Point
Within your script, write your main execution block inside a standard `run()` function. Utilize the shared packages:
```python
# misc/data_analyzer.py
from shared.console import console, print_banner, print_success
from shared.config import PROJECT_ROOT

def run() -> None:
    print_banner("Data Analyzer Tool", "Extracting insights")
    # Analysis logic here...
    print_success("Analysis complete.")
```

### Step 3: Register in the Launcher
Open `main.py` and register the script in the `BUILTIN_SCRIPTS` dictionary:
```python
    "data_analyzer": {
        "name": "Data Analyzer",
        "module": "misc.data_analyzer",
        "description": "Extracts statistical insights from logs",
        "entry": "run",
        "builtin": True,
    },
```
*(Alternatively, a user can register the script dynamically without editing code by going to: Settings / Status → Add Custom Script)*.

### Step 4: Document the Change
Update the version logs in [README.md](file:///d:/02_CODE/98_PYTHON/README.md) and the System Change Log below.

---

## 📁 Rules for Adding a New Folder

If you need to introduce a brand new category (e.g. `image_processing/` or `database/`):
1. **Lowercase Name**: The directory must be all lowercase and a valid Python identifier (no digits or spaces).
2. **Package Init**: You must create an `__init__.py` file inside the new folder (can be empty) to designate it as a Python package.
3. **Link File Inputs**: Put static lists or configuration files inside the root `config/` directory.
4. **Ignored Outputs**: If your package generates files (e.g., outputs, logs, artifacts), create a corresponding directory inside `output/` (e.g., `output/images/`) and ensure `output/` is listed in `.gitignore`.

---

## 📜 System Change Log

Tracks structural, architecture, and package-wide updates.

| Date | Version | Category | Description |
|------|---------|----------|-------------|
| 2026-06-26 | `v1.0.0` | Restructure | Eliminated digit-prefixed folder names. Created `shared/` console & config, moved inputs to `config/` and outputs to `output/`. Deleted redundant `downloader.py` entry point. Added `pyproject.toml` and `SYSTEM.md`. |
| 2025-07-08 | `v0.9.0` | Initial | Initial version with digit-prefixed directories (`01_Downloader`, `03_Converter`, `99_MISCElLLANEOUS`) and duplicate menu entries. |
