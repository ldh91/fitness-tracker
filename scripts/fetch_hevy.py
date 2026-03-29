"""
fetch_hevy.py
-------------
Pulls the last 7 days of workout data from the Hevy API and generates
a structured weekly report markdown file.

Run manually:  python scripts/fetch_hevy.py
Run by GitHub Actions: automatically every Sunday 20:00 UTC
"""

import os
import json
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────
HEVY_API_KEY = os.environ.get("HEVY_API_KEY")
HEVY_BASE_URL = "https://api.hevyapp.com/v1"
REPO_ROOT = Path(__file__).parent.parent

# ── Targets from the 8-week bible ──────────────────────────────
# Week number → (bench_heavy_kg, bench_heavy_sets, bench_heavy_reps,
#                bench_volume_kg, bench_volume_sets, bench_volume_reps,
#                pull_up_kg, pull_up_sets, pull_up_reps)
WEEKLY_TARGETS = {
    1:  (65.0,   4, 5,  55.0,  3, 10, 5.0, 3, 6),
    2:  (65.0,   4, 5,  55.0,  3, 10, 5.0, 3, 7),
    3:  (67.5,   4, 5,  57.5,  3, 10, 5.0, 3, 8),
    4:  (67.5,   4, 5,  57.5,  3, 10, 7.5, 3, 5),
    5:  (70.0,   4, 5,  60.0,  3, 10, 7.5, 3, 6),
    6:  (70.0,   4, 5,  60.0,  3, 10, 7.5, 3, 7),
    7:  (72.5,   4, 5,  62.5,  3, 10, 7.5, 3, 8),
    8:  (72.5,   4, 5,  62.5,  3, 10, 10.0, 3, 5),
}

# Programme start date
PROGRAMME_START = datetime(2026, 3, 28, tzinfo=timezone.utc)

# Nutrition targets
PROTEIN_TARGET_TRAINING = 240
PROTEIN_TARGET_REST = 210
CALORIE_TARGET_TRAINING = 2900
CALORIE_TARGET_REST = 2450
SLEEP_SCORE_TARGET = 78
RECOVERY_TARGET = 80


def get_current_week():
    """Return which week of the programme we're in (1-8)."""
    now = datetime.now(timezone.utc)
    delta = (now - PROGRAMME_START).days
    week = (delta // 7) + 1
    return max(1, min(8, week))


def get_week_date_range():
    """Return ISO start and end datetimes for the past 7 days."""
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=7)
    return week_start.isoformat(), now.isoformat()


def hevy_get(endpoint, params=None):
    """Make an authenticated GET request to the Hevy API."""
    if not HEVY_API_KEY:
        raise ValueError("HEVY_API_KEY environment variable not set.")
    headers = {
        "api-key": HEVY_API_KEY,
        "accept": "application/json",
    }
    url = f"{HEVY_BASE_URL}/{endpoint}"
    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_workouts_this_week():
    """Fetch all workouts from the past 7 days."""
    print("Fetching workouts from Hevy API...")
    all_workouts = []
    page = 1
    week_start, week_end = get_week_date_range()

    while True:
        data = hevy_get("workouts", params={"page": page, "pageSize": 10})
        workouts = data.get("workouts", [])
        if not workouts:
            break

        for w in workouts:
            start = w.get("start_time", "")
            if start >= week_start:
                all_workouts.append(w)
            elif start < week_start:
                # Workouts are returned newest first — stop when we go past our window
                return all_workouts

        # Check if there are more pages
        total_pages = data.get("page_count", 1)
        if page >= total_pages:
            break
        page += 1

    return all_workouts


def extract_exercise_data(workouts):
    """
    Extract key exercise data from workouts.
    Returns a dict keyed by exercise title with best set info.
    """
    exercises = {}

    for workout in workouts:
        workout_title = workout.get("title", "Unknown")
        workout_date = workout.get("start_time", "")[:10]

        for exercise in workout.get("exercises", []):
            title = exercise.get("title", "Unknown")
            sets = exercise.get("sets", [])

            # Find best working set (highest weight)
            best_weight = 0
            best_reps = 0
            working_sets = []

            for s in sets:
                set_type = s.get("type", "normal")
                weight_kg = float(s.get("weight_kg") or 0)
                reps = int(s.get("reps") or 0)

                if set_type == "normal":
                    working_sets.append({"weight_kg": weight_kg, "reps": reps})
                    if weight_kg > best_weight:
                        best_weight = weight_kg
                        best_reps = reps

            if working_sets:
                key = title
                if key not in exercises:
                    exercises[key] = []
                exercises[key].append({
                    "date": workout_date,
                    "workout": workout_title,
                    "best_weight_kg": best_weight,
                    "best_reps": best_reps,
                    "working_sets": working_sets,
                    "total_working_sets": len(working_sets),
                })

    return exercises


def get_bench_press_data(exercises):
    """Extract bench press performance for heavy (Mon) and volume (Thu) sessions."""
    bench_data = {"heavy": None, "volume": None}

    bench_sets = exercises.get("Bench Press (Barbell)", [])
    for entry in bench_sets:
        workout = entry.get("workout", "").lower()
        # Heavy day = Push Heavy (Monday), Volume day = Push Volume (Thursday)
        if "heavy" in workout or "monday" in workout:
            bench_data["heavy"] = entry
        elif "volume" in workout or "thursday" in workout:
            bench_data["volume"] = entry
        else:
            # Assign by weight — heavier set is the heavy day
            if bench_data["heavy"] is None:
                bench_data["heavy"] = entry
            elif entry["best_weight_kg"] > bench_data["heavy"]["best_weight_kg"]:
                bench_data["volume"] = bench_data["heavy"]
                bench_data["heavy"] = entry

    return bench_data


def get_pull_up_weighted_data(exercises):
    """Extract weighted pull-up data."""
    pull_ups = exercises.get("Pull Up (Weighted)", [])
    if not pull_ups:
        return None
    # Return the best session (highest weight)
    return max(pull_ups, key=lambda x: x["best_weight_kg"])


def assess_vs_target(actual_weight, actual_sets, actual_reps,
                     target_weight, target_sets, target_reps):
    """Return a status string comparing actual vs target."""
    if actual_weight is None:
        return "❓ No data"
    if actual_weight > target_weight:
        return f"🚀 Ahead of target"
    elif actual_weight == target_weight:
        if actual_sets >= target_sets and actual_reps >= target_reps:
            return "✅ Hit target"
        elif actual_sets >= target_sets and actual_reps >= target_reps - 1:
            return "⚠️ Close — 1 rep short"
        else:
            return f"❌ Weight hit but sets/reps short ({actual_sets}×{actual_reps} vs {target_sets}×{target_reps})"
    else:
        return f"❌ Below target weight ({actual_weight}kg vs {target_weight}kg)"


def calculate_total_volume(workouts):
    """Calculate total working sets across all workouts this week."""
    total = 0
    for w in workouts:
        for ex in w.get("exercises", []):
            for s in ex.get("sets", []):
                if s.get("type") == "normal":
                    total += 1
    return total


def generate_report(workouts, week_number):
    """Generate the weekly markdown report."""
    week_start, week_end = get_week_date_range()
    report_date = datetime.now(timezone.utc).strftime("%d %B %Y")

    # Get targets for this week
    targets = WEEKLY_TARGETS.get(week_number, WEEKLY_TARGETS[8])
    (bh_kg, bh_sets, bh_reps,
     bv_kg, bv_sets, bv_reps,
     pu_kg, pu_sets, pu_reps) = targets

    # Extract exercise data
    exercises = extract_exercise_data(workouts)
    bench = get_bench_press_data(exercises)
    pull_up = get_pull_up_weighted_data(exercises)
    total_sets = calculate_total_volume(workouts)
    sessions_completed = len(workouts)

    # Bench press heavy assessment
    bh = bench.get("heavy")
    bh_status = assess_vs_target(
        bh["best_weight_kg"] if bh else None,
        bh["total_working_sets"] if bh else 0,
        bh["best_reps"] if bh else 0,
        bh_kg, bh_sets, bh_reps
    )

    # Bench press volume assessment
    bv = bench.get("volume")
    bv_status = assess_vs_target(
        bv["best_weight_kg"] if bv else None,
        bv["total_working_sets"] if bv else 0,
        bv["best_reps"] if bv else 0,
        bv_kg, bv_sets, bv_reps
    )

    # Pull up assessment
    pu_status = assess_vs_target(
        pull_up["best_weight_kg"] if pull_up else None,
        pull_up["total_working_sets"] if pull_up else 0,
        pull_up["best_reps"] if pull_up else 0,
        pu_kg, pu_sets, pu_reps
    )

    # Sessions assessment
    sessions_status = "✅ Hit target" if sessions_completed >= 5 else f"❌ {sessions_completed}/5 sessions"

    # Build all exercises section
    exercise_lines = []
    priority_exercises = [
        "Bench Press (Barbell)",
        "Pull Up (Weighted)",
        "Leg Press (Machine)",
        "Seated Leg Curl (Machine)",
        "Iso-Lateral Row (Machine)",
        "Lateral Raise (Machine)",
        "Cable RDL",
        "Bulgarian Split Squat",
    ]

    for ex_name in priority_exercises:
        entries = exercises.get(ex_name, [])
        if entries:
            best = max(entries, key=lambda x: x["best_weight_kg"])
            sets_str = f"{best['total_working_sets']}×{best['best_reps']}"
            weight_str = f"{best['best_weight_kg']}kg" if best["best_weight_kg"] > 0 else "BW"
            exercise_lines.append(f"| {ex_name} | {weight_str} | {sets_str} | {best['date']} |")

    # Other exercises logged
    other_lines = []
    for ex_name, entries in sorted(exercises.items()):
        if ex_name not in priority_exercises and entries:
            best = max(entries, key=lambda x: x["best_weight_kg"])
            sets_str = f"{best['total_working_sets']}×{best['best_reps']}"
            weight_str = f"{best['best_weight_kg']}kg" if best["best_weight_kg"] > 0 else "BW"
            other_lines.append(f"| {ex_name} | {weight_str} | {sets_str} |")

    # Format workout list
    workout_list = []
    for w in sorted(workouts, key=lambda x: x.get("start_time", "")):
        title = w.get("title", "Unknown")
        date = w.get("start_time", "")[:10]
        duration_s = w.get("duration", 0) or 0
        duration_min = round(duration_s / 60)
        ex_count = len(w.get("exercises", []))
        workout_list.append(f"- **{date}** — {title} ({duration_min} min, {ex_count} exercises)")

    # ── BUILD MARKDOWN ──────────────────────────────────────────
    report = f"""# Weekly Check-In Report
## Week {week_number} of 8 — {report_date}
*Data period: {week_start[:10]} to {week_end[:10]}*
*Auto-generated from Hevy API — nutrition and sleep to be added manually or via MFP/Samsung automation*

---

## ⚡ Quick Snapshot

| Metric | Target | Actual | Status |
|---|---|---|---|
| Training sessions | 5 | {sessions_completed} | {sessions_status} |
| Total working sets | 99–122 | {total_sets} | {"✅ On target" if 99 <= total_sets <= 135 else "⚠️ Check volume" if total_sets > 135 else "❌ Below target"} |
| Bench Press — Heavy | {bh_kg}kg × {bh_sets}×{bh_reps} | {f"{bh['best_weight_kg']}kg × {bh['total_working_sets']}×{bh['best_reps']}" if bh else "No data"} | {bh_status} |
| Bench Press — Volume | {bv_kg}kg × {bv_sets}×{bv_reps} | {f"{bv['best_weight_kg']}kg × {bv['total_working_sets']}×{bv['best_reps']}" if bv else "No data"} | {bv_status} |
| Weighted Pull Up | {pu_kg}kg × {pu_sets}×{pu_reps} | {f"{pull_up['best_weight_kg']}kg × {pull_up['total_working_sets']}×{pull_up['best_reps']}" if pull_up else "No data"} | {pu_status} |
| Daily protein (training) | 240g | ⏳ Add from MFP | — |
| Daily calories (training) | ~2,900 kcal | ⏳ Add from MFP | — |
| MFP logged days | 7 | ⏳ Add manually | — |
| Sleep score avg | 78+ | ⏳ Add from Samsung | — |
| Physical recovery avg | 80%+ | ⏳ Add from Samsung | — |
| Body weight (7-day avg) | On track | ⏳ Add from Samsung | — |
| Skeletal muscle | Trending up | ⏳ Add from Samsung | — |

---

## 🏋️ Training Detail

### Sessions This Week
{chr(10).join(workout_list) if workout_list else "- No sessions recorded this week"}

### Priority Lifts
| Exercise | Best Weight | Sets×Reps | Date |
|---|---|---|---|
{chr(10).join(exercise_lines) if exercise_lines else "| No data | — | — | — |"}

### All Other Exercises
| Exercise | Best Weight | Sets×Reps |
|---|---|---|
{chr(10).join(other_lines) if other_lines else "| No data | — | — |"}

---

## 🍗 Nutrition
*To be populated from MFP — fill in manually at check-in or add MFP automation*

- **Average daily calories:** [ADD]
- **Average daily protein:** [ADD]g
- **Days logged in MFP:** [ADD]/7
- **Lowest protein day:** [ADD] — [ADD]g on [ADD DAY]
- **Any crash days (under 1,500 kcal)?** [YES/NO]
- **Both shakes hit every day?** [YES/NO]

---

## 😴 Sleep & Recovery
*To be populated from Samsung Health — screenshot weekly summary and add below*

- **Average sleep score:** [ADD] / 100
- **Average physical recovery:** [ADD]%
- **Average HRV:** [ADD] ms
- **Average resting HR:** [ADD] bpm
- **Average sleep duration:** [ADD] hours
- **Worst night (score + reason if known):** [ADD]
- **Sunday bedtime this week:** [ADD]
- **Snoring flagged?** [YES/NO]

---

## ⚖️ Body Composition
*To be populated from Samsung Health daily weigh-in data*

- **7-day average weight:** [ADD] kg
- **Body fat % (latest scan):** [ADD]%
- **Skeletal muscle (latest scan):** [ADD] kg
- **Direction vs last week:** [UP/DOWN/FLAT]

---

## 📊 Week {week_number} Bible Targets Reference

| Exercise | This Week Target | Next Week Target |
|---|---|---|
| Bench Press — Heavy | {bh_kg}kg × {bh_sets}×{bh_reps} | {WEEKLY_TARGETS.get(week_number+1, targets)[0]}kg × {WEEKLY_TARGETS.get(week_number+1, targets)[1]}×{WEEKLY_TARGETS.get(week_number+1, targets)[2]} |
| Bench Press — Volume | {bv_kg}kg × {bv_sets}×{bv_reps} | {WEEKLY_TARGETS.get(week_number+1, targets)[3]}kg × {WEEKLY_TARGETS.get(week_number+1, targets)[4]}×{WEEKLY_TARGETS.get(week_number+1, targets)[5]} |
| Weighted Pull Up | {pu_kg}kg × {pu_sets}×{pu_reps} | {WEEKLY_TARGETS.get(week_number+1, targets)[6]}kg × {WEEKLY_TARGETS.get(week_number+1, targets)[7]}×{WEEKLY_TARGETS.get(week_number+1, targets)[8]} |

---
*Report generated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} | Source: Hevy API (automatic) + manual inputs*
"""

    return report


def save_report(report, week_number):
    """Save the report to the weekly_reports directory."""
    now = datetime.now(timezone.utc)
    iso_week = now.isocalendar()
    filename = f"{iso_week[0]}_W{iso_week[1]:02d}_week{week_number}_of_programme.md"
    filepath = REPO_ROOT / "weekly_reports" / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(report, encoding="utf-8")
    print(f"Report saved: {filepath}")
    return filepath


def save_raw_data(workouts, week_number):
    """Save raw workout JSON for debugging."""
    now = datetime.now(timezone.utc)
    iso_week = now.isocalendar()
    filename = f"{iso_week[0]}_W{iso_week[1]:02d}_hevy_raw.json"
    filepath = REPO_ROOT / "data" / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(
        json.dumps(workouts, indent=2, default=str),
        encoding="utf-8"
    )
    print(f"Raw data saved: {filepath}")


def main():
    print(f"{'='*50}")
    print(f"Fitness Tracker — Weekly Report Generator")
    print(f"{'='*50}")

    week_number = get_current_week()
    print(f"Programme week: {week_number} of 8")

    try:
        workouts = fetch_workouts_this_week()
        print(f"Found {len(workouts)} workouts this week")

        save_raw_data(workouts, week_number)

        report = generate_report(workouts, week_number)
        report_path = save_report(report, week_number)

        print(f"\n✅ Report generated successfully")
        print(f"File: {report_path.name}")
        print(f"\nNext steps:")
        print(f"  1. Open the report and fill in the [ADD] fields from MFP and Samsung Health")
        print(f"  2. Paste the report URL to Claude for your PT check-in")

    except ValueError as e:
        print(f"❌ Config error: {e}")
        print("Make sure HEVY_API_KEY is set as an environment variable")
        raise
    except requests.HTTPError as e:
        print(f"❌ Hevy API error: {e}")
        print("Check your API key at hevy.com/settings?developer")
        raise
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        raise


if __name__ == "__main__":
    main()
