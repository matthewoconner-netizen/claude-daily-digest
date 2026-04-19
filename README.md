# Legal SDR Morning Digest

Sends Matthew O'Conner's Legal SDR morning digest to matthew.oconner@levitateapp.com
every weekday at 7:30am EST via GitHub Actions.

## Repo structure

```
digest/
  daily_digest.py          # main script
  requirements.txt
.github/
  workflows/
    morning_digest.yml     # GitHub Actions schedule
```

## Setup (one-time)

### 1. Create a GitHub repo
Create a new private repo (e.g. `levitate-morning-digest`) and push these files.

### 2. Add GitHub Secrets
Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add each of these:

| Secret name         | Value                                      |
|---------------------|--------------------------------------------|
| `REDSHIFT_HOST`     | Your Redshift cluster endpoint             |
| `REDSHIFT_PORT`     | `5439`                                     |
| `REDSHIFT_DB`       | Your Redshift database name                |
| `REDSHIFT_USER`     | Your Redshift username                     |
| `REDSHIFT_PASSWORD` | Your Redshift password                     |
| `GMAIL_ADDRESS`     | `claude.dailysend@gmail.com`               |
| `GMAIL_APP_PASSWORD`| `uknd fzyy iykw zkyb` (no spaces: `ukndFzyyIykwZkyb`) |
| `RECIPIENT_EMAIL`   | `matthew.oconner@levitateapp.com`          |

### 3. Test it manually
Go to **Actions** → **Legal SDR Morning Digest** → **Run workflow**
This triggers it immediately so you can verify the email arrives.

### 4. Schedule
The workflow runs automatically Mon–Fri at 11:30 UTC (7:30am EDT).
In winter (EST, UTC-5) you may want to change the cron to `30 12 * * 1-5`.

## Adding Section 3 (WoW Hotspots)
When ready, the week-over-week hotspots for the full Legal SDR team
will be added as a third section. The placeholder is already in the email.
