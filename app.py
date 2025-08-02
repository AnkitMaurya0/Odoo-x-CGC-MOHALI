import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from math import radians, cos, sin, asin, sqrt

app = Flask(__name__)
app.secret_key = 'supersecretkey'

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create upload folder if doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# -------------------- UTILITIES --------------------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def haversine_distance(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371
    return c * r

# -------------------- USER AUTH --------------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        hashed_password = generate_password_hash(password)

        conn = sqlite3.connect('civictrack.db')
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)", (name, email, hashed_password))
            conn.commit()
            flash('Account created successfully! Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email already exists. Please use a different email.', 'error')
            return redirect(url_for('signup'))
        finally:
            conn.close()
    return render_template('home.html', section='signup')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Hardcoded Admin Login
        if email == 'admin@example.com' and password == 'admin123':
            session['user_role'] = 'admin'
            session['email'] = email
            flash('Admin logged in successfully!', 'success')
            return redirect(url_for('admin_dashboard'))

        # Normal User Login
        conn = sqlite3.connect('civictrack.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, password FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[1], password):
            session['user_id'] = user[0]
            session['email'] = email
            session['user_role'] = 'user'
            flash('Logged in successfully!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid credentials. Try again.', 'error')
            return redirect(url_for('login'))

    return render_template('home.html', section='login')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('home'))

# -------------------- HOME --------------------
@app.route('/')
def home():
    return render_template('home.html')

# -------------------- REPORT ISSUE --------------------
@app.route('/report', methods=['GET', 'POST'])
def report_issue():
    if 'user_id' not in session:
        flash('Please login to report an issue.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        category = request.form.get('category')
        latitude = float(request.form.get('latitude'))
        longitude = float(request.form.get('longitude'))
        images = request.files.getlist('images')

        if not title or not description or not category:
            flash('Please fill all required fields.', 'error')
            return redirect(url_for('report_issue'))

        conn = sqlite3.connect('civictrack.db')
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO issues (user_id, title, description, category, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session['user_id'], title, description, category, latitude, longitude))
        issue_id = cursor.lastrowid

        # Save uploaded images
        for image in images[:3]:
            if image and allowed_file(image.filename):
                filename = secure_filename(image.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                image.save(filepath)
                cursor.execute("INSERT INTO images (issue_id, image_path) VALUES (?, ?)", (issue_id, filename))

        cursor.execute("INSERT INTO status_logs (issue_id, status) VALUES (?, ?)", (issue_id, 'Reported'))
        conn.commit()
        conn.close()

        flash('Issue reported successfully!', 'success')
        return redirect(url_for('all_issues'))

    return render_template('report.html')

# -------------------- MAP VIEW --------------------
@app.route('/map', methods=['GET', 'POST'])
def map_view():
    message = None
    issues = []

    if request.method == 'POST':
        user_lat = float(request.form.get('latitude'))
        user_lon = float(request.form.get('longitude'))

        conn = sqlite3.connect('civictrack.db')
        cursor = conn.cursor()
        cursor.execute('SELECT id, title, category, latitude, longitude FROM issues')
        all_issues = cursor.fetchall()
        conn.close()

        for issue in all_issues:
            dist = haversine_distance(user_lat, user_lon, issue[3], issue[4])
            if dist <= 5:
                issues.append(issue)

        if not issues:
            message = "No issues found within 5 km radius."

    return render_template('map.html', issues=issues, message=message)

# -------------------- ALL ISSUES --------------------
@app.route('/issues')
def all_issues():
    conn = sqlite3.connect('civictrack.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, title, category, status FROM issues')
    issues = cursor.fetchall()
    conn.close()
    return render_template('issues.html', issues=issues)

# -------------------- FLAG ISSUE --------------------
@app.route('/flag/<int:issue_id>', methods=['POST'])
def flag_issue(issue_id):
    conn = sqlite3.connect('civictrack.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO flags (issue_id, reason) VALUES (?, ?)', (issue_id, 'Spam'))
    conn.commit()
    conn.close()
    flash('Issue flagged successfully!', 'success')
    return redirect(url_for('all_issues'))

# -------------------- ADMIN DASHBOARD --------------------
@app.route('/admin')
def admin_dashboard():
    if session.get('user_role') != 'admin':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))

    conn = sqlite3.connect('civictrack.db')
    cursor = conn.cursor()

    # Total Issues
    cursor.execute('SELECT COUNT(*) FROM issues')
    total_issues = cursor.fetchone()[0]

    # Top Category
    cursor.execute('SELECT category, COUNT(*) FROM issues GROUP BY category ORDER BY COUNT(*) DESC LIMIT 1')
    top_category = cursor.fetchone()

    # Flagged Issues
    cursor.execute('''
        SELECT issues.id, issues.title, COUNT(flags.id) as flag_count
        FROM issues
        JOIN flags ON issues.id = flags.issue_id
        GROUP BY issues.id
        HAVING flag_count >= 1
    ''')
    flagged_issues = cursor.fetchall()

    # All Issues (ID, Title, Status)
    cursor.execute('SELECT id, title, status FROM issues')
    all_issues = cursor.fetchall()

    conn.close()

    return render_template('admin.html', total_issues=total_issues, top_category=top_category, flagged_issues=flagged_issues, all_issues=all_issues)


# -------------------- USER PROFILE --------------------
@app.route('/profile')
def profile():
    if 'user_id' not in session:
        flash('Please login to view profile.', 'error')
        return redirect(url_for('login'))

    conn = sqlite3.connect('civictrack.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, email FROM users WHERE id = ?", (session['user_id'],))
    user_info = cursor.fetchone()
    cursor.execute("SELECT id, title, category, status FROM issues WHERE user_id = ?", (session['user_id'],))
    user_issues = cursor.fetchall()
    conn.close()

    return render_template('profile.html', user=user_info, issues=user_issues)

# -------------------- ISSUE DETAIL VIEW --------------------
@app.route('/issue/<int:issue_id>')
def issue_detail(issue_id):
    conn = sqlite3.connect('civictrack.db')
    cursor = conn.cursor()

    # Fetch issue details (id, title, description, category, status, latitude, longitude)
    cursor.execute('SELECT id, title, description, category, status, latitude, longitude FROM issues WHERE id = ?', (issue_id,))
    issue = cursor.fetchone()

    if not issue:
        flash('Issue not found.', 'error')
        return redirect(url_for('home'))

    # Fetch associated images
    cursor.execute('SELECT image_path FROM images WHERE issue_id = ?', (issue_id,))
    images = cursor.fetchall()

    # Fetch status logs
    cursor.execute('SELECT status, timestamp FROM status_logs WHERE issue_id = ? ORDER BY timestamp DESC', (issue_id,))
    status_logs = cursor.fetchall()

    conn.close()

    return render_template('issue_detail.html', issue=issue, images=images, status_logs=status_logs)



# -------------------- UPDATE STATUS (Admin Only) --------------------
@app.route('/update_status_from_dashboard/<int:issue_id>', methods=['POST'])
def update_status_from_dashboard(issue_id):
    if 'user_role' not in session or session['user_role'] != 'admin':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('home'))

    new_status = request.form['status']
    conn = sqlite3.connect('civictrack.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE issues SET status = ? WHERE id = ?', (new_status, issue_id))
    cursor.execute('INSERT INTO status_logs (issue_id, status) VALUES (?, ?)', (issue_id, new_status))
    conn.commit()
    conn.close()

    flash('Status updated successfully!', 'success')
    return redirect(url_for('admin_dashboard'))



# -------------------- MAIN --------------------
if __name__ == '__main__':
    app.run(debug=True)
