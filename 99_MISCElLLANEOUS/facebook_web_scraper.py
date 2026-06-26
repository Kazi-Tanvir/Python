"""
Facebook Tuition Media Scraper v1.0
====================================
Scrapes public "Tuition Media" Facebook pages for tutoring job posts,
parses structured data using regex, and filters results based on
user-configurable preferences (location, subject, class, salary,
university, gender, etc.).

Extraction Methods:
  1. Playwright + stealth  — headless browser scraping (primary)
  2. Apify API             — cloud-based fallback (requires API key)

Usage:
  - As a module:  from _99_MISCElLLANEOUS.facebook_web_scraper import run; run()
  - Standalone:   python -m 99_MISCElLLANEOUS.facebook_web_scraper

Customisation:
  Edit the SCRAPER_CONFIG dict below to change preferences.
  Edit the REGEX patterns in _parse_post() to handle new post formats.
"""

import os
import re
import sys
import json
import time
import asyncio
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Resolve project root & add to path
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(_PROJECT_ROOT / ".env")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.theme import Theme

# ---------------------------------------------------------------------------
# Rich Theme & Console  (matches project style)
# ---------------------------------------------------------------------------
CUSTOM_THEME = Theme({
    "info": "cyan",
    "success": "bold green",
    "warning": "bold yellow",
    "error": "bold red",
    "title": "bold magenta",
    "subtitle": "dim white",
    "highlight": "bold cyan",
    "muted": "dim",
    "best": "bold green",
    "good": "bold yellow",
    "low": "dim white",
})

console = Console(theme=CUSTOM_THEME)


# ---------------------------------------------------------------------------
# Styled output helpers  (same API as 01_Downloader/utils.py)
# ---------------------------------------------------------------------------
def print_success(msg: str) -> None:
    console.print(f"  [success][+][/success] {msg}")

def print_error(msg: str) -> None:
    console.print(f"  [error][!][/error] {msg}")

def print_warning(msg: str) -> None:
    console.print(f"  [warning][*][/warning] {msg}")

def print_info(msg: str) -> None:
    console.print(f"  [info][>][/info] {msg}")

def print_banner(title: str, subtitle: str = "") -> None:
    content = Text(title, style="title", justify="center")
    if subtitle:
        content.append(f"\n{subtitle}", style="subtitle")
    console.print(Panel(content, border_style="bright_magenta", padding=(1, 4)))


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║                        CONFIGURATION SECTION                            ║
# ║                                                                         ║
# ║  Edit this dict to customise your preferences. The filtering engine     ║
# ║  compares parsed post data against these values to find best matches.   ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

SCRAPER_CONFIG = {
    # ── Target Facebook Page ──────────────────────────────────────────────
    # The public Facebook page URL to scrape.
    # You can change this to any "Tuition Media" page.
    "target_page_url": os.getenv(
        "FB_SCRAPER_TARGET_PAGE",
        "https://www.facebook.com/TuitionMediaBD",
    ),

    # ── Scraping Parameters ───────────────────────────────────────────────
    "max_posts": 30,           # Number of posts to try to load (20–50)
    "headless": True,          # Run browser in headless mode?
    "scroll_pause": 2.5,       # Seconds to wait between scroll actions
    "page_load_timeout": 30,   # Max seconds to wait for page load

    # ── Personal Preferences (Filtering) ──────────────────────────────────
    # Leave a list empty [] to skip that filter (i.e. accept any value).

    # Preferred locations in Dhaka (case-insensitive matching)
    "preferred_locations": [
        "Dhanmondi", "Gulshan", "Uttara", "Mirpur", "Banani",
        "Mohammadpur", "Lalmatia", "Jigatola",
    ],

    # Preferred subjects to teach
    "preferred_subjects": [
        "Math", "Higher Math", "Physics", "Chemistry",
    ],

    # Preferred class/standard of students
    "preferred_classes": [
        "Class 8", "Class 9", "Class 10",
        "SSC", "HSC",
        "O-Level", "A-Level",
    ],

    # Minimum acceptable salary in BDT (set to 0 to skip)
    "min_salary": 3000,

    # ── University Preference ─────────────────────────────────────────────
    # Some posts require tutors from specific universities.
    # List your university names here so the filter can match.
    # Example: ["BUET", "DU", "Dhaka University", "NSU", "BRAC"]
    "preferred_universities": [
        "BUET", "DU", "Dhaka University",
    ],

    # ── Gender Preference ─────────────────────────────────────────────────
    # Your gender — used to filter posts that require a specific gender.
    # Options: "Male", "Female", or "Any"
    # If set to "Male", posts requiring "Female only" will be filtered out,
    # and vice versa. "Any" means you accept all posts.
    "tutor_gender": "Male",

    # ── Medium Preference ─────────────────────────────────────────────────
    # Preferred teaching medium/version
    "preferred_medium": [
        "English Medium", "English Version", "Bangla Medium",
    ],

    # ── Days Per Week ─────────────────────────────────────────────────────
    # Preferred number of days per week (set to 0 to skip)
    "max_days_per_week": 0,

    # ── Output Settings ───────────────────────────────────────────────────
    "export_json": True,       # Export results to a JSON file?
    "export_dir": str(_PROJECT_ROOT / "99_MISCElLLANEOUS" / "scraper_output"),
}


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║                         DATA STRUCTURES                                 ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

@dataclass
class TuitionPost:
    """Represents a single parsed tuition job post."""
    raw_text: str = ""                      # The original post text
    post_url: str = ""                      # Direct link to the Facebook post
    tuition_id: str = ""                    # Tuition ID if mentioned (e.g. "TM-12345")

    # Extracted fields
    class_standard: str = ""                # e.g. "Class 8", "O-Level"
    subjects: list[str] = field(default_factory=list)
    location: str = ""                      # e.g. "Dhanmondi, Dhaka"
    salary: int = 0                         # Salary in BDT (0 = unknown/negotiable)
    salary_raw: str = ""                    # Raw salary text (e.g. "5000 tk", "Negotiable")
    gender_required: str = "Any"            # "Male", "Female", or "Any"
    university_required: str = ""           # e.g. "BUET preferred", "DU student"
    days_per_week: int = 0                  # e.g. 3, 5, 0=unknown
    medium: str = ""                        # e.g. "English Medium", "Bangla Medium"
    num_students: int = 1                   # Number of students (default 1)

    # Filtering results (set by the filtering engine)
    match_score: float = 0.0               # 0.0 – 100.0
    match_tier: str = "Low"                 # "Best", "Good", or "Low"
    match_reasons: list[str] = field(default_factory=list)  # Why it matched


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║                     REGEX / TEXT PARSING ENGINE                         ║
# ║                                                                         ║
# ║  HOW TO CUSTOMIZE:                                                      ║
# ║  Tuition Media pages use varied formats. If a page uses different       ║
# ║  wording, add new patterns to the relevant regex list below.            ║
# ║  All patterns are tried in order; the first match wins.                 ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# --- Class / Standard patterns ---
# These capture the class level from common Bengali tuition post formats.
# Add new patterns here if you encounter different wording.
CLASS_PATTERNS = [
    # "Class 8", "Class-8", "class: 8", "Class : 10"
    r'[Cc]lass[\s:\-]*(\d{1,2})',
    # "শ্রেণি ৮", "শ্রেণী ১০"  (Bengali digits)
    r'শ্রেণ[িী][\s:\-]*([\u09E6-\u09EF]+)',
    # "O-Level", "O Level", "A-Level", "A Level"
    r'([OoAa][\s\-]?[Ll]evel)',
    # "HSC", "SSC", "JSC"
    r'\b(HSC|SSC|JSC|hsc|ssc|jsc)\b',
    # "Honours", "Honors", "Masters"
    r'\b(Honours|Honors|Masters|Degree|ডিগ্রি|অনার্স|মাস্টার্স)\b',
    # "Admission" / "Varsity Admission"
    r'\b(Admission|ভর্তি)\b',
    # "Hifz", "Quran", "Arabic" — religious tuition
    r'\b(Hifz|Quran|Arabic|হিফয|কুরআন)\b',
    # "Cadet" preparation
    r'\b(Cadet|ক্যাডেট)\b',
]

# --- Subject patterns ---
# Known subject keywords. Case-insensitive matching is applied.
SUBJECT_KEYWORDS = [
    # English names
    "Math", "Mathematics", "Higher Math", "Higher Mathematics",
    "Physics", "Chemistry", "Biology",
    "English", "Bangla", "Bengali",
    "ICT", "Computer", "Computer Science",
    "Accounting", "Finance", "Economics", "Business Studies",
    "Science", "General Science",
    "Social Science", "History", "Geography",
    "Religion", "Islam", "Islamic Studies",
    "Arabic", "Quran",
    "Statistics", "Calculus",
    "All Subjects", "All subjects", "সকল বিষয়",
    # Bengali names
    "গণিত", "উচ্চতর গণিত", "পদার্থবিজ্ঞান", "রসায়ন", "জীববিজ্ঞান",
    "ইংরেজি", "বাংলা", "হিসাববিজ্ঞান",
]

# --- Location patterns ---
# Known Dhaka-area location names. Add more as needed.
LOCATION_KEYWORDS = [
    # Major areas
    "Dhanmondi", "Gulshan", "Banani", "Uttara", "Mirpur",
    "Mohammadpur", "Lalmatia", "Jigatola", "Shamoli", "Shyamoli",
    "Farmgate", "Tejgaon", "Motijheel", "Paltan", "Khilgaon",
    "Bashundhara", "Baridhara", "Badda", "Rampura", "Mugda",
    "Malibagh", "Moghbazar", "Shahbag", "Elephant Road",
    "Wari", "Old Dhaka", "Lalbagh", "Azimpur", "Nilkhet",
    "Savar", "Gazipur", "Tongi", "Narayanganj",
    "Kakrail", "Eskaton", "Green Road", "Panthapath",
    "Agargaon", "Mohakhali", "Cantonment",
    "Jatrabari", "Demra", "Keraniganj",
    "Dholaikhal", "Chawkbazar",
    # Bengali names
    "ধানমন্ডি", "গুলশান", "বনানী", "উত্তরা", "মিরপুর",
    "মোহাম্মদপুর", "লালমাটিয়া", "ফার্মগেট", "মতিঝিল",
    "বাড্ডা", "রামপুরা", "মালিবাগ", "শাহবাগ",
    "বসুন্ধরা", "বারিধারা",
]

# --- Salary patterns ---
SALARY_PATTERNS = [
    # "5000 tk", "5,000 TK", "8000/-", "10000 Taka"
    r'(\d[\d,]*)\s*(?:tk|taka|টাকা|/\-)',
    # "Salary: 5000", "Salary : 8,000"
    r'[Ss]alary[\s:]*(\d[\d,]*)',
    # "বেতন: ৫০০০", "বেতন ৮০০০"  (Bengali digits)
    r'বেতন[\s:]*([০-৯\d,]+)',
    # "Remuneration: 5000"
    r'[Rr]emuneration[\s:]*(\d[\d,]*)',
    # Negotiable
    r'(Negotiable|নেগোশিয়েবল|আলোচনা সাপেক্ষে)',
]

# --- Gender patterns ---
GENDER_PATTERNS = [
    # "Female tutor", "Male preferred", "পুরুষ", "মহিলা"
    r'\b(Female|মহিলা)\s*(?:tutor|teacher|শিক্ষক|preferred|only|preferable)?\b',
    r'\b(Male|পুরুষ)\s*(?:tutor|teacher|শিক্ষক|preferred|only|preferable)?\b',
    r'\b(?:tutor|teacher|শিক্ষক)\s*(?:gender|লিঙ্গ)[\s:]*\s*(Male|Female|Any|পুরুষ|মহিলা)\b',
    # "Only female", "Only male"
    r'\b[Oo]nly\s+(Male|Female|পুরুষ|মহিলা)\b',
    # "Gender: Male/Female"
    r'[Gg]ender[\s:]+\s*(Male|Female|Any|পুরুষ|মহিলা)',
]

# --- University patterns ---
UNIVERSITY_PATTERNS = [
    # "BUET student preferred", "DU student", "from BUET"
    r'\b(BUET|DU|KUET|RUET|CUET|SUST|JUST|BRAC|NSU|IUT|AUST|AIUB|UIU|EWU|DIU)\b',
    # "Dhaka University", "Rajshahi University"
    r'(Dhaka University|Rajshahi University|Chittagong University|Jahangirnagar University)',
    # "বুয়েট", "ঢাবি", "ঢাকা বিশ্ববিদ্যালয়"
    r'(বুয়েট|ঢাবি|ঢাকা বিশ্ববিদ্যালয়|রাবি|চবি|জবি|কুয়েট|রুয়েট)',
    # "University student", "Varsity student"
    r'(University|Varsity|বিশ্ববিদ্যালয়)\s*(?:student|ছাত্র|ছাত্রী)?',
    # "from <uni> preferred"
    r'from\s+([\w\s]+?)\s+(?:preferred|student)',
    # "Medical student", "Engineering student"
    r'(Medical|Engineering|মেডিকেল|ইঞ্জিনিয়ারিং)\s*(?:student|ছাত্র|ছাত্রী)',
]

# --- Days per week patterns ---
DAYS_PATTERNS = [
    # "3 days/week", "5 days per week", "৩ দিন"
    r'(\d)\s*(?:days?(?:/|\s*per\s*)week|দিন)',
    # "Days: 3", "Days : 5"
    r'[Dd]ays[\s:]*(\d)',
]

# --- Medium patterns ---
MEDIUM_PATTERNS = [
    r'(English Medium|English Version|Bangla Medium|Bengali Medium)',
    r'(ইংরেজি মাধ্যম|বাংলা মাধ্যম|ইংরেজি ভার্সন)',
    r'\b(Cambridge|Edexcel|IB)\b',
]

# --- Tuition ID patterns ---
ID_PATTERNS = [
    # "TM-12345", "ID: 12345", "Tuition ID: TM12345"
    r'(?:Tuition\s*)?(?:ID|আইডি)[\s:\-#]*([A-Za-z]*[\-]?\d{3,})',
    r'(TM[\-]?\d{3,})',
    r'#(\d{4,})',
]


def _bengali_to_int(text: str) -> int:
    """
    Convert a string that may contain Bengali digits (০-৯) to an integer.
    Falls back to standard int() for ASCII digits.
    """
    bengali_map = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
    cleaned = text.translate(bengali_map).replace(",", "").strip()
    try:
        return int(cleaned)
    except ValueError:
        return 0


def parse_post(raw_text: str, post_url: str = "") -> TuitionPost:
    """
    Parse a raw tuition post text and extract structured fields.

    This is the core parsing function. If a tuition agency uses a different
    format, add new regex patterns to the lists above.

    Args:
        raw_text: The full text of the Facebook post.
        post_url:  Direct URL to the post (for reference).

    Returns:
        A TuitionPost dataclass with all extracted fields populated.
    """
    post = TuitionPost(raw_text=raw_text, post_url=post_url)

    # ── Tuition ID ────────────────────────────────────────────────────────
    for pattern in ID_PATTERNS:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            post.tuition_id = match.group(1) if match.lastindex else match.group(0)
            break

    # ── Class / Standard ──────────────────────────────────────────────────
    for pattern in CLASS_PATTERNS:
        match = re.search(pattern, raw_text)
        if match:
            captured = match.group(1) if match.lastindex else match.group(0)
            # Normalise Bengali digits
            if any('\u09E6' <= ch <= '\u09EF' for ch in captured):
                captured = f"Class {_bengali_to_int(captured)}"
            # If we only captured a bare number (e.g. "10" from "Class: 10"),
            # prefix it with "Class " for readability
            elif captured.strip().isdigit():
                captured = f"Class {captured.strip()}"
            post.class_standard = captured.strip()
            break

    # ── Subjects ──────────────────────────────────────────────────────────
    # Check for each known subject keyword in the text (case-insensitive).
    # We preprocess the text to avoid false positives: "English Medium" and
    # "English Version" should NOT match the subject "English".
    subj_text = raw_text
    # Remove medium/version phrases so "English" only matches as a subject
    subj_text = re.sub(r'English\s+(?:Medium|Version)', '', subj_text, flags=re.IGNORECASE)
    subj_text = re.sub(r'Bangla\s+Medium', '', subj_text, flags=re.IGNORECASE)
    subj_text = re.sub(r'Bengali\s+Medium', '', subj_text, flags=re.IGNORECASE)

    found_subjects = []
    for subj in SUBJECT_KEYWORDS:
        # Use word-boundary matching to avoid partial matches
        if re.search(r'\b' + re.escape(subj) + r'\b', subj_text, re.IGNORECASE):
            # Avoid duplicates (e.g. "Math" and "Mathematics")
            normalised = subj.lower().replace("mathematics", "math")
            if normalised not in [s.lower().replace("mathematics", "math") for s in found_subjects]:
                found_subjects.append(subj)
    post.subjects = found_subjects

    # ── Location ──────────────────────────────────────────────────────────
    for loc in LOCATION_KEYWORDS:
        if re.search(r'\b' + re.escape(loc) + r'\b', raw_text, re.IGNORECASE):
            post.location = loc
            break  # Take the first match (most prominent location)

    # ── Salary ────────────────────────────────────────────────────────────
    for pattern in SALARY_PATTERNS:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            captured = match.group(1) if match.lastindex else match.group(0)
            if captured.lower() in ("negotiable", "নেগোশিয়েবল", "আলোচনা সাপেক্ষে"):
                post.salary_raw = "Negotiable"
                post.salary = 0
            else:
                post.salary = _bengali_to_int(captured)
                post.salary_raw = f"{post.salary} BDT"
            break

    # ── Gender ────────────────────────────────────────────────────────────
    for pattern in GENDER_PATTERNS:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            captured = match.group(1) if match.lastindex else match.group(0)
            captured_lower = captured.lower()
            if captured_lower in ("female", "মহিলা"):
                post.gender_required = "Female"
            elif captured_lower in ("male", "পুরুষ"):
                post.gender_required = "Male"
            else:
                post.gender_required = "Any"
            break

    # ── University ────────────────────────────────────────────────────────
    uni_parts = []
    for pattern in UNIVERSITY_PATTERNS:
        for match in re.finditer(pattern, raw_text, re.IGNORECASE):
            captured = match.group(1) if match.lastindex else match.group(0)
            if captured.strip() and captured.strip() not in uni_parts:
                uni_parts.append(captured.strip())
    post.university_required = ", ".join(uni_parts) if uni_parts else ""

    # ── Days per week ─────────────────────────────────────────────────────
    for pattern in DAYS_PATTERNS:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            post.days_per_week = _bengali_to_int(match.group(1))
            break

    # ── Medium ────────────────────────────────────────────────────────────
    for pattern in MEDIUM_PATTERNS:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            post.medium = match.group(1) if match.lastindex else match.group(0)
            break

    return post


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║                        FILTERING ENGINE                                 ║
# ║                                                                         ║
# ║  Compares parsed post data against SCRAPER_CONFIG preferences.          ║
# ║  Calculates a weighted match score (0–100).                             ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# Weights for each filter criterion (must sum to ~100 for clean percentages)
FILTER_WEIGHTS = {
    "location":   25,
    "subjects":   25,
    "class":      15,
    "salary":     10,
    "gender":     10,
    "university": 10,
    "medium":      5,
}


def filter_post(post: TuitionPost, config: dict = None) -> TuitionPost:
    """
    Score a parsed TuitionPost against user preferences.

    Modifies the post in-place, setting match_score, match_tier, and
    match_reasons. Returns the post for chaining.

    Scoring logic:
      - Each criterion has a weight (see FILTER_WEIGHTS).
      - If user has no preference for a criterion (empty list / 0),
        that criterion's weight is redistributed equally among the others.
      - A criterion scores its full weight if matched, 0 if not.

    Tiers:
      - "Best"  — score >= 70
      - "Good"  — score >= 40
      - "Low"   — score < 40
    """
    if config is None:
        config = SCRAPER_CONFIG

    reasons = []
    score = 0.0
    active_weight = 0.0  # Total weight of criteria that are actually used

    # ── Location ──────────────────────────────────────────────────────────
    pref_locations = [loc.lower() for loc in config.get("preferred_locations", [])]
    if pref_locations:
        active_weight += FILTER_WEIGHTS["location"]
        if post.location and post.location.lower() in pref_locations:
            score += FILTER_WEIGHTS["location"]
            reasons.append(f"[+] Location: {post.location}")
        elif not post.location:
            # Unknown location — give partial credit
            score += FILTER_WEIGHTS["location"] * 0.3
            reasons.append("[?] Location: unknown (partial credit)")

    # ── Subjects ──────────────────────────────────────────────────────────
    pref_subjects = [s.lower() for s in config.get("preferred_subjects", [])]
    if pref_subjects:
        active_weight += FILTER_WEIGHTS["subjects"]
        if post.subjects:
            post_subj_lower = [s.lower() for s in post.subjects]
            # Check if any of user's preferred subjects appear
            matched_subj = [s for s in pref_subjects if s in post_subj_lower]
            # Also accept "all subjects"
            if "all subjects" in post_subj_lower or "সকল বিষয়" in post_subj_lower:
                matched_subj = pref_subjects  # All subjects = match everything
                reasons.append("[+] Subjects: All Subjects")
            if matched_subj:
                # Proportional credit based on how many subjects matched
                ratio = len(matched_subj) / len(pref_subjects)
                score += FILTER_WEIGHTS["subjects"] * ratio
                if "all subjects" not in [s.lower() for s in post.subjects]:
                    reasons.append(f"[+] Subjects: {', '.join(matched_subj)}")

    # ── Class / Standard ──────────────────────────────────────────────────
    pref_classes = [c.lower() for c in config.get("preferred_classes", [])]
    if pref_classes:
        active_weight += FILTER_WEIGHTS["class"]
        if post.class_standard and post.class_standard.lower() in pref_classes:
            score += FILTER_WEIGHTS["class"]
            reasons.append(f"[+] Class: {post.class_standard}")

    # ── Salary ────────────────────────────────────────────────────────────
    min_salary = config.get("min_salary", 0)
    if min_salary > 0:
        active_weight += FILTER_WEIGHTS["salary"]
        if post.salary >= min_salary:
            score += FILTER_WEIGHTS["salary"]
            reasons.append(f"[+] Salary: {post.salary_raw} (>= {min_salary})")
        elif post.salary == 0 and post.salary_raw == "Negotiable":
            # Negotiable — give partial credit
            score += FILTER_WEIGHTS["salary"] * 0.5
            reasons.append("[?] Salary: Negotiable (partial credit)")
        elif post.salary == 0:
            # Unknown salary — give partial credit
            score += FILTER_WEIGHTS["salary"] * 0.3
            reasons.append("[?] Salary: unknown (partial credit)")

    # ── Gender ────────────────────────────────────────────────────────────
    tutor_gender = config.get("tutor_gender", "Any")
    if tutor_gender and tutor_gender != "Any":
        active_weight += FILTER_WEIGHTS["gender"]
        if post.gender_required == "Any" or post.gender_required == tutor_gender:
            score += FILTER_WEIGHTS["gender"]
            reasons.append(f"[+] Gender: {post.gender_required} (you: {tutor_gender})")
        else:
            # Gender mismatch — this is a hard filter, penalise heavily
            reasons.append(f"[-] Gender: requires {post.gender_required} (you: {tutor_gender})")

    # ── University ────────────────────────────────────────────────────────
    pref_unis = [u.lower() for u in config.get("preferred_universities", [])]
    if pref_unis:
        active_weight += FILTER_WEIGHTS["university"]
        if post.university_required:
            uni_lower = post.university_required.lower()
            if any(u in uni_lower for u in pref_unis):
                score += FILTER_WEIGHTS["university"]
                reasons.append(f"[+] University: {post.university_required}")
            else:
                reasons.append(f"[-] University: requires {post.university_required}")
        else:
            # No university requirement — give full credit (no restriction)
            score += FILTER_WEIGHTS["university"]
            reasons.append("[+] University: no restriction")

    # ── Medium ────────────────────────────────────────────────────────────
    pref_medium = [m.lower() for m in config.get("preferred_medium", [])]
    if pref_medium:
        active_weight += FILTER_WEIGHTS["medium"]
        if post.medium and post.medium.lower() in pref_medium:
            score += FILTER_WEIGHTS["medium"]
            reasons.append(f"[+] Medium: {post.medium}")
        elif not post.medium:
            score += FILTER_WEIGHTS["medium"] * 0.5
            reasons.append("[?] Medium: not specified (partial credit)")

    # ── Normalise score to 0–100 based on active weight ───────────────────
    if active_weight > 0:
        post.match_score = round((score / active_weight) * 100, 1)
    else:
        post.match_score = 50.0  # No preferences set, neutral score

    # ── Assign tier ───────────────────────────────────────────────────────
    if post.match_score >= 70:
        post.match_tier = "Best"
    elif post.match_score >= 40:
        post.match_tier = "Good"
    else:
        post.match_tier = "Low"

    post.match_reasons = reasons
    return post


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║              EXTRACTION METHOD 1: PLAYWRIGHT + STEALTH                  ║
# ║                                                                         ║
# ║  Uses a headless Chromium browser with stealth patches to bypass        ║
# ║  Facebook's anti-bot detection. Scrolls the page to load posts.         ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

async def _extract_posts_playwright(config: dict) -> list[dict]:
    """
    Scrape Facebook page posts using Playwright with stealth.

    Returns a list of dicts: [{"text": "...", "url": "..."}, ...]
    Each dict contains the raw post text and the post URL.

    Requires:
        pip install playwright playwright-stealth
        playwright install chromium
    """
    try:
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth
    except ImportError:
        print_error(
            "Playwright not installed. Run:\n"
            "    pip install playwright playwright-stealth\n"
            "    playwright install chromium"
        )
        return []

    target_urls = config["target_page_url"]
    if isinstance(target_urls, str):
        target_urls = [target_urls]

    max_posts = config.get("max_posts", 30)
    headless = config.get("headless", True)
    scroll_pause = config.get("scroll_pause", 2.5)
    timeout = config.get("page_load_timeout", 30) * 1000  # ms

    posts = []

    print_info(f"Launching Playwright (headless={headless})...")
    print_info(f"Targets: {', '.join(target_urls)}")

    async with async_playwright() as p:
        # Launch with stealth settings
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="Asia/Dhaka",
        )

        page = await context.new_page()

        # Apply stealth patches to avoid bot detection
        stealth = Stealth()
        await stealth.apply_stealth_async(page)

        try:
            for target_url in target_urls:
                print_info(f"Navigating to: {target_url}")
                try:
                    await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout)

                    # Wait for posts to appear — Facebook uses various selectors
                    await page.wait_for_timeout(3000)

                    # Close any login popups or cookie banners
                    for selector in [
                        '[aria-label="Close"]',
                        '[data-testid="cookie-policy-manage-dialog-accept-button"]',
                        'div[role="dialog"] [aria-label="Close"]',
                    ]:
                        try:
                            btn = page.locator(selector).first
                            if await btn.is_visible(timeout=2000):
                                await btn.click()
                                await page.wait_for_timeout(500)
                        except Exception:
                            pass

                    # Scroll to load more posts
                    print_info(f"Scrolling to load ~{max_posts} posts...")
                    prev_count = 0
                    scroll_attempts = 0
                    max_scroll_attempts = max_posts * 2  # Safety limit

                    while scroll_attempts < max_scroll_attempts:
                        # Count currently visible posts
                        # Facebook wraps each post in a div with role="article"
                        post_elements = page.locator('div[role="article"]')
                        current_count = await post_elements.count()

                        if current_count >= max_posts:
                            print_info(f"Loaded {current_count} posts (target: {max_posts})")
                            break

                        if current_count == prev_count:
                            scroll_attempts += 1
                            if scroll_attempts > 5:
                                print_warning(
                                    f"No new posts after {scroll_attempts} scrolls. "
                                    f"Got {current_count} posts."
                                )
                                break
                        else:
                            scroll_attempts = 0
                            prev_count = current_count

                        # Scroll down
                        await page.evaluate("window.scrollBy(0, window.innerHeight)")
                        await page.wait_for_timeout(int(scroll_pause * 1000))

                    # Extract post data
                    print_info("Extracting post data...")
                    post_elements = page.locator('div[role="article"]')
                    count = await post_elements.count()

                    extracted_count = 0
                    for i in range(min(count, max_posts)):
                        try:
                            el = post_elements.nth(i)
                            # Get the text content of the post
                            text = await el.inner_text()

                            # Try to find the permalink (timestamp link)
                            url = ""
                            links = el.locator('a[href*="/posts/"], a[href*="/permalink/"], a[href*="story_fbid"]')
                            link_count = await links.count()
                            if link_count > 0:
                                href = await links.first.get_attribute("href")
                                if href:
                                    # Normalise the URL
                                    if href.startswith("/"):
                                        url = f"https://www.facebook.com{href}"
                                    else:
                                        url = href

                            if text.strip():
                                posts.append({"text": text.strip(), "url": url})
                                extracted_count += 1

                        except Exception as e:
                            print_warning(f"Failed to extract post {i + 1}: {e}")
                            continue

                    print_success(f"Extracted {extracted_count} posts from: {target_url}")

                except Exception as e:
                    print_error(f"Error scraping {target_url}: {e}")
                    continue

        except Exception as e:
            print_error(f"Playwright browser error: {e}")

        finally:
            await browser.close()

    print_success(f"Total extracted {len(posts)} posts across all pages")
    return posts


def extract_posts_playwright(config: dict = None) -> list[dict]:
    """Synchronous wrapper for the async Playwright extraction."""
    if config is None:
        config = SCRAPER_CONFIG
    return asyncio.run(_extract_posts_playwright(config))


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║              EXTRACTION METHOD 2: APIFY API (FALLBACK)                  ║
# ║                                                                         ║
# ║  Uses Apify's Facebook Pages Scraper actor via their Python client.     ║
# ║  Requires an APIFY_API_TOKEN in .env.                                   ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

def extract_posts_apify(config: dict = None) -> list[dict]:
    """
    Scrape Facebook page posts using Apify's cloud scraper.

    This is the recommended fallback when Playwright can't get through
    Facebook's anti-bot walls (e.g. CAPTCHA, login walls).

    Requires:
        pip install apify-client
        Set APIFY_API_TOKEN in your .env file.
        (Get a free token at https://apify.com)

    Returns:
        A list of dicts: [{"text": "...", "url": "..."}, ...]
    """
    if config is None:
        config = SCRAPER_CONFIG

    api_token = os.getenv("APIFY_API_TOKEN", "").strip()
    if not api_token:
        print_error(
            "APIFY_API_TOKEN not set in .env\n"
            "  Get a free API token at https://apify.com\n"
            "  Then add to your .env file: APIFY_API_TOKEN=your_token_here"
        )
        return []

    try:
        from apify_client import ApifyClient
    except ImportError:
        print_error("apify-client not installed. Run: pip install apify-client")
        return []

    target_urls = config["target_page_url"]
    if isinstance(target_urls, str):
        target_urls = [target_urls]

    max_posts = config.get("max_posts", 30)

    print_info(f"Starting Apify scraper for: {', '.join(target_urls)}")
    print_info("This may take 1-3 minutes depending on your Apify plan...")

    client = ApifyClient(api_token)

    # Use the "apify/facebook-pages-scraper" actor
    # Docs: https://apify.com/apify/facebook-pages-scraper
    run_input = {
        "startUrls": [{"url": url} for url in target_urls],
        "maxPosts": max_posts,
        "maxPostComments": 0,
        "maxReviews": 0,
        "language": "en-US",
        "maxRetries": 3,
    }

    posts = []

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Running Apify actor...", total=None)

            run = client.actor("apify/facebook-pages-scraper").call(run_input=run_input)

            progress.update(task, description="Fetching results...")

            for item in client.dataset(run["defaultDatasetId"]).iterate_items():
                text = item.get("text", "")
                url = item.get("url", "") or item.get("postUrl", "")
                if text.strip():
                    posts.append({"text": text.strip(), "url": url})

        print_success(f"Extracted {len(posts)} posts via Apify")

    except Exception as e:
        print_error(f"Apify error: {e}")

    return posts


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║                         OUTPUT & DISPLAY                                ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

def display_results(posts: list[TuitionPost], config: dict = None) -> None:
    """
    Display filtered tuition posts as a rich table, sorted by match score.
    Best matches are highlighted in green at the top.
    """
    if config is None:
        config = SCRAPER_CONFIG

    if not posts:
        print_warning("No posts to display.")
        return

    # Sort by match score (highest first)
    sorted_posts = sorted(posts, key=lambda p: p.match_score, reverse=True)

    # ── Summary stats ─────────────────────────────────────────────────────
    best = sum(1 for p in sorted_posts if p.match_tier == "Best")
    good = sum(1 for p in sorted_posts if p.match_tier == "Good")
    low = sum(1 for p in sorted_posts if p.match_tier == "Low")

    console.print()
    console.print(
        Panel(
            f"[best]Best Matches: {best}[/best]  |  "
            f"[good]Good Matches: {good}[/good]  |  "
            f"[low]Low Matches: {low}[/low]  |  "
            f"Total: {len(sorted_posts)}",
            title="[bold]Results Summary[/bold]",
            border_style="bright_magenta",
            padding=(0, 2),
        )
    )

    # ── Results table ─────────────────────────────────────────────────────
    table = Table(
        title="Tuition Job Matches",
        border_style="bright_magenta",
        show_lines=True,
        title_style="bold bright_magenta",
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Score", justify="center", width=7)
    table.add_column("Tier", justify="center", width=6)
    table.add_column("ID", style="cyan", width=10)
    table.add_column("Class", width=12)
    table.add_column("Subjects", width=20)
    table.add_column("Location", width=14)
    table.add_column("Salary", width=12)
    table.add_column("Gender", justify="center", width=8)
    table.add_column("University", width=12)
    table.add_column("Medium", width=14)
    table.add_column("URL", style="dim", width=20, no_wrap=True)

    for i, post in enumerate(sorted_posts, 1):
        # Style based on tier
        tier_style = {"Best": "best", "Good": "good", "Low": "low"}.get(post.match_tier, "low")
        score_text = f"[{tier_style}]{post.match_score}%[/{tier_style}]"
        tier_text = f"[{tier_style}]{post.match_tier}[/{tier_style}]"

        # Truncate URL for display
        short_url = post.post_url[:35] + "..." if len(post.post_url) > 38 else post.post_url

        table.add_row(
            str(i),
            score_text,
            tier_text,
            post.tuition_id or "—",
            post.class_standard or "—",
            ", ".join(post.subjects) if post.subjects else "—",
            post.location or "—",
            post.salary_raw or "—",
            post.gender_required,
            post.university_required or "—",
            post.medium or "—",
            short_url or "—",
        )

    console.print()
    console.print(table)

    # ── Detailed view of Best matches ─────────────────────────────────────
    best_posts = [p for p in sorted_posts if p.match_tier == "Best"]
    if best_posts:
        console.print()
        console.print(
            Panel(
                "[bold]Detailed Best Matches[/bold]",
                border_style="green",
                padding=(0, 2),
            )
        )
        for i, post in enumerate(best_posts, 1):
            details = []
            details.append(f"[bold cyan]#{i}[/bold cyan]  Score: [best]{post.match_score}%[/best]")
            if post.tuition_id:
                details.append(f"  ID: {post.tuition_id}")
            details.append(f"  Class: {post.class_standard or '—'}")
            details.append(f"  Subjects: {', '.join(post.subjects) if post.subjects else '—'}")
            details.append(f"  Location: {post.location or '—'}")
            details.append(f"  Salary: {post.salary_raw or '—'}")
            details.append(f"  Gender: {post.gender_required}")
            details.append(f"  University: {post.university_required or '—'}")
            details.append(f"  Medium: {post.medium or '—'}")
            if post.post_url:
                details.append(f"  [dim]URL: {post.post_url}[/dim]")
            details.append("")
            details.append("  [dim]Match reasons:[/dim]")
            for reason in post.match_reasons:
                details.append(f"    {reason}")

            console.print(Panel(
                "\n".join(details),
                border_style="green",
                padding=(0, 2),
            ))


def export_results(posts: list[TuitionPost], config: dict = None) -> Optional[str]:
    """
    Export filtered results to a timestamped JSON file.

    Returns the path to the exported file, or None if export is disabled.
    """
    if config is None:
        config = SCRAPER_CONFIG

    if not config.get("export_json", True):
        return None

    export_dir = Path(config.get("export_dir", _PROJECT_ROOT / "99_MISCElLLANEOUS" / "scraper_output"))
    export_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"tuition_results_{timestamp}.json"
    filepath = export_dir / filename

    # Convert to serializable dicts (exclude raw_text to keep file clean)
    data = []
    for post in sorted(posts, key=lambda p: p.match_score, reverse=True):
        d = asdict(post)
        d.pop("raw_text", None)  # Raw text is verbose, skip it
        data.append(d)

    output = {
        "scraped_at": datetime.now().isoformat(),
        "target_page": config.get("target_page_url", ""),
        "total_posts": len(posts),
        "best_matches": sum(1 for p in posts if p.match_tier == "Best"),
        "good_matches": sum(1 for p in posts if p.match_tier == "Good"),
        "results": data,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print_success(f"Results exported to: {filepath}")
    return str(filepath)


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║                     PREFERENCES EDITOR                                  ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

def edit_preferences() -> None:
    """Interactive editor for scraper preferences."""
    console.print()
    console.print(
        Panel(
            "[bold]Current Preferences[/bold]",
            border_style="bright_magenta",
            padding=(0, 2),
        )
    )

    table = Table(border_style="bright_cyan", show_lines=True)
    table.add_column("Setting", style="bold cyan", min_width=20)
    table.add_column("Current Value", min_width=40)

    target_val = SCRAPER_CONFIG["target_page_url"]
    if isinstance(target_val, list):
        target_val = ", ".join(target_val)
    table.add_row("Target Page", target_val)
    table.add_row("Max Posts", str(SCRAPER_CONFIG["max_posts"]))
    table.add_row("Headless Mode", str(SCRAPER_CONFIG["headless"]))
    table.add_row("Preferred Locations", ", ".join(SCRAPER_CONFIG["preferred_locations"]))
    table.add_row("Preferred Subjects", ", ".join(SCRAPER_CONFIG["preferred_subjects"]))
    table.add_row("Preferred Classes", ", ".join(SCRAPER_CONFIG["preferred_classes"]))
    table.add_row("Min Salary", f"{SCRAPER_CONFIG['min_salary']} BDT")
    table.add_row("Preferred Universities", ", ".join(SCRAPER_CONFIG["preferred_universities"]))
    table.add_row("Tutor Gender", SCRAPER_CONFIG["tutor_gender"])
    table.add_row("Preferred Medium", ", ".join(SCRAPER_CONFIG["preferred_medium"]))
    table.add_row("Export JSON", str(SCRAPER_CONFIG["export_json"]))

    console.print(table)
    console.print()
    print_info(
        "To change preferences, edit the SCRAPER_CONFIG dict at the top of:\n"
        f"    {Path(__file__).resolve()}\n"
        "  Or set FB_SCRAPER_TARGET_PAGE in your .env file."
    )
    console.print()


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║                      MAIN PIPELINE                                      ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

def scrape_and_filter(method: str = "playwright", config: dict = None) -> list[TuitionPost]:
    """
    Full pipeline: extract → parse → filter → display → export.

    Args:
        method: "playwright" or "apify"
        config: Override SCRAPER_CONFIG (optional)

    Returns:
        List of filtered TuitionPost objects, sorted by score.
    """
    if config is None:
        config = SCRAPER_CONFIG

    # ── Step 1: Extract raw posts ─────────────────────────────────────────
    console.print()
    console.rule("[bold cyan]Step 1: Extracting Posts[/bold cyan]", style="bright_magenta")
    console.print()

    if method == "apify":
        raw_posts = extract_posts_apify(config)
    else:
        raw_posts = extract_posts_playwright(config)

    if not raw_posts:
        print_error("No posts extracted. Check your connection and try again.")
        return []

    # ── Step 2: Parse posts ───────────────────────────────────────────────
    console.print()
    console.rule("[bold cyan]Step 2: Parsing Posts[/bold cyan]", style="bright_magenta")
    console.print()

    parsed_posts = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Parsing {len(raw_posts)} posts...", total=len(raw_posts))

        for raw in raw_posts:
            post = parse_post(raw["text"], raw.get("url", ""))
            parsed_posts.append(post)
            progress.advance(task)

    print_success(f"Parsed {len(parsed_posts)} posts")

    # ── Step 3: Filter & score ────────────────────────────────────────────
    console.print()
    console.rule("[bold cyan]Step 3: Filtering & Scoring[/bold cyan]", style="bright_magenta")
    console.print()

    for post in parsed_posts:
        filter_post(post, config)

    # ── Step 4: Display results ───────────────────────────────────────────
    console.print()
    console.rule("[bold cyan]Step 4: Results[/bold cyan]", style="bright_magenta")

    display_results(parsed_posts, config)

    # ── Step 5: Export ────────────────────────────────────────────────────
    if config.get("export_json", True):
        console.print()
        export_results(parsed_posts, config)

    return parsed_posts


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║                   DEMO / TEST WITH SAMPLE DATA                          ║
# ║                                                                         ║
# ║  Run this to test the parser and filter without actually scraping       ║
# ║  Facebook. Uses realistic sample posts.                                 ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

SAMPLE_POSTS = [
    {
        "text": (
            "Tuition ID: TM-45231\n"
            "Class: 10 (SSC)\n"
            "Subject: Math, Higher Math\n"
            "Location: Dhanmondi, Dhaka\n"
            "Salary: 5000 tk\n"
            "Days: 3 days/week\n"
            "Gender: Male tutor preferred\n"
            "Medium: English Version\n"
            "University: BUET student preferred\n"
            "Contact: 01XXXXXXXXX"
        ),
        "url": "https://www.facebook.com/TuitionMediaBD/posts/12345",
    },
    {
        "text": (
            "#67890\n"
            "Need a Female tutor for Class 8 student.\n"
            "Subjects: English, Bangla, Science\n"
            "Area: Gulshan, Dhaka\n"
            "Salary: 8000 tk per month\n"
            "5 days/week\n"
            "Bangla Medium"
        ),
        "url": "https://www.facebook.com/TuitionMediaBD/posts/67890",
    },
    {
        "text": (
            "Tuition ID: TM-11223\n"
            "O-Level student needs help with Physics and Chemistry.\n"
            "Location: Uttara Sector 7, Dhaka\n"
            "Salary: Negotiable\n"
            "3 days per week\n"
            "English Medium\n"
            "DU or BUET student preferred"
        ),
        "url": "https://www.facebook.com/TuitionMediaBD/posts/11223",
    },
    {
        "text": (
            "Tuition Available!\n"
            "Class 9, All subjects\n"
            "Mirpur 10, Dhaka\n"
            "Salary: 4000 tk\n"
            "Male/Female any\n"
            "4 days/week"
        ),
        "url": "https://www.facebook.com/TuitionMediaBD/posts/99887",
    },
    {
        "text": (
            "HSC Physics & Chemistry tutor needed.\n"
            "Area: Mohammadpur, Dhaka\n"
            "Remuneration: 6000\n"
            "Only Male tutor\n"
            "Engineering student from BUET/KUET preferred\n"
            "English Version\n"
            "3 days/week"
        ),
        "url": "https://www.facebook.com/TuitionMediaBD/posts/55443",
    },
    {
        "text": (
            "A-Level (Cambridge) student.\n"
            "Needs tutor for Math and Physics.\n"
            "Banani DOHS area.\n"
            "Salary: 12000 tk\n"
            "Gender: Any\n"
            "BUET student highly preferred"
        ),
        "url": "https://www.facebook.com/TuitionMediaBD/posts/77665",
    },
]


def run_demo() -> None:
    """Run the parser & filter on sample data (no scraping required)."""
    print_banner("DEMO MODE", "Testing parser & filter with sample posts")
    console.print()
    print_info(f"Processing {len(SAMPLE_POSTS)} sample posts...")

    parsed = [parse_post(p["text"], p.get("url", "")) for p in SAMPLE_POSTS]
    for post in parsed:
        filter_post(post)

    display_results(parsed)

    if SCRAPER_CONFIG.get("export_json", True):
        export_results(parsed)


def _get_scraping_inputs() -> tuple[list[str], int]:
    """Prompt user for target links and max posts."""
    console.print()
    default_url = SCRAPER_CONFIG["target_page_url"]
    default_url_str = ", ".join(default_url) if isinstance(default_url, list) else default_url
    
    # Prompt for page URLs
    console.print(f"  [info]Press Enter to use default target URL: {default_url_str}[/info]")
    user_urls_input = Prompt.ask(
        "  Enter Facebook Page URL(s) to scrape\n  (comma-separated if multiple)"
    )
    if not user_urls_input.strip():
        urls = [default_url] if isinstance(default_url, str) else default_url
    else:
        urls = [url.strip() for url in user_urls_input.split(",") if url.strip()]

    # Prompt for number of posts
    default_max = str(SCRAPER_CONFIG["max_posts"])
    user_max_input = Prompt.ask(
        f"  Enter number of posts to load per page",
        default=default_max
    )
    try:
        max_posts = int(user_max_input)
    except ValueError:
        max_posts = SCRAPER_CONFIG["max_posts"]

    return urls, max_posts


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║                        INTERACTIVE MENU                                 ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

def run() -> None:
    """
    Main entry point — interactive Rich menu for the Facebook Tuition Scraper.
    Called by main.py's script launcher.
    """
    print_banner(
        "FACEBOOK TUITION SCRAPER",
        "Find the best tutoring jobs from Tuition Media pages"
    )

    while True:
        console.print()
        console.print(
            Panel(
                "[bold cyan]1[/]  Scrape & Filter (Playwright — recommended)\n"
                "[bold cyan]2[/]  Scrape & Filter (Apify — requires API key)\n"
                "[bold cyan]3[/]  Demo Mode (sample data, no scraping)\n"
                "[bold cyan]4[/]  View / Edit Preferences\n"
                "[bold cyan]0[/]  Back to Main Menu",
                title="[bold]Scraper Menu[/bold]",
                border_style="bright_magenta",
                padding=(1, 3),
            )
        )

        choice = Prompt.ask("  Choice", choices=["0", "1", "2", "3", "4"], default="1")

        if choice == "0":
            break
        elif choice == "1":
            urls, max_posts = _get_scraping_inputs()
            config = SCRAPER_CONFIG.copy()
            config["target_page_url"] = urls
            config["max_posts"] = max_posts
            scrape_and_filter(method="playwright", config=config)
        elif choice == "2":
            urls, max_posts = _get_scraping_inputs()
            config = SCRAPER_CONFIG.copy()
            config["target_page_url"] = urls
            config["max_posts"] = max_posts
            scrape_and_filter(method="apify", config=config)
        elif choice == "3":
            run_demo()
        elif choice == "4":
            edit_preferences()


# ---------------------------------------------------------------------------
# Standalone execution
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    run()
