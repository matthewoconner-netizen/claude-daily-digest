"""
Matthew O'Conner — Legal SDR Morning Digest
Sends a daily email at 7:30am EST Mon–Fri via GitHub Actions.

Secrets required (set in GitHub repo → Settings → Secrets → Actions):
  REDSHIFT_HOST       Redshift cluster endpoint
  REDSHIFT_PORT       Usually 5439
  REDSHIFT_DB         Database name
  REDSHIFT_USER       Redshift username
  REDSHIFT_PASSWORD   Redshift password
  GMAIL_ADDRESS       claude.dailysend@gmail.com
  GMAIL_APP_PASSWORD  App password (16 chars, no spaces)
  RECIPIENT_EMAIL     matthew.oconner@levitateapp.com
"""

import os
import smtplib
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import psycopg2

# ── Config ────────────────────────────────────────────────────────────────────

DB = dict(
    host=os.environ["REDSHIFT_HOST"],
    port=int(os.environ.get("REDSHIFT_PORT", 5439)),
    dbname=os.environ["REDSHIFT_DB"],
    user=os.environ["REDSHIFT_USER"],
    password=os.environ["REDSHIFT_PASSWORD"],
)

GMAIL_ADDRESS    = os.environ["GMAIL_ADDRESS"]
GMAIL_PASSWORD   = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENT        = os.environ["RECIPIENT_EMAIL"]
MANAGER          = "Matthew O'Conner"
QUOTA_TEAM       = "Legal"

# ── Helpers ───────────────────────────────────────────────────────────────────

def query(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def pct(val):
    if val is None:
        return "—"
    return f"{val:.1f}%"


def num(val, decimals=1):
    if val is None:
        return "—"
    if decimals == 0:
        return f"{int(val):,}"
    return f"{val:,.{decimals}f}"


def arrow(yday, norm, higher_is_better=True):
    if yday is None or norm is None or norm == 0:
        return "—"
    diff_pct = ((yday - norm) / abs(norm)) * 100
    if abs(diff_pct) <= 5:
        return "—"
    if higher_is_better:
        return "▲" if diff_pct > 0 else "▼"
    return "▼" if diff_pct > 0 else "▲"


def pill(val, target, good_threshold=None):
    """Return ✓ if at/above target, ⚠ if below."""
    if val is None:
        return "—"
    threshold = good_threshold if good_threshold is not None else target
    return "✓" if val >= threshold else "⚠"

# ── SQL ───────────────────────────────────────────────────────────────────────

MTD_5STEPS_SQL = """
SELECT
    user_full_name,
    SUM(CASE WHEN is_prospecting_dial THEN 1 ELSE 0 END)                                          AS dials,
    SUM(CASE WHEN is_connect          THEN 1 ELSE 0 END)                                          AS connects,
    SUM(CASE WHEN is_demo             THEN 1 ELSE 0 END)                                          AS demos,
    ROUND(SUM(CASE WHEN is_connect THEN 1 ELSE 0 END)::float
        / NULLIF(SUM(CASE WHEN is_prospecting_dial THEN 1 ELSE 0 END), 0) * 100, 1)              AS connect_pct,
    ROUND((SUM(CASE WHEN is_connect THEN 1 ELSE 0 END)
         - SUM(CASE WHEN is_hook_rejected THEN 1 ELSE 0 END))::float
        / NULLIF(SUM(CASE WHEN is_connect THEN 1 ELSE 0 END), 0) * 100, 1)                       AS hook_pct,
    ROUND(SUM(CASE WHEN is_qp THEN 1 ELSE 0 END)::float
        / NULLIF(SUM(CASE WHEN is_connect THEN 1 ELSE 0 END)
                - SUM(CASE WHEN is_hook_rejected THEN 1 ELSE 0 END), 0) * 100, 1)                AS pitch_pct,
    ROUND(SUM(CASE WHEN is_qq THEN 1 ELSE 0 END)::float
        / NULLIF(SUM(CASE WHEN is_connect THEN 1 ELSE 0 END)
                - SUM(CASE WHEN is_hook_rejected THEN 1 ELSE 0 END), 0) * 100, 1)                AS qq_pct,
    ROUND(SUM(CASE WHEN is_demo THEN 1 ELSE 0 END)::float
        / NULLIF(SUM(CASE WHEN is_connect THEN 1 ELSE 0 END)
                - SUM(CASE WHEN is_hook_rejected THEN 1 ELSE 0 END), 0) * 100, 1)                AS demo_pct,
    ROUND(SUM(CASE WHEN is_prospecting_dial THEN 1 ELSE 0 END)::float
        / NULLIF(SUM(CASE WHEN is_demo THEN 1 ELSE 0 END), 0), 1)                                AS dials_per_demo,
    ROUND(SUM(CASE WHEN NOT is_cold_demo_dial AND is_prospecting_dial THEN 1 ELSE 0 END)::float
        / NULLIF(SUM(CASE WHEN is_demo THEN 1 ELSE 0 END), 0), 1)                                AS reg_dials_per_demo,
    ROUND(SUM(CASE WHEN is_cold_demo_dial AND is_demo THEN 1 ELSE 0 END)::float
        / NULLIF(SUM(CASE WHEN is_demo THEN 1 ELSE 0 END), 0) * 100, 1)                          AS cold_demo_pct
FROM sales_ops.tbl_fact_dial_interactions
WHERE interaction_date >= DATE_TRUNC('month', CURRENT_DATE)
  AND manager    = %s
  AND quota_team = %s
  AND role       = 'SDR'
  AND is_prospecting_dial = TRUE
GROUP BY 1
ORDER BY demos DESC, user_full_name
"""

YDAY_5STEPS_SQL = """
SELECT
    user_full_name,
    SUM(CASE WHEN is_prospecting_dial THEN 1 ELSE 0 END)                                          AS dials,
    SUM(CASE WHEN is_connect          THEN 1 ELSE 0 END)                                          AS connects,
    SUM(CASE WHEN is_demo             THEN 1 ELSE 0 END)                                          AS demos,
    ROUND(SUM(CASE WHEN is_connect THEN 1 ELSE 0 END)::float
        / NULLIF(SUM(CASE WHEN is_prospecting_dial THEN 1 ELSE 0 END), 0) * 100, 1)              AS connect_pct,
    ROUND((SUM(CASE WHEN is_connect THEN 1 ELSE 0 END)
         - SUM(CASE WHEN is_hook_rejected THEN 1 ELSE 0 END))::float
        / NULLIF(SUM(CASE WHEN is_connect THEN 1 ELSE 0 END), 0) * 100, 1)                       AS hook_pct,
    ROUND(SUM(CASE WHEN is_qp THEN 1 ELSE 0 END)::float
        / NULLIF(SUM(CASE WHEN is_connect THEN 1 ELSE 0 END)
                - SUM(CASE WHEN is_hook_rejected THEN 1 ELSE 0 END), 0) * 100, 1)                AS pitch_pct,
    ROUND(SUM(CASE WHEN is_qq THEN 1 ELSE 0 END)::float
        / NULLIF(SUM(CASE WHEN is_connect THEN 1 ELSE 0 END)
                - SUM(CASE WHEN is_hook_rejected THEN 1 ELSE 0 END), 0) * 100, 1)                AS qq_pct,
    ROUND(SUM(CASE WHEN is_demo THEN 1 ELSE 0 END)::float
        / NULLIF(SUM(CASE WHEN is_connect THEN 1 ELSE 0 END)
                - SUM(CASE WHEN is_hook_rejected THEN 1 ELSE 0 END), 0) * 100, 1)                AS demo_pct,
    ROUND(SUM(CASE WHEN is_prospecting_dial THEN 1 ELSE 0 END)::float
        / NULLIF(SUM(CASE WHEN is_demo THEN 1 ELSE 0 END), 0), 1)                                AS dials_per_demo,
    ROUND(SUM(CASE WHEN NOT is_cold_demo_dial AND is_prospecting_dial THEN 1 ELSE 0 END)::float
        / NULLIF(SUM(CASE WHEN is_demo THEN 1 ELSE 0 END), 0), 1)                                AS reg_dials_per_demo,
    ROUND(SUM(CASE WHEN is_cold_demo_dial AND is_demo THEN 1 ELSE 0 END)::float
        / NULLIF(SUM(CASE WHEN is_demo THEN 1 ELSE 0 END), 0) * 100, 1)                          AS cold_demo_pct
FROM sales_ops.tbl_fact_dial_interactions
WHERE interaction_date >= %s
  AND interaction_date <  %s
  AND manager    = %s
  AND quota_team = %s
  AND role       = 'SDR'
  AND is_prospecting_dial = TRUE
GROUP BY 1
ORDER BY demos DESC, user_full_name
"""

MTD_SUMMARY_SQL = """
SELECT
    SUM(prospecting_dials)       AS total_dials,
    SUM(demos)                   AS total_demos,
    SUM(goal_dials_prospecting)  AS dial_goal,
    SUM(goal_demos_daily_adjusted) AS demo_goal
FROM sales_ops.tbl_vw_daily_dial_summary
WHERE activity_date BETWEEN DATE_TRUNC('month', CURRENT_DATE) AND CURRENT_DATE - 1
  AND manager    = %s
  AND quota_team = %s
"""

DEMO_SUMMARY_SQL = """
SELECT
    SUM(CASE WHEN is_confirmed THEN 1 ELSE 0 END)                                                          AS confirmed,
    SUM(CASE WHEN is_demo_performed THEN 1 ELSE 0 END)                                                     AS performed,
    SUM(CASE WHEN NOT is_demo_performed AND demo_perform_date < CURRENT_DATE THEN 1 ELSE 0 END)            AS no_shows,
    ROUND(SUM(CASE WHEN is_demo_performed THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*), 0) * 100, 1)       AS show_rate,
    ROUND(SUM(CASE WHEN is_confirmed THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*), 0) * 100, 1)            AS confirm_rate,
    SUM(CASE WHEN demo_perform_date >= CURRENT_DATE THEN 1 ELSE 0 END)                                    AS future_demos,
    ROUND(SUM(CASE WHEN is_closed_won THEN 1 ELSE 0 END)::float
        / NULLIF(SUM(CASE WHEN is_demo_performed THEN 1 ELSE 0 END), 0) * 100, 1)                        AS gcr
FROM sales_ops.tbl_dim_deals
WHERE demo_perform_month = DATE_TRUNC('month', CURRENT_DATE)
  AND booked_by_quota_team = %s
  AND booked_by IN (
      SELECT user_full_name FROM sales_ops.tbl_dim_users_with_roles
      WHERE manager = %s AND quota_team = %s AND role = 'SDR'
        AND quota > 0 AND role_month = DATE_TRUNC('month', CURRENT_DATE)
  )
"""

MTD_DAILY_AVG_SQL = """
SELECT
    user_full_name,
    ROUND(SUM(prospecting_dials)::float / NULLIF(COUNT(DISTINCT activity_date), 0), 1)  AS avg_dials,
    ROUND(AVG(connect_rate) * 100, 1)                                                    AS avg_connect_pct,
    ROUND(AVG(hook_acceptance_rate) * 100, 1)                                            AS avg_hook_pct,
    ROUND(AVG(demo_per_connect_rate) * 100, 1)                                           AS avg_demo_pct,
    ROUND(SUM(demos)::float / NULLIF(COUNT(DISTINCT activity_date), 0), 1)              AS avg_demos
FROM sales_ops.tbl_vw_daily_dial_summary
WHERE activity_date BETWEEN DATE_TRUNC('month', CURRENT_DATE) AND CURRENT_DATE - 1
  AND manager    = %s
  AND quota_team = %s
  AND prospecting_dials > 0
GROUP BY 1
"""

# ── Email builder ─────────────────────────────────────────────────────────────

def last_business_day():
    """Return the most recent weekday before today."""
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:  # Sat=5, Sun=6
        d -= timedelta(days=1)
    return d


def fmt_row(r, targets):
    """Format a 5-steps row for plain-text email."""
    name = r["user_full_name"].ljust(18)
    return (
        f"{name} "
        f"{num(r['dials'],0):>5}  "
        f"{num(r['connects'],0):>5}  "
        f"{num(r['demos'],0):>4}  "
        f"{pct(r['connect_pct']):>6}{pill(r['connect_pct'], targets['connect'])}  "
        f"{pct(r['hook_pct']):>6}{pill(r['hook_pct'], targets['hook'])}  "
        f"{pct(r['pitch_pct']):>6}{pill(r['pitch_pct'], targets['pitch'])}  "
        f"{pct(r['qq_pct']):>6}{pill(r['qq_pct'], targets['qq'])}  "
        f"{pct(r['demo_pct']):>6}{pill(r['demo_pct'], targets['demo'])}  "
        f"{num(r['dials_per_demo']):>6}  "
        f"{num(r['reg_dials_per_demo']):>8}  "
        f"{pct(r['cold_demo_pct']):>7}"
    )


def build_email(conn):
    today      = date.today()
    yday       = last_business_day()
    month_str  = today.strftime("%B %Y")
    yday_str   = yday.strftime("%b %-d")

    targets = dict(connect=17, hook=85, pitch=75, qq=75, demo=25)

    # Fetch all data
    mtd_rows   = query(conn, MTD_5STEPS_SQL,    [MANAGER, QUOTA_TEAM])
    yday_rows  = query(conn, YDAY_5STEPS_SQL,   [yday, yday + timedelta(days=1), MANAGER, QUOTA_TEAM])
    summary    = query(conn, MTD_SUMMARY_SQL,   [MANAGER, QUOTA_TEAM])[0]
    demos      = query(conn, DEMO_SUMMARY_SQL,  [QUOTA_TEAM, MANAGER, QUOTA_TEAM])[0]
    daily_avgs = query(conn, MTD_DAILY_AVG_SQL, [MANAGER, QUOTA_TEAM])
    avg_by_rep = {r["user_full_name"]: r for r in daily_avgs}

    dial_goal_pct  = (summary["total_dials"] / summary["dial_goal"] * 100) if summary["dial_goal"] else 0
    demo_goal_pct  = (summary["total_demos"] / summary["demo_goal"] * 100) if summary["demo_goal"] else 0

    header = "=" * 68
    col_hdr = (
        f"{'Rep':<18} {'Dials':>5}  {'Conn':>5}  {'Demos':>4}  "
        f"{'Con%':>7}  {'Hook%':>7}  {'Pitch%':>7}  {'QQ%':>7}  "
        f"{'Demo%':>7}  {'D/Dm':>6}  {'RD/Dm':>8}  {'Cold%':>7}"
    )
    sep = "-" * 68

    # MTD 5-steps table
    mtd_table = "\n".join(fmt_row(r, targets) for r in mtd_rows)

    # Totals row for MTD
    def tot(rows, key):
        vals = [r[key] for r in rows if r[key] is not None]
        return sum(vals) if vals else None

    total_dials    = tot(mtd_rows, "dials")
    total_connects = tot(mtd_rows, "connects")
    total_demos_   = tot(mtd_rows, "demos")
    total_conn_pct = (total_connects / total_dials * 100) if total_dials else None
    hook_accepts   = sum((r["connects"] or 0) - int((r["hook_pct"] or 0) / 100 * (r["connects"] or 0)) for r in mtd_rows)
    total_hook_pct = (hook_accepts / total_connects * 100) if total_connects else None

    total_row = (
        f"{'TOTAL':<18} "
        f"{num(total_dials,0):>5}  "
        f"{num(total_connects,0):>5}  "
        f"{num(total_demos_,0):>4}  "
        f"{pct(total_conn_pct):>6}{pill(total_conn_pct, targets['connect'])}  "
        f"{pct(total_hook_pct):>6}{pill(total_hook_pct, targets['hook'])}  "
        f"{'—':>7}  {'—':>7}  {'—':>7}  {'—':>6}  {'—':>8}  {'—':>7}"
    )

    # Yesterday 5-steps table
    yday_table = "\n".join(fmt_row(r, targets) for r in yday_rows) if yday_rows else "  No activity recorded."

    # Yesterday vs MTD norm comparison
    comp_lines = []
    for r in yday_rows:
        name = r["user_full_name"]
        avg  = avg_by_rep.get(name, {})
        comp_lines.append(
            f"  {name}\n"
            f"    Dials:    {num(r['dials'],0):>5}  (avg {num(avg.get('avg_dials'),1)})  {arrow(r['dials'], avg.get('avg_dials'))}\n"
            f"    Connect:  {pct(r['connect_pct']):>6}  (avg {pct(avg.get('avg_connect_pct'))})  {arrow(r['connect_pct'], avg.get('avg_connect_pct'))}\n"
            f"    Hook:     {pct(r['hook_pct']):>6}  (avg {pct(avg.get('avg_hook_pct'))})  {arrow(r['hook_pct'], avg.get('avg_hook_pct'))}\n"
            f"    Demo%:    {pct(r['demo_pct']):>6}  (avg {pct(avg.get('avg_demo_pct'))})  {arrow(r['demo_pct'], avg.get('avg_demo_pct'))}\n"
            f"    Demos:    {num(r['demos'],0):>5}  (avg {num(avg.get('avg_demos'),1)})  {arrow(r['demos'], avg.get('avg_demos'))}"
        )
    comp_section = "\n\n".join(comp_lines)

    body = f"""Good morning Matthew,

Here is your Legal SDR Morning Digest — {month_str}.

{header}
 SECTION 1 · MTD PROSPECTING KPIs
{header}
All Dials:      {dial_goal_pct:.1f}%   ({num(summary['total_dials'],0)} / {num(summary['dial_goal'],0)} goal)
Demos Booked:   {demo_goal_pct:.1f}%   ({num(summary['total_demos'],0)} / {num(summary['demo_goal'],1)} goal)

Demos Confirmed:    {pct(demos['confirm_rate'])}    Demos Performed:  {num(demos['performed'],0)}
Demo No Shows:      {num(demos['no_shows'],0)}         Show Rate:        {pct(demos['show_rate'])}
Booked-By GCR:      {pct(demos['gcr'])}    Future Demos:     {num(demos['future_demos'],0)}

── 5-STEPS BY REP (MTD) {'─'*20}
{col_hdr}
{sep}
{mtd_table}
{sep}
{total_row}

Targets: Connect 17% | Hook 85% | Pitch 75% | QQ 75% | Demo 25%
✓ = at/above target   ⚠ = below target
* Pitch % = QP / hook accepts (may differ slightly from dashboard
  until "Set via Goal Uploads" filter is resolved)

{header}
 SECTION 2 · YESTERDAY ({yday_str}) — 5-STEPS
{header}
{col_hdr}
{sep}
{yday_table}

── YESTERDAY vs MTD DAILY AVERAGE {'─'*10}
{comp_section}

{header}
 SECTION 3 · WoW HOTSPOTS  [coming soon]
{header}

{'─'*68}
Data: Sales Insights (Redshift) · Refreshed hourly
Sender: claude.dailysend@gmail.com · 7:30am EST Mon–Fri
"""
    return body


# ── Send ──────────────────────────────────────────────────────────────────────

def send_email(body):
    today     = date.today()
    month_str = today.strftime("%b %Y")
    subject   = f"Legal SDR Morning Digest — {month_str} · {today.strftime('%-d %b')}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = RECIPIENT
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, RECIPIENT, msg.as_string())

    print(f"✓ Digest sent to {RECIPIENT}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    conn = psycopg2.connect(**DB)
    try:
        body = build_email(conn)
        send_email(body)
    finally:
        conn.close()
