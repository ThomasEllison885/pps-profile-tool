# The Pure Way Profile
**Pure Property Solutions · Team Behavioral Assessment Tool**

A 44-question scenario-based behavioral and motivational assessment for the PPS team. Built on the DISC framework with a motivators/values layer. Results are stored in PostgreSQL for year-over-year tracking.

---

## What It Does

- **44 scenario-based questions** across two sections: Behavioral Style (DISC) and Motivators & Values
- **Full results report** including DISC scores, motivator scores, strengths, blind spots, energizers, drainers, communication style, conflict style, and a TV/movie character match
- **PostgreSQL storage** — results persist across server restarts, searchable by name and year
- **Admin dashboard** — Thomas's view of all 13 team members' results side by side

---

## Passwords

| Access | Password |
|---|---|
| Team (take test + view history) | `PureProfile2026` |
| Admin dashboard | `Luther1985` |

---

## Deployment on Render

### Step 1 — Create the GitHub Repo

```bash
cd pps-profile-tool
git init
git add .
git commit -m "Initial commit — Pure Way Profile"
gh repo create ThomasEllison885/pps-profile-tool --public --push --source=.
```

Or create the repo on github.com and push manually.

### Step 2 — Create Render PostgreSQL Database

1. Go to [render.com](https://render.com) → **New** → **PostgreSQL**
2. Name: `pps-profile-db`
3. Plan: **Free**
4. Click **Create Database**
5. Copy the **Internal Database URL** — you'll need it in Step 3

### Step 3 — Create Render Web Service

1. **New** → **Web Service**
2. Connect your GitHub repo `pps-profile-tool`
3. Settings:
   - **Name:** `pps-profile-tool`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --worker-class eventlet --workers 1 --timeout 120`
   - **Plan:** Free

4. Add **Environment Variables:**

| Key | Value |
|---|---|
| `SECRET_KEY` | any random string (e.g. `pps-profile-secret-2026`) |
| `APP_PASSWORD` | `PureProfile2026` |
| `ADMIN_PASSWORD` | `Luther1985` |
| `DATABASE_URL` | paste the Internal Database URL from Step 2 |

5. Click **Create Web Service**

### Step 4 — Done

Your app will be live at `https://pps-profile-tool.onrender.com`

---

## Custom Domain (Optional)

To use `profile.purepropertysolutions.com`:

1. In Render → your web service → **Settings** → **Custom Domains** → Add `profile.purepropertysolutions.com`
2. In your DNS provider (GoDaddy / Cloudflare / etc.), add a **CNAME record**:
   - Name: `profile`
   - Value: `pps-profile-tool.onrender.com`
3. Wait 5–30 minutes for DNS to propagate

---

## Routes

| URL | Access | Description |
|---|---|---|
| `/` | Public | Login page |
| `/profile` | Team password | Home / landing |
| `/take-test` | Team password | 44-question assessment |
| `/submit` | Team password | POST endpoint (form submission) |
| `/results` | Team password | Results page (after submission) |
| `/history` | Team password | Search past results by name |
| `/history/<id>` | Team password | View a specific past result |
| `/admin` | Admin password | Team dashboard, all results |
| `/logout` | — | Clear session |

---

## Retaking the Assessment

Team members can retake the assessment each year. Each submission is stored separately with the date, so year-over-year comparisons are preserved. The history page lets anyone look up their own results by name across all years.

---

## File Structure

```
pps-profile-tool/
├── app.py              # Flask app, scoring engine, routes
├── requirements.txt
├── Procfile
├── README.md
└── templates/
    ├── login.html      # Password entry
    ├── index.html      # Landing page
    ├── test.html       # 44-question assessment
    ├── results.html    # Full results report
    ├── history.html    # Past results search
    └── admin.html      # Thomas's admin dashboard
```
