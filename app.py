from flask import Flask, render_template, request, redirect, url_for, flash, make_response
import mysql.connector
import json
import io
import csv
import os
import warnings
import markdown

# Load .env from project directory if present (e.g. on EC2; file is not in git)
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.isfile(_env_path):
        load_dotenv(_env_path)
except ImportError:
    pass

# Suppress Google lib FutureWarnings about Python 3.8 (so you can see Gemini success/failure clearly)
warnings.filterwarnings("ignore", category=FutureWarning, module="google.")
# new commit after k8
#New commit
# New commit
#app.py
#chanikya - 1st commit
#added commit to chech build on ec2-harsha

app = Flask(__name__)
app.secret_key = 'super_secret_key'


@app.template_filter('markdown')
def markdown_filter(s):
    if not s:
        return ""
    from markupsafe import Markup
    return Markup(markdown.markdown(s, extensions=['nl2br']))

db_config = {
    'host': 'serverless-europe-west3.sysp0000.db2.skysql.com',
    'user': 'dbpgf38237478',
    'password': ':x9ywtb734M%jK)Hb2vWz',
    'database': 'incident_db',
    'port': 4040
}


def get_db_connection():
    return mysql.connector.connect(**db_config)


# Ensures DB has system_logs column (logs were silently dropped if INSERT/UPDATE fell back).
_incidents_schema_checked = False


def ensure_incidents_schema():
    """Add incidents.system_logs if missing (one attempt per process)."""
    global _incidents_schema_checked
    if _incidents_schema_checked:
        return
    _incidents_schema_checked = True
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT DATABASE()")
        dbrow = cur.fetchone()
        schema_name = (dbrow[0] if dbrow and dbrow[0] else None) or db_config["database"]
        cur.execute(
            """
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'incidents' AND COLUMN_NAME = 'system_logs'
            """,
            (schema_name,),
        )
        if cur.fetchone()[0] == 0:
            cur.execute("ALTER TABLE incidents ADD COLUMN system_logs TEXT NULL")
            conn.commit()
            print("[DB] Added missing column: incidents.system_logs (for separate Logs field).")
        cur.close()
        conn.close()
    except Exception as e:
        print("[DB] Could not ensure incidents.system_logs column — run migrations/add_system_logs_column.sql:", e)


def write_log(cursor, incident_id, action, message):
    cursor.execute("INSERT INTO incident_logs (incident_id, action, message) VALUES (%s, %s, %s)", 
                   (incident_id, action, message))


LOG_MERGER_MARKER = "--- Application logs ---"


def normalize_row_keys(row):
    """Normalize dict keys to lowercase (MariaDB/MySQL drivers may return mixed-case column names)."""
    if not row:
        return row
    return {str(k).lower(): v for k, v in row.items()}


def errors_and_logs_for_form(incident):
    """
    Build textarea values for Errors vs Logs. Prefer system_logs column; if empty, split legacy
    merged error_logs (when DB had no system_logs column).
    """
    if not incident:
        return "", ""
    el_raw = incident.get("error_logs")
    sl_raw = incident.get("system_logs")
    el = (el_raw or "").strip() if isinstance(el_raw, str) else str(el_raw or "").strip()
    sl = (sl_raw or "").strip() if isinstance(sl_raw, str) else str(sl_raw or "").strip()
    if sl:
        return el, sl
    if LOG_MERGER_MARKER in el:
        idx = el.find(LOG_MERGER_MARKER)
        err_part = el[:idx].strip()
        log_part = el[idx + len(LOG_MERGER_MARKER) :].lstrip("\n").strip()
        return err_part, log_part
    return el, ""


def _build_ai_prompt(service, severity, description, error_logs=None, system_logs=None, impact=None):
    """Build the incident analysis prompt (shared by all providers)."""
    detail_lines = []
    if error_logs:
        detail_lines.append(f"* Errors: {error_logs}")
    if system_logs:
        detail_lines.append(f"* Application / server logs: {system_logs}")
    extra_section = ("\n" + "\n".join(detail_lines)) if detail_lines else ""
    impact_section = f"\n* Impact: {impact}" if impact else ""

    log_note = (
        "\n\nNote: **Application / server logs** (if present) are separate from **Errors**; use both in your analysis."
        if (system_logs and error_logs)
        else ""
    )

    if system_logs:
        section_guide = """Analyze the issue and provide a structured response with the following sections. Use clear markdown headings (##) and bullet points. Be concise and actionable for SREs.

1. **Summary** – Brief problem summary (2–3 sentences).
2. **Log interpretation** – Required: quote or reference specific log lines, timestamps, severity levels, and request IDs when present; relate them to the errors and description; call out anomalies, patterns, or smoking guns.
3. **Possible root causes** – List likely causes.
4. **Step-by-step troubleshooting** – Numbered steps to diagnose and isolate the issue.
5. **Suggested fixes** – Concrete remediation steps.
6. **Preventive measures** – How to reduce recurrence (monitoring, config, runbooks)."""
    else:
        section_guide = """Analyze the issue and provide a structured response with the following sections. Use clear markdown headings (##) and bullet points. Be concise and actionable for SREs.

1. **Summary** – Brief problem summary (2–3 sentences).
2. **Possible root causes** – List likely causes.
3. **Step-by-step troubleshooting** – Numbered steps to diagnose and isolate the issue.
4. **Suggested fixes** – Concrete remediation steps.
5. **Preventive measures** – How to reduce recurrence (monitoring, config, runbooks)."""

    return f"""An incident has been reported in a production environment. Below are the details:

* Service: {service}
* Severity: {severity}
* Description: {description}{extra_section}{impact_section}{log_note}

{section_guide}"""


def _call_gemini_rest(api_key, full_prompt, model_id="gemini-2.0-flash", max_output_tokens=1500):
    """Call Gemini via REST API (works even when SDK has import issues). Returns text or None."""
    try:
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        key = (api_key or "").strip()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={key}"
        body = json.dumps({
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": {"maxOutputTokens": int(max_output_tokens)},
        }).encode("utf-8")
        req = Request(url, data=body, method="POST", headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
        text = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        return (text or "").strip() or None
    except Exception as e:
        print("[AI] Gemini error:", e)
        return None


# Log "no API key" at most once per process (edit/save would otherwise spam the console).
_ai_key_missing_logged = False


def get_ai_analysis(service, severity, description, error_logs=None, system_logs=None, impact=None):
    """Use Gemini only (same approach as your friend's code). Key from GEMINI_API_KEY."""
    global _ai_key_missing_logged
    gemini_key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not gemini_key:
        if not _ai_key_missing_logged:
            print(
                "[AI] No API key. Set GEMINI_API_KEY or GOOGLE_API_KEY "
                "(https://aistudio.google.com/apikey), or add it to .env in this folder, then restart."
            )
            _ai_key_missing_logged = True
        return None

    prompt = _build_ai_prompt(service, severity, description, error_logs, system_logs, impact)
    system = "You are an expert SRE assisting with incident analysis. Provide structured, actionable guidance in markdown. Be concise and production-focused."
    full_prompt = f"{system}\n\n{prompt}"
    max_tokens = 2500 if (system_logs or "").strip() else 1500

    for model_id in ["gemini-2.0-flash", "gemini-3-flash-preview", "gemini-1.5-flash"]:
        try:
            print("[AI] Calling Gemini for analysis...")
            out = _call_gemini_rest(
                gemini_key, full_prompt, model_id=model_id, max_output_tokens=max_tokens
            )
            if out:
                print("[AI] Analysis received (Gemini).")
                return out
        except Exception as e:
            print("[AI] Gemini failed:", e)
            continue
    return None

# --- 1. HOME: The Dashboard (New!) ---
@app.route('/')
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # KPI: Total & Active SEV1
    cursor.execute("SELECT COUNT(*) as total FROM incidents")
    total = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as active FROM incidents WHERE severity='SEV1' AND status!='Resolved'")
    active_sev1 = cursor.fetchone()['active']

    # Chart 1: Severity Breakdown
    cursor.execute("SELECT severity, COUNT(*) as count FROM incidents GROUP BY severity")
    sev_data = cursor.fetchall()
    sev_labels = [row['severity'] for row in sev_data]
    sev_values = [row['count'] for row in sev_data]

    # Chart 2: Status Breakdown
    cursor.execute("SELECT status, COUNT(*) as count FROM incidents GROUP BY status")
    stat_data = cursor.fetchall()
    stat_labels = [row['status'] for row in stat_data]
    stat_values = [row['count'] for row in stat_data]

    # Recent Activity (Last 5)
    cursor.execute("SELECT * FROM incidents ORDER BY created_at DESC LIMIT 5")
    recents = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('dashboard.html', 
                           total=total, 
                           active_sev1=active_sev1,
                           sev_labels=json.dumps(sev_labels),
                           sev_values=json.dumps(sev_values),
                           stat_labels=json.dumps(stat_labels),
                           stat_values=json.dumps(stat_values),
                           recents=recents)

# --- 2. LIST: The Search Page ---
@app.route('/incidents')
def incident_list():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    search = request.args.get('search')
    if search:
        query = "SELECT * FROM incidents WHERE service LIKE %s OR custom_id LIKE %s ORDER BY created_at DESC"
        cursor.execute(query, (f"%{search}%", f"%{search}%"))
    else:
        cursor.execute("SELECT * FROM incidents ORDER BY created_at DESC")
    
    incidents = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('list.html', incidents=incidents)

# --- 3. CREATE ---
@app.route('/create', methods=('GET', 'POST'))
def create():
    ensure_incidents_schema()
    if request.method == 'POST':
        service = request.form['service']
        severity = request.form['severity']
        description = request.form['description']
        error_logs = request.form.get('error_logs', '').strip() or None
        system_logs = request.form.get('system_logs', '').strip() or None
        impact = request.form.get('impact', '').strip() or None

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id FROM incidents ORDER BY id DESC LIMIT 1")
        last = cursor.fetchone()
        new_id = (last['id'] + 1) if last else 1
        custom_id = f"INC{new_id:03d}"

        try:
            cursor.execute(
                """INSERT INTO incidents (custom_id, service, severity, description, error_logs, system_logs, impact)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (custom_id, service, severity, description, error_logs or '', system_logs or '', impact or '')
            )
        except mysql.connector.Error:
            try:
                cursor.execute(
                    """INSERT INTO incidents (custom_id, service, severity, description, error_logs, impact)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (custom_id, service, severity, description, error_logs or '', impact or '')
                )
            except mysql.connector.Error:
                cursor.execute(
                    "INSERT INTO incidents (custom_id, service, severity, description) VALUES (%s, %s, %s, %s)",
                    (custom_id, service, severity, description)
                )
            # DB had no system_logs column — keep log text in error_logs so UI/AI still see it
            if system_logs:
                try:
                    base = (error_logs or "").strip()
                    merged = (
                        (base + "\n\n" + LOG_MERGER_MARKER + "\n" + system_logs).strip()
                        if base
                        else f"{LOG_MERGER_MARKER}\n{system_logs}"
                    )
                    cursor.execute(
                        "UPDATE incidents SET error_logs = %s WHERE id = %s",
                        (merged, cursor.lastrowid),
                    )
                except mysql.connector.Error:
                    pass
        incident_id = cursor.lastrowid
        conn.commit()
        write_log(cursor, incident_id, "CREATED", "Incident Logged")
        conn.commit()

        ai_analysis = None
        try:
            ai_analysis = get_ai_analysis(service, severity, description, error_logs, system_logs, impact)
            if ai_analysis:
                cursor.execute("UPDATE incidents SET ai_analysis = %s WHERE id = %s", (ai_analysis, incident_id))
                conn.commit()
                write_log(cursor, incident_id, "AI_ANALYSIS", "AI analysis generated")
                conn.commit()
                print("[AI] Analysis saved to database.")
        except mysql.connector.Error as e:
            print("[AI] Could not save analysis to DB (is migration applied?):", e)

        cursor.close()
        conn.close()
        if ai_analysis:
            flash('Incident created successfully! AI analysis has been generated.', 'success')
        else:
            flash('Incident created successfully! AI analysis was not generated (quota may be exceeded; try again later).', 'success')
        return redirect(url_for('edit', id=incident_id))

    return render_template('create.html')

# --- 4. EDIT ---
@app.route('/edit/<int:id>', methods=('GET', 'POST'))
def edit(id):
    ensure_incidents_schema()
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM incidents WHERE id=%s", (id,))
    incident = cursor.fetchone()
    if incident:
        incident = normalize_row_keys(incident)
    cursor.execute("SELECT * FROM incident_logs WHERE incident_id=%s ORDER BY timestamp DESC", (id,))
    logs = cursor.fetchall()
    display_error_logs, display_system_logs = errors_and_logs_for_form(incident)

    if request.method == 'POST':
        new_status = request.form.get('status')
        new_sev = request.form.get('severity')
        new_desc = request.form.get('description')
        new_error_logs = (request.form.get("error_logs") or "").strip()
        new_system_logs = (request.form.get("system_logs") or "").strip()
        new_impact = (request.form.get("impact") or "").strip()

        if new_status and new_status != incident['status']:
            write_log(cursor, id, "STATUS_CHANGE", f"{incident['status']} -> {new_status}")
            cursor.execute("UPDATE incidents SET status=%s WHERE id=%s", (new_status, id))
            
        if new_sev and new_sev != incident['severity']:
            write_log(cursor, id, "SEV_CHANGE", f"{incident['severity']} -> {new_sev}")
            cursor.execute("UPDATE incidents SET severity=%s WHERE id=%s", (new_sev, id))

        if new_desc is not None and new_desc != incident['description']:
            cursor.execute("UPDATE incidents SET description=%s WHERE id=%s", (new_desc, id))

        prev_err, prev_log = errors_and_logs_for_form(incident)
        logs_changed = (new_error_logs != prev_err) or (new_system_logs != prev_log)

        try:
            cursor.execute(
                "UPDATE incidents SET error_logs=%s, system_logs=%s, impact=%s WHERE id=%s",
                (new_error_logs or '', new_system_logs or '', new_impact or '', id),
            )
        except mysql.connector.Error:
            try:
                merged_errors = new_error_logs
                if new_system_logs:
                    merged_errors = (
                        (new_error_logs + "\n\n" + LOG_MERGER_MARKER + "\n" + new_system_logs).strip()
                        if new_error_logs
                        else f"{LOG_MERGER_MARKER}\n{new_system_logs}"
                    )
                cursor.execute(
                    "UPDATE incidents SET error_logs=%s, impact=%s WHERE id=%s",
                    (merged_errors or "", new_impact or "", id),
                )
            except mysql.connector.Error:
                pass
        conn.commit()

        # Re-run AI analysis with updated incident details so analysis stays in sync
        service = incident['service']
        severity = new_sev if new_sev else incident['severity']
        description = new_desc if (new_desc is not None and new_desc.strip()) else incident['description']
        error_logs = new_error_logs or None
        system_logs = new_system_logs or None
        impact = new_impact or None
        try:
            ai_analysis = get_ai_analysis(service, severity, description, error_logs, system_logs, impact)
            if ai_analysis:
                cursor.execute("UPDATE incidents SET ai_analysis = %s WHERE id = %s", (ai_analysis, id))
                conn.commit()
                msg = (
                    "AI analysis regenerated after edit (includes logs)."
                    if (system_logs or "").strip()
                    else "AI analysis regenerated after edit"
                )
                write_log(cursor, id, "AI_ANALYSIS", msg)
                conn.commit()
                flash('Incident updated! AI analysis has been regenerated.', 'success')
            else:
                if logs_changed and (new_system_logs or "").strip():
                    flash(
                        "Incident updated. Logs were saved. AI analysis was not regenerated "
                        "(check GEMINI_API_KEY and quota).",
                        "warning",
                    )
                else:
                    flash("Incident updated!", "success")
        except mysql.connector.Error:
            flash('Incident updated! (AI analysis could not be saved.)', 'success')

        cursor.close()
        conn.close()
        return redirect(url_for('edit', id=id))

    return render_template(
        "edit.html",
        incident=incident,
        logs=logs,
        display_error_logs=display_error_logs,
        display_system_logs=display_system_logs,
    )

# --- 5. EXPORT ---
@app.route('/export')
def export_csv():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM incidents")
    result = cursor.fetchall()
    
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Custom ID', 'Service', 'Severity', 'Desc', 'Status', 'Date'])
    cw.writerows(result)
    
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=incidents.csv"
    output.headers["Content-type"] = "text/csv"
    return output
@app.route('/delete/<int:id>', methods=['POST'])
def delete(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Check if the incident is actually resolved
    cursor.execute("SELECT status FROM incidents WHERE id = %s", (id,))
    incident = cursor.fetchone()
    
    if incident and incident['status'] == 'Resolved':
        cursor.execute("DELETE FROM incidents WHERE id = %s", (id,))
        conn.commit()
        flash('Incident permanently deleted.', 'success')
    else:
        flash('Action Denied: Only Resolved incidents can be deleted.', 'error')
        
    cursor.close()
    conn.close()
    
    return redirect(url_for('incident_list'))
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=False)
