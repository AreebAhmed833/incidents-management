from flask import Flask, render_template, request, redirect, url_for, flash, make_response
import mysql.connector
import json
import io
import csv

#new Comment added for testing jenkins trigger 2 by adding ngrok
#new commit to check - chanikya

app = Flask(__name__)
app.secret_key = 'super_secret_key'

db_config = {
    'host': 'serverless-europe-west3.sysp0000.db2.skysql.com',
    'user': 'dbpgf38237478',
    'password': ':x9ywtb734M%jK)Hb2vWz',
    'database': 'incident_db',
    'port': 4040
}


def get_db_connection():
    return mysql.connector.connect(**db_config)

def write_log(cursor, incident_id, action, message):
    cursor.execute("INSERT INTO incident_logs (incident_id, action, message) VALUES (%s, %s, %s)", 
                   (incident_id, action, message))

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
    if request.method == 'POST':
        service = request.form['service']
        severity = request.form['severity']
        description = request.form['description']
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT id FROM incidents ORDER BY id DESC LIMIT 1")
        last = cursor.fetchone()
        new_id = (last['id'] + 1) if last else 1
        custom_id = f"INC{new_id:03d}"
        
        cursor.execute("INSERT INTO incidents (custom_id, service, severity, description) VALUES (%s, %s, %s, %s)",
                       (custom_id, service, severity, description))
        conn.commit()
        write_log(cursor, cursor.lastrowid, "CREATED", "Incident Logged")
        conn.commit()
        
        cursor.close()
        conn.close()
        flash('Incident created successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('create.html')

# --- 4. EDIT ---
@app.route('/edit/<int:id>', methods=('GET', 'POST'))
def edit(id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM incidents WHERE id=%s", (id,))
    incident = cursor.fetchone()
    cursor.execute("SELECT * FROM incident_logs WHERE incident_id=%s ORDER BY timestamp DESC", (id,))
    logs = cursor.fetchall()

    if request.method == 'POST':
        new_status = request.form.get('status')
        new_sev = request.form.get('severity')
        new_desc = request.form.get('description')
        
        if new_status and new_status != incident['status']:
            write_log(cursor, id, "STATUS_CHANGE", f"{incident['status']} -> {new_status}")
            cursor.execute("UPDATE incidents SET status=%s WHERE id=%s", (new_status, id))
            
        if new_sev and new_sev != incident['severity']:
            write_log(cursor, id, "SEV_CHANGE", f"{incident['severity']} -> {new_sev}")
            cursor.execute("UPDATE incidents SET severity=%s WHERE id=%s", (new_sev, id))

        if new_desc and new_desc != incident['description']:
            cursor.execute("UPDATE incidents SET description=%s WHERE id=%s", (new_desc, id))
            
        conn.commit()
        cursor.close()
        conn.close()
        flash('Incident updated!', 'success')
        return redirect(url_for('edit', id=id))

    return render_template('edit.html', incident=incident, logs=logs)

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
