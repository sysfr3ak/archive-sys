
import os
import sqlite3
import datetime
import calendar
import shutil
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'gif'}
MAX_PER_JOB = 30

TRACKER_STAGES = [
    ('PRE_DESIGN', 'Pre-Press: Designing', 'Pre-Press'),
    ('PRESS_PRINTING', 'Press: Printing', 'Press'),
    ('POST_LAMINATION', 'Post-Press: Lamination', 'Post-Press'),
    ('POST_DIECUT', 'Post-Press: Die cutting', 'Post-Press'),
    ('POST_GUILLOTINE', 'Post-Press: Guillotine', 'Post-Press'),
    ('POST_BINDING', 'Post-Press: Binding', 'Post-Press'),
    ('POST_PACKING', 'Post-Press: Packing', 'Post-Press'),
    ('POST_OUT_FOR_DELIVERY', 'Post-Press: Out for delivery', 'Post-Press'),
    ('POST_DELIVERED', 'Post-Press: Delivered', 'Post-Press'),
]

def get_stage_label(code):
    for c, label, group in TRACKER_STAGES:
        if c == code:
            return label
    return None

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SECRET_KEY'] = 'replace-with-a-secure-secret'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    # Main jobs table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY,
            job_no TEXT UNIQUE,
            name TEXT,
            date TEXT,
            paper TEXT,
            note TEXT
        )
    ''')
    cur.execute("PRAGMA table_info(jobs)")
    cols = [row[1] for row in cur.fetchall()]
    if 'price' not in cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN price TEXT")
    if 'serial' not in cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN serial TEXT")
    if 'created_by' not in cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN created_by INTEGER")
    if 'created_at' not in cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN created_at TEXT")
    if 'updated_by' not in cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN updated_by INTEGER")
    if 'updated_at' not in cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN updated_at TEXT")
    if 'stage' not in cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN stage TEXT")
    if 'stage_updated_by' not in cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN stage_updated_by INTEGER")
    if 'stage_updated_at' not in cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN stage_updated_at TEXT")
    if 'pre_plate' not in cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN pre_plate INTEGER DEFAULT 0")
    if 'pre_die' not in cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN pre_die INTEGER DEFAULT 0")
    if 'pre_paper' not in cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN pre_paper INTEGER DEFAULT 0")
    # Outsourced processing timestamps
    if 'plate_sent_at' not in cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN plate_sent_at TEXT")
    if 'plate_received_at' not in cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN plate_received_at TEXT")
    if 'die_sent_at' not in cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN die_sent_at TEXT")
    if 'die_received_at' not in cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN die_received_at TEXT")
    if 'paper_sent_at' not in cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN paper_sent_at TEXT")
    if 'paper_done_at' not in cols:
        cur.execute("ALTER TABLE jobs ADD COLUMN paper_done_at TEXT")

    # Photos table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY,
            job_id INTEGER,
            filename TEXT,
            uploaded_at TEXT
        )
    ''')

    # Users table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT UNIQUE,
            password_hash TEXT,
            role TEXT
        )
    ''')

    # Activity log
    cur.execute('''
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            action TEXT,
            job_id INTEGER,
            job_no TEXT,
            details TEXT,
            created_at TEXT
        )
    ''')

    # Stage history for tracker detail
    cur.execute('''
        CREATE TABLE IF NOT EXISTS stage_history (
            id INTEGER PRIMARY KEY,
            job_id INTEGER,
            stage TEXT,
            updated_by INTEGER,
            updated_at TEXT,
            pre_plate INTEGER,
            pre_die INTEGER,
            pre_paper INTEGER
        )
    ''')

    # Backup logbook table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS backup_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            backup_date TEXT NOT NULL,
            next_due TEXT NOT NULL,
            backup_type TEXT,
            backup_location TEXT,
            notes TEXT,
            created_by INTEGER,
            created_at TEXT
        )
    ''')

    conn.commit()

    # Ensure default super admin user exists
    cur.execute("SELECT id FROM users WHERE username = ?", ('isuka',))
    row = cur.fetchone()
    if not row:
        pwd = generate_password_hash('Colour@123')
        cur.execute(
            "INSERT INTO users (full_name, username, password_hash, role) VALUES (?, ?, ?, ?)",
            ('Isuka Kasthuriarachchi', 'isuka', pwd, 'superadmin'),
        )
        conn.commit()

    conn.close()
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(fn):
    return '.' in fn and fn.rsplit('.', 1)[1].lower() in ALLOWED_EXT

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return wrapper

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login', next=request.path))
            if session.get('role') not in roles:
                flash('You do not have permission to access this page', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return wrapper
    return decorator

def log_action(user_id, action, job_id=None, job_no=None, details=None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO activity_log (user_id, action, job_id, job_no, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, action, job_id, job_no, details, datetime.datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def add_one_month(date_str: str) -> str:
    """Add one calendar month to a YYYY-MM-DD date string (clamp day)."""
    d = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    y, m = d.year, d.month
    if m == 12:
        y2, m2 = y + 1, 1
    else:
        y2, m2 = y, m + 1
    last_day = calendar.monthrange(y2, m2)[1]
    return datetime.date(y2, m2, min(d.day, last_day)).strftime("%Y-%m-%d")

def backup_status(next_due_str: str, due_soon_days: int = 5):
    """Return (status_key, days_until_due). status_key: up_to_date | due_soon | overdue | unknown"""
    try:
        due = datetime.datetime.strptime(next_due_str, "%Y-%m-%d").date()
    except Exception:
        return ("unknown", None)
    today = datetime.date.today()
    delta = (due - today).days
    if delta < 0:
        return ("overdue", delta)
    if delta <= due_soon_days:
        return ("due_soon", delta)
    return ("up_to_date", delta)

@app.context_processor
def inject_user():
    return {
        'current_user_id': session.get('user_id'),
        'current_user_name': session.get('full_name'),
        'current_user_role': session.get('role'),
        'TRACKER_STAGES': TRACKER_STAGES,
        'get_stage_label': get_stage_label,
    }

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['full_name'] = user['full_name']
            session['role'] = user['role']
            flash('Logged in', 'success')
            next_url = request.args.get('next') or url_for('index')
            return redirect(next_url)
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    q = request.args.get('q', '').strip()
    mode = request.args.get('mode', '')
    year = request.args.get('year', '').strip()
    month = request.args.get('month', '').strip()

    conn = get_db()
    cur = conn.cursor()
    query = "SELECT * FROM jobs WHERE 1=1"
    params = []
    if year:
        query += " AND substr(date,1,4) = ?"
        params.append(year)
    if month:
        if len(month) == 1:
            month = f"0{month}"
        query += " AND substr(date,6,2) = ?"
        params.append(month)

    if q and mode == 'job':
        query += " AND job_no LIKE ?"
        params.append(f"%{q}%")
    elif q and mode == 'customer':
        query += " AND name LIKE ?"
        params.append(f"%{q}%")
    elif q and mode == 'keyword':
        like = f"%{q}%"
        query += " AND (name LIKE ? OR note LIKE ? OR paper LIKE ? OR job_no LIKE ?)"
        params.extend([like, like, like, like])

    query += " ORDER BY date DESC, id DESC"
    cur.execute(query, params)
    jobs = cur.fetchall()

    cur.execute("SELECT DISTINCT substr(date,1,4) AS y FROM jobs WHERE date IS NOT NULL AND date != '' ORDER BY y DESC")
    years = [row['y'] for row in cur.fetchall() if row['y']]

    
    # Backup status (monthly)
    cur.execute("SELECT b.*, u.full_name FROM backup_log b LEFT JOIN users u ON b.created_by = u.id ORDER BY b.backup_date DESC, b.id DESC LIMIT 1")
    last_backup = cur.fetchone()
    backup_status_key = None
    backup_days_until = None
    if last_backup and last_backup['next_due']:
        backup_status_key, backup_days_until = backup_status(last_backup['next_due'], due_soon_days=5)

    conn.close()
    return render_template('dashboard.html', jobs=jobs, q=q, mode=mode, sel_year=year, sel_month=month, years=years, last_backup=last_backup, backup_status_key=backup_status_key, backup_days_until=backup_days_until)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    role = session.get('role')
    if role not in ('superadmin', 'admin', 'staff'):
        flash('You do not have permission to add jobs', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        job_no = request.form.get('job_no', '').strip()
        name = request.form.get('name', '').strip()
        date = request.form.get('date', '').strip()
        paper = request.form.get('paper', '').strip()
        note = request.form.get('note', '').strip()
        price = request.form.get('price', '').strip()
        serial = request.form.get('serial', '').strip()
        stage = request.form.get('stage', '').strip() or 'PRE_DESIGN'

        pre_plate = 1 if request.form.get('pre_plate') == 'on' else 0
        pre_die = 1 if request.form.get('pre_die') == 'on' else 0
        pre_paper = 1 if request.form.get('pre_paper') == 'on' else 0

        if not job_no or not name:
            flash('Job number and customer name are required', 'warning')
            return redirect(url_for('add'))

        conn = get_db()
        cur = conn.cursor()
        now = datetime.datetime.now().isoformat()
        try:
            cur.execute(
                'INSERT INTO jobs (job_no, name, date, paper, note, price, serial, created_by, created_at, stage, stage_updated_by, stage_updated_at, pre_plate, pre_die, pre_paper) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    job_no,
                    name,
                    date,
                    paper,
                    note,
                    price,
                    serial,
                    session.get('user_id'),
                    now,
                    stage,
                    session.get('user_id'),
                    now,
                    pre_plate,
                    pre_die,
                    pre_paper,
                ),
            )
        except sqlite3.IntegrityError:
            flash('Job number already exists. Use edit to modify.', 'danger')
            conn.close()
            return redirect(url_for('add'))

        job_id = cur.lastrowid
        # record initial stage in history
        cur.execute(
            'INSERT INTO stage_history (job_id, stage, updated_by, updated_at, pre_plate, pre_die, pre_paper) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (job_id, stage, session.get('user_id'), now, pre_plate, pre_die, pre_paper),
        )
        conn.commit()

        files = request.files.getlist('photos')
        job_folder = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(job_no))
        os.makedirs(job_folder, exist_ok=True)
        saved = 0
        for f in files:
            if f and f.filename and allowed_file(f.filename) and saved < MAX_PER_JOB:
                fn = secure_filename(f.filename)
                base, ext = os.path.splitext(fn)
                stamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
                fn = f"{base}_{stamp}{ext}"
                f.save(os.path.join(job_folder, fn))
                cur.execute(
                    'INSERT INTO photos (job_id, filename, uploaded_at) VALUES (?, ?, ?)',
                    (job_id, fn, datetime.datetime.now().isoformat()),
                )
                saved += 1

        conn.commit()
        conn.close()

        log_action(session.get('user_id'), 'CREATE_JOB', job_id=job_id, job_no=job_no)

        flash('Job saved successfully', 'success')
        return redirect(url_for('index'))

    return render_template('add_job.html')

@app.route('/job/<int:job_id>')
@login_required
def job_detail(job_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM jobs WHERE id = ?', (job_id,))
    job = cur.fetchone()
    if not job:
        conn.close()
        flash('Job not found', 'warning')
        return redirect(url_for('index'))

    cur.execute('SELECT * FROM photos WHERE job_id = ? ORDER BY id DESC', (job_id,))
    photos = cur.fetchall()

    created_by_name = None
    updated_by_name = None
    if job['created_by']:
        cur.execute("SELECT full_name FROM users WHERE id = ?", (job['created_by'],))
        u = cur.fetchone()
        created_by_name = u['full_name'] if u else None
    if job['updated_by']:
        cur.execute("SELECT full_name FROM users WHERE id = ?", (job['updated_by'],))
        u = cur.fetchone()
        updated_by_name = u['full_name'] if u else None

    conn.close()
    stage_label = get_stage_label(job['stage']) if job['stage'] else None
    return render_template('job_detail.html', job=job, photos=photos,
                           created_by_name=created_by_name, updated_by_name=updated_by_name,
                           stage_label=stage_label)

@app.route('/uploads/<job_no>/<filename>')
@login_required
def uploaded_file(job_no, filename):
    folder = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(job_no))
    return send_from_directory(folder, filename)

@app.route('/delete_job/<int:job_id>', methods=['POST'])
@login_required
def delete_job(job_id):
    if session.get('role') not in ('superadmin', 'admin'):
        flash('Only admin or super admin can delete jobs', 'danger')
        return redirect(url_for('job_detail', job_id=job_id))

    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT job_no FROM jobs WHERE id = ?', (job_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        flash('Job not found', 'warning')
        return redirect(url_for('index'))

    job_no = row['job_no']

    cur.execute('DELETE FROM photos WHERE job_id = ?', (job_id,))
    cur.execute('DELETE FROM jobs WHERE id = ?', (job_id,))
    conn.commit()
    conn.close()

    folder = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(job_no))
    if os.path.exists(folder):
        try:
            shutil.rmtree(folder)
        except Exception as e:
            print('Error deleting folder', e)

    log_action(session.get('user_id'), 'DELETE_JOB', job_id=job_id, job_no=job_no)

    flash('Job deleted', 'success')
    return redirect(url_for('index'))

@app.route('/edit/<int:job_id>', methods=['GET', 'POST'])
@login_required
def edit(job_id):
    if session.get('role') not in ('superadmin', 'admin'):
        flash('Only admin or super admin can edit jobs', 'danger')
        return redirect(url_for('job_detail', job_id=job_id))

    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM jobs WHERE id = ?', (job_id,))
    job = cur.fetchone()
    if not job:
        conn.close()
        flash('Job not found', 'warning')
        return redirect(url_for('index'))

    if request.method == 'POST':
        job_no = request.form.get('job_no', '').strip()
        name = request.form.get('name', '').strip()
        date = request.form.get('date', '').strip()
        paper = request.form.get('paper', '').strip()
        note = request.form.get('note', '').strip()
        price = request.form.get('price', '').strip()
        serial = request.form.get('serial', '').strip()

        old_job_no = job['job_no']
        if job_no != old_job_no:
            old_folder = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(old_job_no))
            new_folder = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(job_no))
            if os.path.exists(old_folder):
                try:
                    os.rename(old_folder, new_folder)
                except Exception as e:
                    print('Error renaming folder', e)

        try:
            cur.execute(
                'UPDATE jobs SET job_no = ?, name = ?, date = ?, paper = ?, note = ?, price = ?, serial = ?, updated_by = ?, updated_at = ? WHERE id = ?',
                (
                    job_no,
                    name,
                    date,
                    paper,
                    note,
                    price,
                    serial,
                    session.get('user_id'),
                    datetime.datetime.now().isoformat(),
                    job_id,
                ),
            )
        except sqlite3.IntegrityError:
            flash('Job number already exists for another job', 'danger')
            conn.close()
            return redirect(url_for('edit', job_id=job_id))

        files = request.files.getlist('photos')
        job_folder = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(job_no))
        os.makedirs(job_folder, exist_ok=True)
        saved = 0
        for f in files:
            if f and f.filename and allowed_file(f.filename) and saved < MAX_PER_JOB:
                fn = secure_filename(f.filename)
                base, ext = os.path.splitext(fn)
                stamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
                fn = f"{base}_{stamp}{ext}"
                f.save(os.path.join(job_folder, fn))
                cur.execute(
                    'INSERT INTO photos (job_id, filename, uploaded_at) VALUES (?, ?, ?)',
                    (job_id, fn, datetime.datetime.now().isoformat()),
                )
                saved += 1

        conn.commit()
        conn.close()

        log_action(session.get('user_id'), 'EDIT_JOB', job_id=job_id, job_no=job_no)

        flash('Job updated', 'success')
        return redirect(url_for('job_detail', job_id=job_id))

    cur.execute('SELECT * FROM photos WHERE job_id = ? ORDER BY id DESC', (job_id,))
    photos = cur.fetchall()
    conn.close()
    return render_template('edit_job.html', job=job, photos=photos)

@app.route('/delete_photo/<int:photo_id>', methods=['POST'])
@login_required
def delete_photo(photo_id):
    if session.get('role') not in ('superadmin', 'admin'):
        flash('Only admin or super admin can delete photos', 'danger')
        return redirect(url_for('index'))

    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT filename, job_id FROM photos WHERE id = ?', (photo_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        flash('Photo not found', 'warning')
        return redirect(url_for('index'))

    filename = row['filename']
    job_id = row['job_id']

    cur.execute('SELECT job_no FROM jobs WHERE id = ?', (job_id,))
    job = cur.fetchone()
    job_no = job['job_no'] if job else None

    cur.execute('DELETE FROM photos WHERE id = ?', (photo_id,))
    conn.commit()
    conn.close()

    if job_no:
        path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(job_no), filename)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                print('could not delete photo file', e)

    flash('Photo deleted', 'success')
    return redirect(url_for('edit', job_id=job_id))

@app.route('/activity')
@role_required('superadmin', 'admin')
def activity():
    # Filters: single date and/or date range (ignoring time part)
    date = request.args.get('date', '').strip()
    from_date = request.args.get('from_date', '').strip()
    to_date = request.args.get('to_date', '').strip()

    conn = get_db()
    cur = conn.cursor()

    base_query = '''
        SELECT a.*, u.full_name
        FROM activity_log a
        LEFT JOIN users u ON a.user_id = u.id
        WHERE 1=1
    '''
    params = []

    # Single-date filter: exact match on date portion only
    if date:
        base_query += " AND substr(a.created_at, 1, 10) = ?"
        params.append(date)
    else:
        # Range filter only applies when no single date is given
        if from_date:
            base_query += " AND substr(a.created_at, 1, 10) >= ?"
            params.append(from_date)
        if to_date:
            base_query += " AND substr(a.created_at, 1, 10) <= ?"
            params.append(to_date)

    base_query += " ORDER BY a.created_at DESC LIMIT 500"

    cur.execute(base_query, params)
    rows = cur.fetchall()
    conn.close()
    return render_template('activity.html', rows=rows, date=date, from_date=from_date, to_date=to_date)

@app.route('/users')
@role_required('superadmin')
def users():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, full_name, username, role FROM users ORDER BY full_name")
    users = cur.fetchall()
    conn.close()
    return render_template('users.html', users=users)

@app.route('/users/add', methods=['GET', 'POST'])
@role_required('superadmin')
def add_user():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', '').strip()
        if not full_name or not username or not password or not role:
            flash('All fields are required', 'warning')
            return redirect(url_for('add_user'))
        pwd_hash = generate_password_hash(password)
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO users (full_name, username, password_hash, role) VALUES (?, ?, ?, ?)",
                (full_name, username, pwd_hash, role),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            flash('Username already exists', 'danger')
            conn.close()
            return redirect(url_for('add_user'))
        conn.close()
        flash('User added', 'success')
        return redirect(url_for('users'))
    return render_template('add_user.html')

@app.route('/users/delete/<int:user_id>', methods=['POST'])
@role_required('superadmin')
def delete_user(user_id):
    if user_id == session.get('user_id'):
        flash('You cannot delete your own account while logged in.', 'warning')
        return redirect(url_for('users'))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT username, full_name FROM users WHERE id = ?", (user_id,))
    u = cur.fetchone()
    if not u:
        conn.close()
        flash('User not found', 'warning')
        return redirect(url_for('users'))

    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    details = f"Deleted user {u['username']} ({u['full_name']})"
    log_action(session.get('user_id'), 'DELETE_USER', details=details)

    flash('User deleted', 'success')
    return redirect(url_for('users'))

@app.route('/tracker')
@login_required
def tracker():
    q = request.args.get('job_no', '').strip()
    conn = get_db()
    cur = conn.cursor()
    if q:
        cur.execute("SELECT * FROM jobs WHERE job_no LIKE ? ORDER BY date DESC, id DESC", (f"%{q}%",))
    else:
        cur.execute("SELECT * FROM jobs ORDER BY date DESC, id DESC")
    jobs = cur.fetchall()
    conn.close()
    return render_template('tracker.html', jobs=jobs)

@app.route('/tracker/job/<int:job_id>')
@login_required
def tracker_job_detail(job_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    job = cur.fetchone()
    if not job:
        conn.close()
        flash('Job not found', 'warning')
        return redirect(url_for('tracker'))

    cur.execute(
        '''
        SELECT h.*, u.full_name
        FROM stage_history h
        LEFT JOIN users u ON h.updated_by = u.id
        WHERE h.job_id = ?
        ORDER BY h.updated_at ASC
        ''',
        (job_id,),
    )
    history = cur.fetchall()
    conn.close()
    return render_template('tracker_detail.html', job=job, history=history)



@app.route('/tracker/update/<int:job_id>', methods=['GET', 'POST'])
@login_required
def tracker_update(job_id):
    if session.get('role') not in ('superadmin', 'admin', 'staff'):
        flash('You do not have permission to update job stages', 'danger')
        return redirect(url_for('tracker'))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    job = cur.fetchone()
    if not job:
        conn.close()
        flash('Job not found', 'warning')
        return redirect(url_for('tracker'))

    if request.method == 'POST':
        stage = request.form.get('stage', '').strip() or job['stage'] or 'PRE_DESIGN'
        pre_plate = 1 if request.form.get('pre_plate') == 'on' else 0
        pre_die = 1 if request.form.get('pre_die') == 'on' else 0
        pre_paper = 1 if request.form.get('pre_paper') == 'on' else 0

        now = datetime.datetime.now().isoformat()

        # Outsourced processing timestamps: set once when first ticked
        plate_sent_at = job['plate_sent_at']
        plate_received_at = job['plate_received_at']
        die_sent_at = job['die_sent_at']
        die_received_at = job['die_received_at']
        paper_sent_at = job['paper_sent_at']
        paper_done_at = job['paper_done_at']

        if request.form.get('plate_sent') == 'on' and not plate_sent_at:
            plate_sent_at = now
        if request.form.get('plate_received') == 'on' and not plate_received_at:
            plate_received_at = now
        if request.form.get('die_sent') == 'on' and not die_sent_at:
            die_sent_at = now
        if request.form.get('die_received') == 'on' and not die_received_at:
            die_received_at = now
        if request.form.get('paper_sent') == 'on' and not paper_sent_at:
            paper_sent_at = now
        if request.form.get('paper_done') == 'on' and not paper_done_at:
            paper_done_at = now

        cur.execute(
            "UPDATE jobs SET stage = ?, stage_updated_by = ?, stage_updated_at = ?, "
            "pre_plate = ?, pre_die = ?, pre_paper = ?, "
            "plate_sent_at = ?, plate_received_at = ?, "
            "die_sent_at = ?, die_received_at = ?, "
            "paper_sent_at = ?, paper_done_at = ? "
            "WHERE id = ?",
            (
                stage,
                session.get('user_id'),
                now,
                pre_plate,
                pre_die,
                pre_paper,
                plate_sent_at,
                plate_received_at,
                die_sent_at,
                die_received_at,
                paper_sent_at,
                paper_done_at,
                job_id,
            ),
        )

        # Stage history entry
        cur.execute(
            'INSERT INTO stage_history (job_id, stage, updated_by, updated_at, pre_plate, pre_die, pre_paper) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (job_id, stage, session.get('user_id'), now, pre_plate, pre_die, pre_paper),
        )

        conn.commit()
        conn.close()

        label = get_stage_label(stage) or stage
        details = f"Stage set to {label}; Pre-press: Plate={bool(pre_plate)}, Die={bool(pre_die)}, Paper={bool(pre_paper)}"
        log_action(session.get('user_id'), 'UPDATE_STAGE', job_id=job_id, job_no=job['job_no'], details=details)

        flash('Job stage updated', 'success')
        return redirect(url_for('tracker'))

    conn.close()
    return render_template('tracker_update.html', job=job)



@app.route('/backups')
@role_required('superadmin', 'admin', 'staff')
def backups():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT b.*, u.full_name
        FROM backup_log b
        LEFT JOIN users u ON b.created_by = u.id
        ORDER BY b.backup_date DESC, b.id DESC
        LIMIT 200
    """)
    rows = cur.fetchall()

    last = rows[0] if rows else None
    status_key = None
    days_until = None
    if last and last['next_due']:
        status_key, days_until = backup_status(last['next_due'], due_soon_days=5)

    conn.close()
    return render_template('backups.html', rows=rows, last=last, status_key=status_key, days_until=days_until)

@app.route('/backups/add', methods=['GET', 'POST'])
@role_required('superadmin', 'admin', 'staff')
def backups_add():
    if request.method == 'POST':
        backup_date = request.form.get('backup_date', '').strip()
        backup_type = request.form.get('backup_type', '').strip()
        backup_location = request.form.get('backup_location', '').strip()
        notes = request.form.get('notes', '').strip()

        if not backup_date:
            flash('Backup date is required.', 'danger')
            return redirect(url_for('backups_add'))

        next_due = add_one_month(backup_date)

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO backup_log (backup_date, next_due, backup_type, backup_location, notes, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (backup_date, next_due, backup_type, backup_location, notes, session.get('user_id'), datetime.datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()

        log_action(session.get('user_id'), 'BACKUP_ADDED', details=f"Backup on {backup_date}, next due {next_due}")
        flash('Backup entry added.', 'success')
        return redirect(url_for('backups'))

    return render_template('backup_form.html', mode='add', item=None)

@app.route('/backups/<int:backup_id>/edit', methods=['GET', 'POST'])
@role_required('superadmin', 'admin', 'staff')
def backups_edit(backup_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM backup_log WHERE id = ?', (backup_id,))
    item = cur.fetchone()
    if not item:
        conn.close()
        flash('Backup entry not found.', 'danger')
        return redirect(url_for('backups'))

    if request.method == 'POST':
        backup_date = request.form.get('backup_date', '').strip()
        backup_type = request.form.get('backup_type', '').strip()
        backup_location = request.form.get('backup_location', '').strip()
        notes = request.form.get('notes', '').strip()

        if not backup_date:
            conn.close()
            flash('Backup date is required.', 'danger')
            return redirect(url_for('backups_edit', backup_id=backup_id))

        next_due = add_one_month(backup_date)

        cur.execute(
            "UPDATE backup_log SET backup_date=?, next_due=?, backup_type=?, backup_location=?, notes=? WHERE id=?",
            (backup_date, next_due, backup_type, backup_location, notes, backup_id),
        )
        conn.commit()
        conn.close()

        log_action(session.get('user_id'), 'BACKUP_EDITED', details=f"Backup #{backup_id} updated: {backup_date}, next due {next_due}")
        flash('Backup entry updated.', 'success')
        return redirect(url_for('backups'))

    conn.close()
    return render_template('backup_form.html', mode='edit', item=item)



if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
