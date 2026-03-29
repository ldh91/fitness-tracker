# Setup Guide — Windows

Complete step-by-step instructions to get the automated weekly report running.
Estimated time: 20–30 minutes.

---

## What This Does

Every Sunday at 20:00 UTC, GitHub automatically:
1. Pulls your last 7 days of Hevy workout data via the official API
2. Compares your key lifts against your 8-week programme targets
3. Generates a markdown report file and commits it to this repo
4. You paste the file URL into your Claude PT project chat for your weekly check-in

---

## Step 1 — Get Your Hevy API Key

1. Open a browser and go to: **https://hevy.com/settings?developer**
2. Log in to your Hevy account
3. Generate an API key — copy it and keep it safe (treat it like a password)

---

## Step 2 — Create Your GitHub Repository

1. Go to **https://github.com/new**
2. Repository name: `fitness-tracker` (or anything you like)
3. Set to **Private** (your health data — keep it private)
4. Do NOT initialise with README (you'll push these files yourself)
5. Click **Create repository**
6. Note the repo URL — it will look like: `https://github.com/YOUR_USERNAME/fitness-tracker`

---

## Step 3 — Add Your Hevy API Key as a GitHub Secret

This keeps your API key secure — it never appears in the code.

1. Go to your new repo on GitHub
2. Click **Settings** (top menu)
3. Left sidebar → **Secrets and variables** → **Actions**
4. Click **New repository secret**
5. Name: `HEVY_API_KEY`
6. Secret: paste your Hevy API key from Step 1
7. Click **Add secret**

---

## Step 4 — Install Git on Windows (if not already installed)

1. Go to **https://git-scm.com/download/win**
2. Download and run the installer
3. Accept all defaults
4. Open **Git Bash** (search for it in Start menu) — use this for all commands below

---

## Step 5 — Install Python on Windows (if not already installed)

1. Go to **https://www.python.org/downloads/**
2. Download Python 3.11 or newer
3. Run the installer — **IMPORTANT: tick "Add Python to PATH"** before clicking Install
4. Verify: open Git Bash and type `python --version` — should show 3.11+

---

## Step 6 — Set Up the Repository Locally

Open **Git Bash** and run these commands one at a time:

```bash
# Navigate to where you want the folder (e.g. your Documents)
cd ~/Documents

# Clone your empty repo
git clone https://github.com/YOUR_USERNAME/fitness-tracker.git
cd fitness-tracker
```

Now copy all the files from this zip/folder into the `fitness-tracker` directory.
Your folder structure should look like this:

```
fitness-tracker/
├── .github/
│   └── workflows/
│       └── weekly_report.yml
├── scripts/
│   └── fetch_hevy.py
├── weekly_reports/
│   └── README.md
├── data/
│   └── README.md
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Step 7 — Test the Script Locally First

In Git Bash:

```bash
# Install the Python dependency
pip install requests

# Set your API key temporarily for this test
export HEVY_API_KEY="your-api-key-here"

# Run the script
python scripts/fetch_hevy.py
```

You should see output like:
```
==================================================
Fitness Tracker — Weekly Report Generator
==================================================
Programme week: 1 of 8
Fetching workouts from Hevy API...
Found 5 workouts this week
Raw data saved: data/2026_W14_hevy_raw.json
Report saved: weekly_reports/2026_W14_week1_of_programme.md

✅ Report generated successfully
```

If you see an error about the API key, double-check it at hevy.com/settings?developer.

---

## Step 8 — Push Everything to GitHub

```bash
# Add all files
git add .

# Commit
git commit -m "Initial setup — fitness tracker"

# Push to GitHub
git push origin main
```

If prompted for credentials, use your GitHub username and a Personal Access Token
(not your password). Create one at: GitHub → Settings → Developer settings →
Personal access tokens → Tokens (classic) → Generate new token.
Tick the `repo` scope. Use this token as your password when prompted.

---

## Step 9 — Verify GitHub Actions is Working

1. Go to your repo on GitHub
2. Click the **Actions** tab
3. You should see **Weekly Fitness Report** in the left sidebar
4. To test it immediately without waiting for Sunday: click the workflow name →
   **Run workflow** → **Run workflow** (green button)
5. Watch it run — it should complete in under 60 seconds
6. Check the **weekly_reports/** folder — a new file should appear

---

## Step 10 — Get the Raw File URL for Claude

After the report is generated:

1. Go to your repo → `weekly_reports/` folder
2. Click the latest `.md` file
3. Click the **Raw** button (top right of the file view)
4. Copy the URL — it will look like:
   `https://raw.githubusercontent.com/YOUR_USERNAME/fitness-tracker/main/weekly_reports/2026_W14_week1_of_programme.md`

**This is the URL you give to Claude at your weekly check-in.**

Paste it into the project instructions (replacing `[REPO URL TO BE ADDED]` in the personal profile document) so the PT knows where to look automatically.

---

## Step 11 — Update Your Personal Profile in Claude

1. Open the `personal_profile.md` in your Claude project
2. Find the line: `[REPO URL TO BE ADDED]`
3. Replace with the base URL of your repo:
   `https://raw.githubusercontent.com/YOUR_USERNAME/fitness-tracker/main/weekly_reports/`
4. The PT will then know to look for files matching the naming pattern

---

## Weekly Routine After Setup

Every Sunday evening:

1. **Nothing required for Hevy** — runs automatically at 20:00 UTC
2. **Samsung Health:** Take a screenshot of your weekly summary (30 seconds)
3. **MFP:** Check if weekly summary email arrived (once automation is set up, this is also automatic)
4. **Claude check-in:** Open your PT project, say "Week X check-in" and paste the GitHub report URL if the PT asks for it — or just let it fetch automatically

---

## Troubleshooting

**Script fails with "HEVY_API_KEY not set"**
→ Make sure you ran `export HEVY_API_KEY="your-key"` in the same terminal window

**No workouts found**
→ Check the date range in the script — workouts must be in the last 7 days

**GitHub Actions fails**
→ Go to Actions tab → click the failed run → expand the failing step to see the error
→ Most common cause: HEVY_API_KEY secret not added correctly (Step 3)

**Push rejected**
→ You may need to set up a Personal Access Token (see Step 8)

---

## Updating the Programme Targets (After Week 8)

When you start a new programme phase, update the `WEEKLY_TARGETS` dictionary
in `scripts/fetch_hevy.py` with the new target weights and reps.
Also update `PROGRAMME_START` to the new start date.
