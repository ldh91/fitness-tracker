"""
fetch_hevy.py
-------------
Pulls workout data from the Hevy API and generates a detailed weekly report.
Every exercise compared against its exact week target from the 8-week bible.

Modes:
  --mode weekly  : Full weekly report (Sunday cron)
  --mode sync    : Check for new workouts since last sync, update if found (hourly)

Manual run:
  python scripts/fetch_hevy.py --mode weekly
  python scripts/fetch_hevy.py --mode sync
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────
HEVY_API_KEY = os.environ.get("HEVY_API_KEY")
HEVY_BASE_URL = "https://api.hevyapp.com/v1"
REPO_ROOT = Path(__file__).parent.parent
LAST_SYNC_FILE = REPO_ROOT / "data" / "last_sync.json"
PROGRAMME_START = datetime(2026, 3, 28, tzinfo=timezone.utc)

# ── Full 8-week progression table ──────────────────────────────
# Each exercise has a "weeks" list of 8 entries.
# Each entry is a dict with keys: heavy, volume, both
# Each value is a tuple: (sets, reps, weight_kg)  — weight None = bodyweight
# "heavy" = Monday Push / Tuesday Pull
# "volume" = Thursday Push / Friday Pull
# "both" = same target both sessions (legs, single-day exercises)

PROGRESSION = {

    # ════════════════════════════════════════════════
    # PUSH — CHEST
    # ════════════════════════════════════════════════
    "Bench Press (Barbell)": {
        "priority": True,
        "weeks": [
            {"heavy": (4,  5, 65.0),  "volume": (3, 10, 55.0)},
            {"heavy": (4,  5, 65.0),  "volume": (3, 10, 55.0)},
            {"heavy": (4,  5, 67.5),  "volume": (3, 10, 57.5)},
            {"heavy": (4,  5, 67.5),  "volume": (3, 10, 57.5)},
            {"heavy": (4,  5, 70.0),  "volume": (3, 10, 60.0)},
            {"heavy": (4,  5, 70.0),  "volume": (3, 10, 60.0)},
            {"heavy": (4,  5, 72.5),  "volume": (3, 10, 62.5)},
            {"heavy": (4,  5, 72.5),  "volume": (3, 10, 62.5)},
        ],
    },
    "Iso-Lateral Chest Press (Machine)": {
        "weeks": [
            {"heavy": (3, 10, 50.0), "volume": (3, 12, 45.0)},
            {"heavy": (3, 10, 50.0), "volume": (3, 12, 45.0)},
            {"heavy": (3, 10, 52.5), "volume": (3, 12, 47.5)},
            {"heavy": (3, 10, 52.5), "volume": (3, 12, 47.5)},
            {"heavy": (3, 10, 55.0), "volume": (3, 12, 50.0)},
            {"heavy": (3, 10, 55.0), "volume": (3, 12, 50.0)},
            {"heavy": (3, 10, 57.5), "volume": (3, 12, 52.5)},
            {"heavy": (3, 10, 57.5), "volume": (3, 12, 52.5)},
        ],
    },
    "Chest Fly (Machine)": {
        "weeks": [
            {"heavy": (3, 12, 77.0), "volume": (3, 15, 70.0)},
            {"heavy": (3, 12, 77.0), "volume": (3, 15, 70.0)},
            {"heavy": (3, 12, 80.0), "volume": (3, 15, 73.0)},
            {"heavy": (3, 12, 80.0), "volume": (3, 15, 73.0)},
            {"heavy": (3, 12, 82.0), "volume": (3, 15, 77.0)},
            {"heavy": (3, 12, 82.0), "volume": (3, 15, 77.0)},
            {"heavy": (3, 12, 85.0), "volume": (3, 15, 80.0)},
            {"heavy": (3, 12, 85.0), "volume": (3, 15, 80.0)},
        ],
    },

    # ════════════════════════════════════════════════
    # PUSH — SHOULDERS
    # ════════════════════════════════════════════════
    "Shoulder Press (Machine Plates)": {
        "weeks": [
            {"heavy": (4, 10, 20.0), "volume": (3, 12, 17.5)},
            {"heavy": (4, 10, 20.0), "volume": (3, 12, 17.5)},
            {"heavy": (4, 10, 20.0), "volume": (3, 12, 17.5)},
            {"heavy": (4, 10, 22.5), "volume": (3, 12, 20.0)},
            {"heavy": (4, 10, 22.5), "volume": (3, 12, 20.0)},
            {"heavy": (4, 10, 22.5), "volume": (3, 12, 20.0)},
            {"heavy": (4, 10, 25.0), "volume": (3, 12, 22.5)},
            {"heavy": (4, 10, 25.0), "volume": (3, 12, 22.5)},
        ],
    },
    "Lateral Raise (Machine)": {
        "weeks": [
            {"heavy": (3, 12, 42.5), "volume": (4, 12, 42.5)},
            {"heavy": (3, 12, 42.5), "volume": (4, 12, 42.5)},
            {"heavy": (3, 12, 45.0), "volume": (4, 12, 45.0)},
            {"heavy": (3, 12, 45.0), "volume": (4, 12, 45.0)},
            {"heavy": (3, 12, 47.5), "volume": (4, 12, 47.5)},
            {"heavy": (3, 12, 47.5), "volume": (4, 12, 47.5)},
            {"heavy": (3, 12, 50.0), "volume": (4, 12, 50.0)},
            {"heavy": (3, 12, 50.0), "volume": (4, 12, 50.0)},
        ],
    },
    "Single Arm Lateral Raise (Cable)": {
        "reps_note": "each side",
        "weeks": [
            {"volume": (3, 12, 7.5)},
            {"volume": (3, 12, 7.5)},
            {"volume": (3, 12, 7.5)},
            {"volume": (3, 12, 8.75)},
            {"volume": (3, 12, 8.75)},
            {"volume": (3, 12, 8.75)},
            {"volume": (3, 12, 10.0)},
            {"volume": (3, 12, 10.0)},
        ],
    },

    # ════════════════════════════════════════════════
    # PUSH — TRICEPS
    # ════════════════════════════════════════════════
    "Triceps Dip": {
        "weight_note": "added via belt/DB",
        "weeks": [
            {"both": (3, 12, None)},
            {"both": (3, 12, None)},
            {"both": (3, 12, 5.0)},
            {"both": (3, 12, 5.0)},
            {"both": (3, 12, 7.5)},
            {"both": (3, 12, 7.5)},
            {"both": (3, 12, 10.0)},
            {"both": (3, 12, 10.0)},
        ],
    },
    "Triceps Pushdown": {
        "weeks": [
            {"heavy": (3, 12, 60.0)},
            {"heavy": (3, 12, 60.0)},
            {"heavy": (3, 12, 62.5)},
            {"heavy": (3, 12, 62.5)},
            {"heavy": (3, 12, 65.0)},
            {"heavy": (3, 12, 65.0)},
            {"heavy": (3, 12, 67.5)},
            {"heavy": (3, 12, 67.5)},
        ],
    },
    "Single Arm Triceps Pushdown (Cable)": {
        "reps_note": "each side",
        "weeks": [
            {"volume": (3, 12, 22.5)},
            {"volume": (3, 12, 22.5)},
            {"volume": (3, 12, 22.5)},
            {"volume": (3, 12, 25.0)},
            {"volume": (3, 12, 25.0)},
            {"volume": (3, 12, 25.0)},
            {"volume": (3, 12, 27.5)},
            {"volume": (3, 12, 27.5)},
        ],
    },

    # ════════════════════════════════════════════════
    # PULL — BACK
    # ════════════════════════════════════════════════
    "Pull Up (Weighted)": {
        "priority": True,
        "weeks": [
            {"heavy": (3, 6,  5.0),  "volume": (3, 5,  5.0)},
            {"heavy": (3, 7,  5.0),  "volume": (3, 6,  5.0)},
            {"heavy": (3, 8,  5.0),  "volume": (3, 6,  5.0)},
            {"heavy": (3, 5,  7.5),  "volume": (3, 4,  7.5)},
            {"heavy": (3, 6,  7.5),  "volume": (3, 5,  7.5)},
            {"heavy": (3, 7,  7.5),  "volume": (3, 6,  7.5)},
            {"heavy": (3, 8,  7.5),  "volume": (3, 7,  7.5)},
            {"heavy": (3, 5, 10.0),  "volume": (3, 4, 10.0)},
        ],
    },
    "Pull Up": {
        "note": "Drop sets after weighted — sub-maximal, never to failure",
        "weeks": [
            {"both": (3, 5, None)},
            {"both": (3, 6, None)},
            {"both": (3, 6, None)},
            {"both": (3, 6, None)},
            {"both": (3, 6, None)},
            {"both": (3, 6, None)},
            {"both": (3, 7, None)},
            {"both": (3, 7, None)},
        ],
    },
    "Chin Up": {
        "weeks": (
            [{"both": (3, 4, None)}] * 4 +
            [{"both": (3, 5, None)}] * 2 +
            [{"both": (3, 6, None)}] * 2
        ),
    },
    "Iso-Lateral Row (Machine)": {
        "weeks": [
            {"heavy": (3, 10, 85.0),  "volume": (3, 12, 80.0)},
            {"heavy": (3, 10, 85.0),  "volume": (3, 12, 80.0)},
            {"heavy": (3, 10, 90.0),  "volume": (3, 12, 85.0)},
            {"heavy": (3, 10, 90.0),  "volume": (3, 12, 85.0)},
            {"heavy": (3, 10, 92.5),  "volume": (3, 12, 87.5)},
            {"heavy": (3, 10, 92.5),  "volume": (3, 12, 87.5)},
            {"heavy": (3, 10, 95.0),  "volume": (3, 12, 90.0)},
            {"heavy": (3, 10, 95.0),  "volume": (3, 12, 90.0)},
        ],
    },
    "Seated Cable Row - Bar Grip": {
        "weeks": [
            {"both": (3, 10, 75.0)},
            {"both": (3, 10, 75.0)},
            {"both": (3, 10, 77.5)},
            {"both": (3, 10, 77.5)},
            {"both": (3, 10, 80.0)},
            {"both": (3, 10, 80.0)},
            {"both": (3, 10, 82.5)},
            {"both": (3, 10, 82.5)},
        ],
    },
    "Lat Pulldown (Cable)": {
        "weeks": [
            {"volume": (4, 12, 87.5)},
            {"volume": (4, 12, 87.5)},
            {"volume": (4, 12, 90.0)},
            {"volume": (4, 12, 90.0)},
            {"volume": (4, 12, 92.5)},
            {"volume": (4, 12, 92.5)},
            {"volume": (4, 12, 95.0)},
            {"volume": (4, 12, 95.0)},
        ],
    },

    # ════════════════════════════════════════════════
    # PULL — REAR DELT & FACE PULL
    # ════════════════════════════════════════════════
    "Rear Delt Reverse Fly (Machine)": {
        "weeks": [
            {"heavy": (3, 12, 63.0), "volume": (3, 15, 60.0)},
            {"heavy": (3, 12, 63.0), "volume": (3, 15, 60.0)},
            {"heavy": (3, 12, 66.0), "volume": (3, 15, 63.0)},
            {"heavy": (3, 12, 66.0), "volume": (3, 15, 63.0)},
            {"heavy": (3, 12, 70.0), "volume": (3, 15, 66.0)},
            {"heavy": (3, 12, 70.0), "volume": (3, 15, 66.0)},
            {"heavy": (3, 12, 73.0), "volume": (3, 15, 70.0)},
            {"heavy": (3, 12, 73.0), "volume": (3, 15, 70.0)},
        ],
    },
    "Face Pull (Cable)": {
        "note": "Never ego lift — light, high reps, external rotation focus",
        "weeks": [
            {"heavy": (3, 15, 25.0), "volume": (3, 20, 20.0)},
            {"heavy": (3, 15, 25.0), "volume": (3, 20, 20.0)},
            {"heavy": (3, 15, 27.5), "volume": (3, 20, 22.5)},
            {"heavy": (3, 15, 27.5), "volume": (3, 20, 22.5)},
            {"heavy": (3, 15, 27.5), "volume": (3, 20, 22.5)},
            {"heavy": (3, 15, 30.0), "volume": (3, 20, 25.0)},
            {"heavy": (3, 15, 30.0), "volume": (3, 20, 25.0)},
            {"heavy": (3, 15, 30.0), "volume": (3, 20, 25.0)},
        ],
    },

    # ════════════════════════════════════════════════
    # PULL — BICEPS & TRAPS
    # ════════════════════════════════════════════════
    "Bicep Curl (Dumbbell)": {
        "weeks": [
            {"heavy": (3, 10, 12.5), "volume": (3, 12, 12.5)},
            {"heavy": (3, 10, 12.5), "volume": (3, 12, 12.5)},
            {"heavy": (3, 10, 12.5), "volume": (3, 12, 12.5)},
            {"heavy": (3, 10, 14.0), "volume": (3, 12, 14.0)},
            {"heavy": (3, 10, 14.0), "volume": (3, 12, 14.0)},
            {"heavy": (3, 10, 14.0), "volume": (3, 12, 14.0)},
            {"heavy": (3, 10, 15.0), "volume": (3, 12, 15.0)},
            {"heavy": (3, 10, 15.0), "volume": (3, 12, 15.0)},
        ],
    },
    "Hammer Curl (Dumbbell)": {
        "weeks": [
            {"both": (3, 10, 15.0)},
            {"both": (3, 11, 15.0)},
            {"both": (3, 12, 15.0)},
            {"both": (3, 10, 16.25)},
            {"both": (3, 11, 16.25)},
            {"both": (3, 12, 16.25)},
            {"both": (3, 10, 17.5)},
            {"both": (3, 11, 17.5)},
        ],
    },
    "Reverse Curl (Barbell)": {
        "weeks": [
            {"both": (3, 12, 12.5)},
            {"both": (3, 12, 12.5)},
            {"both": (3, 12, 12.5)},
            {"both": (3, 12, 15.0)},
            {"both": (3, 12, 15.0)},
            {"both": (3, 12, 15.0)},
            {"both": (3, 12, 17.5)},
            {"both": (3, 12, 17.5)},
        ],
    },
    "T Bar Shrugs": {
        "weeks": [
            {"heavy": (3, 12, 40.0), "volume": (3, 15, 35.0)},
            {"heavy": (3, 12, 40.0), "volume": (3, 15, 35.0)},
            {"heavy": (3, 12, 42.5), "volume": (3, 15, 37.5)},
            {"heavy": (3, 12, 42.5), "volume": (3, 15, 37.5)},
            {"heavy": (3, 12, 45.0), "volume": (3, 15, 40.0)},
            {"heavy": (3, 12, 45.0), "volume": (3, 15, 40.0)},
            {"heavy": (3, 12, 47.5), "volume": (3, 15, 42.5)},
            {"heavy": (3, 12, 47.5), "volume": (3, 15, 42.5)},
        ],
    },

    # ════════════════════════════════════════════════
    # LEGS — QUADS
    # ════════════════════════════════════════════════
    "Leg Extension (Machine)": {
        "weeks": [
            {"both": (3, 12, 65.0)},
            {"both": (3, 12, 65.0)},
            {"both": (3, 12, 70.0)},
            {"both": (3, 12, 70.0)},
            {"both": (3, 12, 72.5)},
            {"both": (3, 12, 72.5)},
            {"both": (3, 12, 75.0)},
            {"both": (3, 12, 75.0)},
        ],
    },
    "Leg Press (Machine)": {
        "priority": True,
        "weeks": [
            {"both": (4, 12, 150.0)},
            {"both": (4, 12, 150.0)},
            {"both": (4, 11, 155.0)},
            {"both": (4, 10, 160.0)},
            {"both": (4, 11, 160.0)},
            {"both": (4, 10, 165.0)},
            {"both": (4, 11, 165.0)},
            {"both": (4, 10, 170.0)},
        ],
    },
    "Bulgarian Split Squat": {
        "reps_note": "each leg",
        "note": "BW only weeks 1-2. Add DBs week 3 if pain-free. STOP if lower back twinges.",
        "weeks": [
            {"both": (3, 8, None)},
            {"both": (3, 8, None)},
            {"both": (3, 8, 5.0)},
            {"both": (3, 8, 5.0)},
            {"both": (3, 8, 7.5)},
            {"both": (3, 8, 7.5)},
            {"both": (3, 8, 10.0)},
            {"both": (3, 8, 10.0)},
        ],
    },

    # ════════════════════════════════════════════════
    # LEGS — HAMSTRINGS & GLUTES
    # ════════════════════════════════════════════════
    "Romanian Deadlift (Cable)": {
        "note": "CABLE ONLY — never barbell. Hold 30kg for first 4 weeks regardless of feel.",
        "weeks": [
            {"both": (3, 12, 30.0)},
            {"both": (3, 12, 30.0)},
            {"both": (3, 12, 30.0)},
            {"both": (3, 12, 30.0)},
            {"both": (3, 12, 32.5)},
            {"both": (3, 12, 32.5)},
            {"both": (3, 12, 35.0)},
            {"both": (3, 12, 35.0)},
        ],
    },
    "Cable Pull-Through": {
        "weeks": [
            {"both": (3, 15, 25.0)},
            {"both": (3, 15, 25.0)},
            {"both": (3, 15, 27.5)},
            {"both": (3, 15, 27.5)},
            {"both": (3, 15, 30.0)},
            {"both": (3, 15, 30.0)},
            {"both": (3, 15, 32.5)},
            {"both": (3, 15, 32.5)},
        ],
    },
    "Seated Leg Curl (Machine)": {
        "priority": True,
        "weeks": [
            {"both": (3, 12, 100.0)},
            {"both": (3, 12, 100.0)},
            {"both": (3, 12, 102.5)},
            {"both": (3, 12, 105.0)},
            {"both": (3, 12, 107.5)},
            {"both": (3, 12, 107.5)},
            {"both": (3, 12, 110.0)},
            {"both": (3, 12, 110.0)},
        ],
    },

    # ════════════════════════════════════════════════
    # LEGS — CALVES
    # ════════════════════════════════════════════════
    "Standing Calf Raise (Machine)": {
        "weeks": [
            {"both": (4, 12, 120.0)},
            {"both": (4, 12, 120.0)},
            {"both": (4, 12, 125.0)},
            {"both": (4, 12, 125.0)},
            {"both": (4, 12, 130.0)},
            {"both": (4, 12, 130.0)},
            {"both": (4, 12, 135.0)},
            {"both": (4, 12, 135.0)},
        ],
    },

    # ════════════════════════════════════════════════
    # CORE
    # ════════════════════════════════════════════════
    "Plank": {
        "weeks": [
            {"both": (3, "40s", None)},
            {"both": (3, "40s", None)},
            {"both": (3, "45s", None)},
            {"both": (3, "45s", None)},
            {"both": (3, "50s", None)},
            {"both": (3, "50s", None)},
            {"both": (3, "55s", None)},
            {"both": (3, "60s", None)},
        ],
    },
    "Dead Hang": {
        "note": "Primer — spine decompression",
        "weeks": [{"both": (2, "40s", None)}] * 8,
    },
    "Scapular Pull Ups": {
        "note": "Primer — shoulder activation",
        "weeks": [{"both": (2, 5, None)}] * 8,
    },
}

# ── Session type detection ──────────────────────────────────────
HEAVY_KEYWORDS = ["heavy", "monday", "push day", "pull day", "back/biceps", "chest/triceps"]
VOLUME_KEYWORDS = ["volume", "thursday", "friday"]


def detect_session_type(workout_title):
    t = workout_title.lower()
    if any(k in t for k in HEAVY_KEYWORDS):
        return "heavy"
    if any(k in t for k in VOLUME_KEYWORDS):
        return "volume"
    return "both"


# ── Hevy API ────────────────────────────────────────────────────

def hevy_get(endpoint, params=None):
    if not HEVY_API_KEY:
        raise ValueError("HEVY_API_KEY environment variable not set.")
    headers = {"api-key": HEVY_API_KEY, "accept": "application/json"}
    resp = requests.get(
        f"{HEVY_BASE_URL}/{endpoint}",
        headers=headers, params=params, timeout=30
    )
    resp.raise_for_status()
    return resp.json()


def fetch_workouts_since(since_dt):
    all_workouts = []
    page = 1
    since_str = since_dt.isoformat()
    while True:
        data = hevy_get("workouts", params={"page": page, "pageSize": 10})
        workouts = data.get("workouts", [])
        if not workouts:
            break
        for w in workouts:
            if w.get("start_time", "") >= since_str:
                all_workouts.append(w)
            else:
                return all_workouts
        if page >= data.get("page_count", 1):
            break
        page += 1
    return all_workouts


# ── Programme helpers ───────────────────────────────────────────

def get_current_week():
    delta = (datetime.now(timezone.utc) - PROGRAMME_START).days
    return max(1, min(8, (delta // 7) + 1))


def get_target(ex_name, week_number, session_type):
    prog = PROGRESSION.get(ex_name)
    if not prog:
        return None
    wk = prog["weeks"][min(week_number - 1, 7)]
    # Priority: match session type, fall back to "both"
    for key in [session_type, "both", "heavy", "volume"]:
        if key in wk:
            s, r, w = wk[key]
            return {"sets": s, "reps": r, "weight": w}
    return None


# ── Formatting helpers ──────────────────────────────────────────

def fmt_weight(w):
    return f"{w}kg" if w and w > 0 else "BW"


def fmt_target(target, reps_note=""):
    if not target:
        return "—"
    s, r, w = target["sets"], target["reps"], target["weight"]
    rn = f" {reps_note}" if reps_note else ""
    return f"{s}×{r}{rn} @ {fmt_weight(w)}"


def fmt_sets_detail(working_sets):
    parts = []
    for i, s in enumerate(working_sets, 1):
        w = s["weight_kg"]
        r = s["reps"]
        d = s.get("duration_s", 0)
        if w > 0 and r > 0:
            parts.append(f"S{i}: {w}kg×{r}")
        elif w > 0 and d > 0:
            parts.append(f"S{i}: {w}kg×{d}s")
        elif r > 0:
            parts.append(f"S{i}: BW×{r}")
        elif d > 0:
            parts.append(f"S{i}: {d}s")
    return "  |  ".join(parts) if parts else "—"


def assess(actual_sets, actual_weight, actual_best_reps,
           target_sets, target_weight, target_reps):
    if actual_sets == 0:
        return "❌", "Not logged"
    if isinstance(target_reps, str):
        return ("✅", "Timed sets completed") if actual_sets >= target_sets else ("⚠️", "Sets short")

    if target_weight and actual_weight < target_weight - 0.1:
        return "❌", f"Weight {target_weight - actual_weight:.1f}kg short ({actual_weight}kg vs {target_weight}kg)"
    if target_weight and actual_weight > target_weight + 0.1:
        return "🚀", f"Ahead — {actual_weight}kg vs {target_weight}kg target"
    if actual_sets < target_sets:
        return "⚠️", f"Sets short: {actual_sets}/{target_sets}"
    if target_reps and actual_best_reps < target_reps - 1:
        return "⚠️", f"Reps short: {actual_best_reps} vs {target_reps} target on best set"
    if target_reps and actual_best_reps == target_reps - 1:
        return "⚠️", "1 rep short of target on best set — very close"
    return "✅", "Target hit"


# ── Extract exercise entries ────────────────────────────────────

def extract_exercises(workouts):
    entries = []
    for w in workouts:
        title = w.get("title", "Unknown")
        date = w.get("start_time", "")[:10]
        session_type = detect_session_type(title)
        duration_min = round((w.get("duration") or 0) / 60)

        for ex in w.get("exercises", []):
            ex_name = ex.get("title", "Unknown")
            working = []
            warmups = []
            for s in ex.get("sets", []):
                item = {
                    "weight_kg": float(s.get("weight_kg") or 0),
                    "reps": int(s.get("reps") or 0),
                    "duration_s": int(s.get("duration_seconds") or 0),
                    "type": s.get("type", "normal"),
                }
                if item["type"] == "warmup":
                    warmups.append(item)
                elif item["type"] == "normal":
                    working.append(item)

            if working or warmups:
                best_w = max((s["weight_kg"] for s in working), default=0)
                best_r = max((s["reps"] for s in working), default=0)
                entries.append({
                    "exercise": ex_name,
                    "workout_title": title,
                    "workout_date": date,
                    "session_type": session_type,
                    "working_sets": working,
                    "warmup_sets": warmups,
                    "n_working": len(working),
                    "best_weight": best_w,
                    "best_reps": best_r,
                })
    return entries


def group_by_exercise(entries):
    g = {}
    for e in entries:
        g.setdefault(e["exercise"], []).append(e)
    return g


# ── Build exercise analysis section ────────────────────────────

def exercise_section(ex_names, section_title, grouped, week_number):
    lines = [f"\n### {section_title}\n"]

    for ex_name in ex_names:
        prog = PROGRESSION.get(ex_name, {})
        is_priority = prog.get("priority", False)
        note = prog.get("note", "")
        reps_note = prog.get("reps_note", "")
        entries = grouped.get(ex_name, [])

        star = " ⭐" if is_priority else ""
        lines.append(f"\n#### {ex_name}{star}")

        if note:
            lines.append(f"> ⚠️ {note}\n")

        if not entries:
            # Show what was expected but wasn't done
            target = get_target(ex_name, week_number, "both")
            if not target:
                target = get_target(ex_name, week_number, "heavy")
            if target:
                t_str = fmt_target(target, reps_note)
                lines.append("| Session | Target | Actual | Status |")
                lines.append("|---|---|---|---|")
                lines.append(f"| — | {t_str} | Not logged | ❌ Missing |")
            continue

        lines.append("| Date | Session | Target | Actual | Status | All Sets |")
        lines.append("|---|---|---|---|---|---|")

        for entry in sorted(entries, key=lambda x: x["workout_date"]):
            date = entry["workout_date"]
            session_label = entry["workout_title"]
            stype = entry["session_type"]
            n_sets = entry["n_working"]
            best_w = entry["best_weight"]
            best_r = entry["best_reps"]
            sets_detail = fmt_sets_detail(entry["working_sets"])

            target = get_target(ex_name, week_number, stype)
            t_str = fmt_target(target, reps_note)

            actual_w_str = fmt_weight(best_w)
            actual_str = f"{n_sets}×{best_r} @ {actual_w_str}"

            if target:
                t_s = target["sets"]
                t_r = target["reps"]
                t_w = target["weight"]
                emoji, detail = assess(n_sets, best_w, best_r, t_s, t_w,
                                       t_r if isinstance(t_r, int) else 0)
            else:
                emoji, detail = "📝", "No target — logged"

            lines.append(
                f"| {date} | {session_label[:30]} | {t_str} | {actual_str} "
                f"| {emoji} {detail} | {sets_detail} |"
            )

    return "\n".join(lines)


# ── Report assembly ─────────────────────────────────────────────

def generate_report(workouts, week_number):
    report_date = datetime.now(timezone.utc).strftime("%d %B %Y")
    week_start = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    week_end = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    entries = extract_exercises(workouts)
    grouped = group_by_exercise(entries)

    sessions = len(workouts)
    total_sets = sum(e["n_working"] for e in entries)

    # Session list
    workout_lines = []
    for w in sorted(workouts, key=lambda x: x.get("start_time", "")):
        date = w.get("start_time", "")[:10]
        title = w.get("title", "Unknown")
        dur = round((w.get("duration") or 0) / 60)
        ex_count = len(w.get("exercises", []))
        workout_lines.append(f"- **{date}** — {title} ({dur} min, {ex_count} exercises)")

    # Priority snapshots
    def snap(ex, wk):
        e_list = grouped.get(ex, [])
        if not e_list:
            return "❌ Not logged", "❌"
        best = max(e_list, key=lambda x: x["best_weight"])
        t = get_target(ex, wk, best["session_type"])
        w_str = fmt_weight(best["best_weight"])
        actual = f"{best['n_working']}×{best['best_reps']} @ {w_str}"
        if t:
            emoji, _ = assess(
                best["n_working"], best["best_weight"], best["best_reps"],
                t["sets"], t["weight"], t["reps"] if isinstance(t["reps"], int) else 0
            )
        else:
            emoji = "📝"
        return actual, emoji

    # Get targets for snapshot table
    def target_str(ex, wk, stype="heavy"):
        t = get_target(ex, wk, stype) or get_target(ex, wk, "both")
        return fmt_target(t) if t else "—"

    bench_actual, bench_emoji = snap("Bench Press (Barbell)", week_number)
    pu_actual, pu_emoji = snap("Pull Up (Weighted)", week_number)
    lp_actual, lp_emoji = snap("Leg Press (Machine)", week_number)
    lc_actual, lc_emoji = snap("Seated Leg Curl (Machine)", week_number)

    vol_status = ("✅ On target" if 99 <= total_sets <= 135
                  else ("⚠️ High — watch recovery" if total_sets > 135
                        else "❌ Below target"))

    # Section definitions
    push_chest     = ["Bench Press (Barbell)", "Iso-Lateral Chest Press (Machine)", "Chest Fly (Machine)"]
    push_shoulders = ["Shoulder Press (Machine Plates)", "Lateral Raise (Machine)", "Single Arm Lateral Raise (Cable)"]
    push_triceps   = ["Triceps Dip", "Triceps Pushdown", "Single Arm Triceps Pushdown (Cable)"]
    pull_back      = ["Pull Up (Weighted)", "Pull Up", "Chin Up", "Iso-Lateral Row (Machine)", "Seated Cable Row - Bar Grip", "Lat Pulldown (Cable)"]
    pull_rear      = ["Rear Delt Reverse Fly (Machine)", "Face Pull (Cable)"]
    pull_biceps    = ["Bicep Curl (Dumbbell)", "Hammer Curl (Dumbbell)", "Reverse Curl (Barbell)", "T Bar Shrugs"]
    legs_quads     = ["Leg Extension (Machine)", "Leg Press (Machine)", "Bulgarian Split Squat"]
    legs_hams      = ["Romanian Deadlift (Cable)", "Cable Pull-Through", "Seated Leg Curl (Machine)"]
    legs_calves    = ["Standing Calf Raise (Machine)"]
    core_ex        = ["Plank", "Dead Hang", "Scapular Pull Ups"]

    all_planned = set(
        push_chest + push_shoulders + push_triceps +
        pull_back + pull_rear + pull_biceps +
        legs_quads + legs_hams + legs_calves + core_ex
    )
    extra = [ex for ex in grouped if ex not in all_planned]
    extra_section = ""
    if extra:
        extra_lines = ["\n### Extra Exercises (not in programme)\n"]
        for ex in extra:
            e = grouped[ex][0]
            extra_lines.append(
                f"- **{ex}**: {e['n_working']} working sets, "
                f"best {fmt_weight(e['best_weight'])} × {e['best_reps']} reps"
            )
        extra_section = "\n".join(extra_lines)

    report = f"""# Weekly Training Report — Week {week_number} of 8
**Generated: {report_date}** | Period: {week_start} → {week_end}
*Hevy data: automatic ✅ | Nutrition + sleep: fill in at check-in*

---

## ⚡ Priority Lifts — At a Glance

| Lift | W{week_number} Target | Actual | Status |
|---|---|---|---|
| Bench Press (Heavy) ⭐ | {target_str("Bench Press (Barbell)", week_number, "heavy")} | {bench_actual} | {bench_emoji} |
| Weighted Pull Up (Heavy) ⭐ | {target_str("Pull Up (Weighted)", week_number, "heavy")} | {pu_actual} | {pu_emoji} |
| Leg Press ⭐ | {target_str("Leg Press (Machine)", week_number, "both")} | {lp_actual} | {lp_emoji} |
| Seated Leg Curl ⭐ | {target_str("Seated Leg Curl (Machine)", week_number, "both")} | {lc_actual} | {lc_emoji} |

**Sessions completed:** {sessions}/5 | **Total working sets:** {total_sets} | {vol_status}

---

## 📋 Sessions This Week

{chr(10).join(workout_lines) if workout_lines else "- No sessions recorded this week"}

---

## 🏋️ Full Exercise Breakdown — Every Exercise vs Every Target

> ⭐ Priority | ✅ Hit | ⚠️ Close/partial | ❌ Missed | 🚀 Ahead | 📝 No target set

{exercise_section(push_chest,     "PUSH — Chest",               grouped, week_number)}

{exercise_section(push_shoulders, "PUSH — Shoulders",           grouped, week_number)}

{exercise_section(push_triceps,   "PUSH — Triceps",             grouped, week_number)}

{exercise_section(pull_back,      "PULL — Back",                grouped, week_number)}

{exercise_section(pull_rear,      "PULL — Rear Delt & Face Pull", grouped, week_number)}

{exercise_section(pull_biceps,    "PULL — Biceps & Traps",      grouped, week_number)}

{exercise_section(legs_quads,     "LEGS — Quads",               grouped, week_number)}

{exercise_section(legs_hams,      "LEGS — Hamstrings & Glutes", grouped, week_number)}

{exercise_section(legs_calves,    "LEGS — Calves",              grouped, week_number)}

{exercise_section(core_ex,        "CORE",                       grouped, week_number)}

{extra_section}

---

## 🍗 Nutrition
*Fill in at check-in — MFP weekly summary*

- **Avg daily calories:** [ADD] kcal  *(target: ~2,900 training / ~2,450 rest)*
- **Avg daily protein:** [ADD]g  *(target: 240g training / 210g rest)*
- **Days logged in MFP:** [ADD]/7
- **Lowest protein day:** [ADD]g on [ADD DAY]
- **Crash days under 1,500 kcal?** [YES/NO]
- **Both shakes every day?** [YES/NO]

---

## 😴 Sleep & Recovery
*Fill in at check-in — Samsung Health weekly summary screenshot*

- **Avg sleep score:** [ADD] / 100  *(target: 78+)*
- **Avg physical recovery:** [ADD]%  *(target: 80%+)*
- **Avg HRV:** [ADD] ms
- **Avg resting HR:** [ADD] bpm
- **Avg sleep duration:** [ADD] hours
- **Worst night:** [ADD] — score [ADD]
- **Sunday bedtime:** [ADD]
- **Snoring flagged?** [YES/NO]

---

## ⚖️ Body Composition
*Fill in at check-in — Samsung Health daily weigh-in + body scan*

- **7-day avg weight:** [ADD] kg  *(baseline: 86.0 kg)*
- **Body fat %:** [ADD]%  *(baseline: 18.4%)*
- **Skeletal muscle:** [ADD] kg  *(baseline: 38.4 kg — target: UP)*
- **Direction vs last week:** [UP / DOWN / FLAT]

---
*Auto-generated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} | Source: Hevy API*
"""
    return report


# ── Sync state ──────────────────────────────────────────────────

def load_last_sync():
    if LAST_SYNC_FILE.exists():
        return datetime.fromisoformat(
            json.loads(LAST_SYNC_FILE.read_text()).get("last_sync")
        )
    return datetime.now(timezone.utc) - timedelta(days=7)


def save_last_sync():
    LAST_SYNC_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_SYNC_FILE.write_text(
        json.dumps({"last_sync": datetime.now(timezone.utc).isoformat()}, indent=2)
    )


# ── File I/O ────────────────────────────────────────────────────

def save_report(report, week_number):
    now = datetime.now(timezone.utc)
    iso = now.isocalendar()
    fname = f"{iso[0]}_W{iso[1]:02d}_week{week_number}_of_programme.md"
    path = REPO_ROOT / "weekly_reports" / fname
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    print(f"Report saved: {fname}")
    return path


def save_raw(workouts, label):
    now = datetime.now(timezone.utc)
    iso = now.isocalendar()
    fname = f"{iso[0]}_W{iso[1]:02d}_{label}_raw.json"
    path = REPO_ROOT / "data" / fname
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(workouts, indent=2, default=str), encoding="utf-8")


# ── Main ────────────────────────────────────────────────────────

def run_weekly():
    print("Mode: WEEKLY REPORT")
    week = get_current_week()
    print(f"Programme week: {week}/8")
    since = datetime.now(timezone.utc) - timedelta(days=7)
    workouts = fetch_workouts_since(since)
    print(f"Workouts: {len(workouts)}")
    save_raw(workouts, "weekly")
    report = generate_report(workouts, week)
    save_report(report, week)
    save_last_sync()
    print("Done")


def run_sync():
    print("Mode: INCREMENTAL SYNC")
    last = load_last_sync()
    print(f"Last sync: {last.strftime('%Y-%m-%d %H:%M UTC')}")
    new = fetch_workouts_since(last)
    print(f"New workouts: {len(new)}")

    if not new:
        print("No new data — nothing to update")
        # Signal to Actions that no commit is needed
        env_file = os.environ.get("GITHUB_OUTPUT", "")
        if env_file:
            with open(env_file, "a") as f:
                f.write("new_data=false\n")
        return

    print("New workout detected — regenerating report")
    week = get_current_week()
    since = datetime.now(timezone.utc) - timedelta(days=7)
    all_workouts = fetch_workouts_since(since)
    save_raw(all_workouts, "sync")
    report = generate_report(all_workouts, week)
    save_report(report, week)
    save_last_sync()

    env_file = os.environ.get("GITHUB_OUTPUT", "")
    if env_file:
        with open(env_file, "a") as f:
            f.write("new_data=true\n")
    print("Done")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["weekly", "sync"], default="weekly")
    args = parser.parse_args()
    if args.mode == "sync":
        run_sync()
    else:
        run_weekly()


if __name__ == "__main__":
    main()
