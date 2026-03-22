from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from datetime import datetime, timedelta
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Optional
from functools import wraps
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import timedelta
import atexit
import os
from werkzeug.utils import secure_filename

# ────────────────────────────────────────────────
# Forms
# ────────────────────────────────────────────────
class AddUserForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    role = SelectField(
        'Role',
        choices=[('admin', 'Admin'), ('student', 'Student'),
                 ('plumber', 'Plumber'), ('cleaner', 'Cleaner'),
                 ('electrician', 'Electrician'), ('technician', 'Technician'),
                 ('pest_controller', 'Pest Controller')],
        validators=[DataRequired()]
    )
    room_number = StringField('Room Number', validators=[Optional(), Length(max=20)])
    submit = SubmitField('Create User')

# ────────────────────────────────────────────────
# App setup
# ────────────────────────────────────────────────
app = Flask(__name__)

# ──── Base directory & production-friendly paths ────
basedir = os.path.abspath(os.path.dirname(__file__))

# Create necessary folders
instance_dir = os.path.join(basedir, 'instance')
upload_dir   = os.path.join(basedir, 'static', 'uploads')
os.makedirs(instance_dir, exist_ok=True)
os.makedirs(upload_dir,   exist_ok=True)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-me-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(instance_dir, 'maintenance.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = upload_dir
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

# Email configuration (use environment variables in production!)
app.config['MAIL_SERVER']   = 'smtp.gmail.com'
app.config['MAIL_PORT']     = 587
app.config['MAIL_USE_TLS']  = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME') or 'thembelanibuthelezi64@gmail.com'
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD') or 'iuuocjnhsocusnrz'

db   = SQLAlchemy(app)
mail = Mail(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ────────────────────────────────────────────────
# Background scheduler
# ────────────────────────────────────────────────
scheduler = BackgroundScheduler()
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# ────────────────────────────────────────────────
# Notifications context processor
# ────────────────────────────────────────────────
@app.context_processor
def inject_notifications():
    if not current_user.is_authenticated:
        return {'unread_count': 0, 'has_unread': False}
    unread_count = current_user.unread_notifications_count()
    return {'unread_count': unread_count, 'has_unread': unread_count > 0}

@app.route('/notifications/mark-read/<int:notif_id>', methods=['POST'])
@login_required
def mark_read(notif_id):
    notif = Notification.query.get_or_404(notif_id)
    if notif.user_id != current_user.id:
        return jsonify({'success': False}), 403
    if not notif.is_read:
        notif.is_read = True
        db.session.commit()
    return jsonify({'success': True})

@app.route('/notifications/unread-count')
@login_required
def unread_count():
    return jsonify({'unread': current_user.unread_notifications_count()})

@app.route('/notifications')
@login_required
def notifications_all():
    notifs = current_user.notifications.order_by(Notification.created_at.desc()).all()
    return render_template('notifications_all.html', notifications=notifs)

# ────────────────────────────────────────────────
# Models
# ────────────────────────────────────────────────
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    password_hash = db.Column(db.String(200))
    role = db.Column(db.String(20))
    room_number = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def unread_notifications_count(self):
        return self.notifications.filter_by(is_read=False).count()

    def get_notifications(self, limit=12):
        return self.notifications.order_by(Notification.created_at.desc()).limit(limit).all()

class Request(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    staff_id = db.Column(db.Integer, nullable=True)
    room_number = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(50))
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default="Pending")
    photo_path = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    type = db.Column(db.String(30), default='request', nullable=False)
    related_request_id = db.Column(db.Integer, db.ForeignKey('request.id'), nullable=True)
    related_object_id = db.Column(db.Integer, nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('notifications', lazy='dynamic', cascade="all, delete-orphan"))
    request = db.relationship('Request', backref='notifications', lazy=True)

def check_and_create_reminder_notifications():
    with app.app_context():
        overdue = Request.query.filter(
            Request.status == "Pending",
            Request.created_at <= datetime.utcnow() - timedelta(hours=48)
        ).all()

        for req in overdue:
            student = User.query.get(req.user_id)
            if not student: continue

            recent_reminder = Notification.query.filter(
                Notification.user_id == student.id,
                Notification.type == 'reminder',
                Notification.related_request_id == req.id,
                Notification.created_at >= datetime.utcnow() - timedelta(hours=24)
            ).first()

            if recent_reminder: continue

            message = f"Reminder: Your maintenance request #{req.id} (Room {req.room_number}) is still pending for over 2 days."
            notif = Notification(
                user_id=student.id,
                message=message,
                type='reminder',
                related_request_id=req.id
            )
            db.session.add(notif)
            db.session.commit()

scheduler.add_job(
    func=check_and_create_reminder_notifications,
    trigger=IntervalTrigger(minutes=1),
    id='maintenance_reminders',
    replace_existing=True
)

from apscheduler.triggers.cron import CronTrigger

# Add this after your existing scheduler jobs
scheduler.add_job(
    func=send_weekly_digest,
    trigger=CronTrigger(day_of_week='mon', hour=8, minute=0),
    id='weekly_email_digest',
    replace_existing=True
)
print("✓ Weekly email digest scheduled for every Monday at 8:00 AM")

# ────────────────────────────────────────────────
# Decorators
# ────────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in.", "warning")
            return redirect(url_for('login'))
        if current_user.role != 'admin':
            flash("Admin access only.", "danger")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def staff_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in.", "warning")
            return redirect(url_for('login'))
        if current_user.role in ['admin', 'student']:
            flash("Staff access only.", "danger")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

# ────────────────────────────────────────────────
# Template filters
# ────────────────────────────────────────────────
@app.template_filter('format_datetime')
def format_datetime(value, format='%Y-%m-%d %H:%M'):
    if value is None:
        value = datetime.now()
    return value.strftime(format)

# ────────────────────────────────────────────────
# Email helpers (unchanged)
# ────────────────────────────────────────────────
def get_admin_emails():
    admins = User.query.filter(User.role.ilike('%admin%')).all()
    return [a.email for a in admins if a.email]

def notify_admins_new_request(new_request):
    admin_emails = get_admin_emails()
    if not admin_emails: return

    student = current_user
    subject = f"New Maintenance Request #{new_request.id} — Room {new_request.room_number}"

    html_content = render_template(
        'emails/new_request_notification.html',
        request_id=new_request.id,
        submitted_by_name=student.full_name,
        submitted_by_email=student.email,
        room_number=new_request.room_number,
        category=new_request.category,
        priority=new_request.priority,
        description=new_request.description,
        status=new_request.status,
        created_at=new_request.created_at.strftime('%Y-%m-%d %H:%M UTC'),
        has_photo=bool(new_request.photo_path),
        review_url="http://127.0.0.1:5000/requests"
    )

    try:
        msg = Message(subject, sender=app.config['MAIL_USERNAME'], recipients=admin_emails,
                      body="New maintenance request submitted.", html=html_content)

        if new_request.photo_path:
            full_path = os.path.join('static', new_request.photo_path)
            if os.path.exists(full_path):
                with open(full_path, 'rb') as f:
                    data = f.read()
                ext = new_request.photo_path.rsplit('.', 1)[-1].lower()
                mime = f"image/{'jpeg' if ext in ('jpg','jpeg') else ext}"
                msg.attach(filename=f"photo.{ext}", content_type=mime, data=data)

        mail.send(msg)
        print(f"Notification sent for request #{new_request.id}")
    except Exception as e:
        print(f"Email failed: {e}")

def create_notification(user_id, message, notif_type='request', related_request_id=None):
    notif = Notification(
        user_id=user_id,
        message=message,
        type=notif_type,
        related_request_id=related_request_id
    )
    db.session.add(notif)

def notify_user_email(user, subject, html_template, **kwargs):
    try:
        html = render_template(html_template, **kwargs)
        msg = Message(subject, sender=app.config['MAIL_USERNAME'], recipients=[user.email],
                      body="Automated update.", html=html)
        mail.send(msg)
    except Exception as e:
        print(f"→ Email failed for {user.email}: {e}")

# ────────────────────────────────────────────────
# Login / Logout
# ────────────────────────────────────────────────
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Email or password incorrect.", "danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ────────────────────────────────────────────────
# Admin – Register user
# ────────────────────────────────────────────────
@app.route('/admin/register', methods=['GET', 'POST'])
@login_required
@admin_required
def register():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        role = request.form.get('role', '').strip().lower()
        room_number = request.form.get('room_number', '').strip()

        if not all([full_name, email, password, role]):
            flash('Required fields missing.', 'danger')
            return redirect(url_for('register'))

        if role == 'student' and not room_number:
            flash('Room number required for students.', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('register'))

        new_user = User(
            full_name=full_name,
            email=email,
            password_hash=generate_password_hash(password),
            role=role,
            room_number=room_number if role == 'student' else None
        )
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('User created successfully!', 'success')
            return redirect(url_for('users'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')

    return render_template('admin/register.html')

# ────────────────────────────────────────────────
# Dashboard (already good – kept as is)
# ────────────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    notifications = current_user.get_notifications(limit=12)
    unread_count = current_user.unread_notifications_count()
    role = current_user.role.lower()

    if role == "admin":
        total_requests = Request.query.count()
        pending_requests = Request.query.filter_by(status="Pending").count()
        in_progress = Request.query.filter_by(status="In Progress").count()
        completed = Request.query.filter_by(status="Completed").count()
        recent_requests = Request.query.order_by(Request.created_at.desc()).limit(10).all()
        categories = {cat: Request.query.filter_by(category=cat).count()
                      for cat in ['plumber', 'cleaner', 'electrician', 'technician', 'pest_controller']}
        return render_template("admin/dashboard.html", **locals())

    elif role == "student":
        requests = Request.query.filter_by(user_id=current_user.id)\
                               .order_by(Request.created_at.desc()).all()
        pending_count = Request.query.filter_by(user_id=current_user.id, status="Pending").count()
        in_progress_count = Request.query.filter_by(user_id=current_user.id, status="In Progress").count()
        completed_count = Request.query.filter_by(user_id=current_user.id, status="Completed").count()
        return render_template("student/dashboard.html", **locals())

    elif role in ['technician', 'plumber', 'cleaner', 'electrician', 'pest_controller']:
        requests = Request.query.filter_by(staff_id=current_user.id)\
                               .order_by(Request.created_at.desc()).all()
        pending_count = Request.query.filter_by(staff_id=current_user.id, status="Pending").count()
        in_progress_count = Request.query.filter_by(staff_id=current_user.id, status="In Progress").count()
        completed_count = Request.query.filter_by(staff_id=current_user.id, status="Completed").count()
        role_display = current_user.role.replace('_', ' ').title()
        return render_template("staff/dashboard.html", **locals())

    else:
        flash("Unknown or invalid user role", "danger")
        return redirect(url_for("login"))

# ────────────────────────────────────────────────
# FIXED: Assignment (now works for all categories)
# ────────────────────────────────────────────────
@app.route("/assign/<int:req_id>", methods=["POST"])
@login_required
@admin_required
def assign(req_id):
    req = Request.query.get_or_404(req_id)

    if req.status == "Completed":
        flash("Cannot assign to completed request.", "warning")
        return redirect(url_for("requests"))

    staff_id_str = request.form.get("staff_id")
    if not staff_id_str:
        flash("No staff member selected.", "danger")
        return redirect(url_for("requests"))

    try:
        staff_id = int(staff_id_str)
    except ValueError:
        flash("Invalid staff selection.", "danger")
        return redirect(url_for("requests"))

    staff = User.query.get(staff_id)
    if not staff:
        flash("Selected user not found.", "danger")
        return redirect(url_for("requests"))

    if staff.role.lower() != req.category.lower():
        flash(f"Cannot assign: user is {staff.role}, request requires {req.category}", "danger")
        return redirect(url_for("requests"))

    old_staff_id = req.staff_id
    req.staff_id = staff.id
    req.status = "Assigned"

    student = User.query.get(req.user_id)
    if student:
        create_notification(
            student.id,
            f"Your request #{req.id} ({req.room_number}) assigned to {staff.full_name} ({staff.role}).",
            'assignment', req.id
        )

    create_notification(
        staff.id,
        f"Assigned request #{req.id} – {req.room_number} – {req.category} – Priority: {req.priority}",
        'assignment', req.id
    )

    db.session.commit()

    action = "Re-assigned" if old_staff_id else "Assigned"
    flash(f"{action} to {staff.full_name} ({staff.role})", "success")
    return redirect(url_for("requests"))

# ────────────────────────────────────────────────
# FIXED: Status update – supports all staff roles
# ────────────────────────────────────────────────
@app.route("/update_status/<int:req_id>", methods=["POST"])
@login_required
def update_status(req_id):
    allowed_roles = {'technician', 'plumber', 'cleaner', 'electrician', 'pest_controller'}
    if current_user.role.lower() not in allowed_roles:
        flash("Only maintenance staff can update status", "danger")
        return redirect(url_for("dashboard"))

    req = Request.query.get_or_404(req_id)

    if req.staff_id != current_user.id:
        flash("This task is not assigned to you", "danger")
        return redirect(url_for("dashboard"))

    new_status = request.form.get("status")
    allowed = {"Assigned", "In Progress", "Completed"}

    if new_status in allowed:
        if req.status == "Completed" and new_status != "Completed":
            flash("Completed tasks cannot be changed back", "warning")
        else:
            req.status = new_status
            db.session.commit()
            flash(f"Status updated to {new_status}", "success")
    else:
        flash("Invalid status", "danger")

    return redirect(url_for("staff_assigned_work"))

# ────────────────────────────────────────────────
# The rest of your application (unchanged routes)
# ────────────────────────────────────────────────

@app.route('/new_request', methods=['GET', 'POST'])
@login_required
def new_request():
    if current_user.role != "student":
        flash("Only students can submit requests.", "danger")
        return redirect(url_for("my_requests"))

    if request.method == 'POST':
        room_number = request.form.get('room_number', current_user.room_number)
        category = request.form.get('category')
        priority = request.form.get('priority')
        description = request.form.get('description')

        photo_path = None
        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                photo_path = f"uploads/{filename}"

        if not all([room_number, category, priority, description]):
            flash("Please fill in all required fields", "danger")
            return redirect(url_for('new_request'))

        new_req = Request(
            user_id=current_user.id,
            room_number=room_number.strip(),
            category=category,
            priority=priority,
            description=description.strip(),
            photo_path=photo_path
        )

        try:
            db.session.add(new_req)
            db.session.commit()
            notify_admins_new_request(new_req)
            flash("Maintenance request submitted successfully!", "success")
            return redirect(url_for('my_requests'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error saving request: {str(e)}", "danger")

    return render_template('student/new_request.html', default_room=current_user.room_number)

@app.route('/my-requests')
@login_required
def my_requests():
    if current_user.role != "student":
        flash("Unauthorized access.", "danger")
        return redirect(url_for("dashboard"))

    page = request.args.get('page', 1, type=int)
    per_page = 10

    pagination = Request.query.filter_by(user_id=current_user.id)\
                              .order_by(Request.created_at.desc())\
                              .paginate(page=page, per_page=per_page)

    requests = pagination.items
    for req in requests:
        if req.staff_id:
            staff = User.query.get(req.staff_id)
            req.staff_name = staff.full_name if staff else "Unknown"

    return render_template('student/my_requests.html', requests=requests, pagination=pagination)

@app.route("/requests")
@login_required
@admin_required
def requests():
    page = request.args.get('page', 1, type=int)

    paginated_requests = Request.query.order_by(Request.created_at.desc()).paginate(
        page=page, per_page=10, error_out=False
    )

    staff_by_category = {}
    staff_roles = ['plumber', 'cleaner', 'electrician', 'technician', 'pest_controller']
    for role in staff_roles:
        staff_by_category[role] = User.query.filter_by(role=role).all()

    for req in paginated_requests.items:
        student = User.query.get(req.user_id)
        req.student_name = student.full_name if student else "Unknown Student"
        req.student_room = student.room_number if student else "Unknown"

        if req.staff_id:
            staff = User.query.get(req.staff_id)
            req.staff_name = staff.full_name if staff else "Unknown"
        else:
            req.staff_name = "Not assigned"

    return render_template("admin/requests.html",
                          requests=paginated_requests,
                          staff_by_category=staff_by_category,
                          User=User)

@app.route("/users")
@login_required
@admin_required
def users():
    page = request.args.get('page', 1, type=int)
    users = User.query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=10, error_out=False
    )
    return render_template("admin/users.html", users=users)

@app.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Cannot edit your own account here.", "warning")
        return redirect(url_for('users'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        role = request.form.get('role', '').strip().lower()
        room_number = request.form.get('room_number', '').strip()
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not full_name or not role:
            flash("Full name and role required.", "danger")
            return redirect(url_for('edit_user', user_id=user_id))

        if role == 'student' and not room_number:
            flash("Room number required for students.", "danger")
            return redirect(url_for('edit_user', user_id=user_id))

        user.full_name = full_name
        user.role = role
        user.room_number = room_number if role == 'student' else None

        if new_password and confirm_password:
            if new_password == confirm_password:
                user.password_hash = generate_password_hash(new_password)
            else:
                flash("Passwords do not match.", "danger")
                return redirect(url_for('edit_user', user_id=user_id))

        db.session.commit()
        flash(f"User {user.full_name} updated.", "success")
        return redirect(url_for('users'))

    return render_template('admin/edit_user.html', user=user)

@app.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Cannot delete your own account.", "danger")
        return redirect(url_for('users'))

    if user.role == 'admin' and User.query.filter_by(role='admin').count() <= 1:
        flash("Cannot delete the last admin.", "danger")
        return redirect(url_for('users'))

    db.session.delete(user)
    db.session.commit()
    flash(f"User {user.full_name} deleted.", "success")
    return redirect(url_for('users'))

@app.route("/staff/assigned-work")
@login_required
def staff_assigned_work():
    if current_user.role in ['admin', 'student']:
        flash("Access denied", "danger")
        return redirect(url_for("dashboard"))

    requests = Request.query.filter_by(staff_id=current_user.id)\
                           .order_by(Request.created_at.desc()).all()

    for req in requests:
        student = User.query.get(req.user_id)
        req.student_name = student.full_name if student else "Unknown"
        req.student_room = student.room_number if student else "Unknown"

    return render_template("staff/assigned_work.html",
                          requests=requests,
                          role_display=current_user.role.replace('_', ' ').title(),
                          current_user=current_user)

@app.route('/requests/<int:request_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_request(request_id):
    if current_user.role != "student":
        flash("Only students can edit requests.", "danger")
        return redirect(url_for("dashboard"))

    req = Request.query.get_or_404(request_id)
    if req.user_id != current_user.id:
        flash("You can only edit your own requests.", "danger")
        return redirect(url_for("my_requests"))

    if req.status in ["Assigned", "In Progress", "Completed"]:
        flash("Cannot edit assigned/in-progress/completed requests.", "warning")
        return redirect(url_for("my_requests"))

    if request.method == "POST":
        room_number = request.form.get("room_number", "").strip()
        category = request.form.get("category", "").strip()
        priority = request.form.get("priority", "").strip()
        description = request.form.get("description", "").strip()

        if not all([room_number, category, priority, description]):
            flash("All fields required.", "danger")
            return redirect(url_for("edit_request", request_id=request_id))

        if 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename and allowed_file(file.filename):
                if req.photo_path:
                    old_path = os.path.join('static', req.photo_path)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                req.photo_path = f"uploads/{filename}"

        req.room_number = room_number
        req.category = category
        req.priority = priority
        req.description = description

        try:
            db.session.commit()
            flash("Request updated.", "success")
            return redirect(url_for("my_requests"))
        except Exception as e:
            db.session.rollback()
            flash(f"Update failed: {str(e)}", "danger")

    return render_template("student/edit_request.html", request=req)

@app.route('/requests/<int:request_id>/delete', methods=['POST'])
@login_required
def delete_request(request_id):
    if current_user.role != "student":
        flash("Only students can delete requests.", "danger")
        return redirect(url_for("dashboard"))

    req = Request.query.get_or_404(request_id)
    if req.user_id != current_user.id:
        flash("Can only delete own requests.", "danger")
        return redirect(url_for("my_requests"))

    if req.status in ["Assigned", "In Progress", "Completed"]:
        flash("Cannot delete assigned/in-progress/completed requests.", "warning")
        return redirect(url_for("my_requests"))

    if req.photo_path:
        photo_file = os.path.join('static', req.photo_path)
        if os.path.exists(photo_file):
            os.remove(photo_file)

    try:
        db.session.delete(req)
        db.session.commit()
        flash("Request deleted.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Delete failed: {str(e)}", "danger")

    return redirect(url_for("my_requests"))

@app.route('/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    form = AddUserForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data.lower()).first():
            flash('Email already registered.', 'danger')
            return render_template('admin/add_user.html', form=form)

        if form.role.data == 'student' and not form.room_number.data:
            flash('Room number required for students.', 'danger')
            return render_template('admin/add_user.html', form=form)

        user = User(
            full_name=form.full_name.data.strip(),
            email=form.email.data.lower().strip(),
            password_hash=generate_password_hash(form.password.data),
            role=form.role.data,
            room_number=form.room_number.data if form.role.data == 'student' else None
        )
        db.session.add(user)
        db.session.commit()
        flash('User created successfully!', 'success')
        return redirect(url_for('users'))

    return render_template('admin/add_user.html', form=form)

def send_email(to, subject, body):
    msg = Message(subject, sender=app.config['MAIL_USERNAME'], recipients=[to])
    msg.body = body
    mail.send(msg)



@app.route("/notify/<int:req_id>")
@login_required
def notify(req_id):
    req = Request.query.get_or_404(req_id)
    user = User.query.get(req.user_id)
    send_email(user.email, "Maintenance Update",
               f"Your request #{req.id} status is {req.status}")
    flash("Email notification sent")
    return redirect(url_for("dashboard"))

@app.route('/view-photo/<int:request_id>')
@login_required
def view_photo(request_id):
    req = Request.query.get_or_404(request_id)

    if current_user.role == 'student' and req.user_id != current_user.id:
        flash("Access denied", "danger")
        return redirect(url_for('dashboard'))

    if current_user.role not in ['admin', 'student'] and req.staff_id != current_user.id:
        flash("Access denied", "danger")
        return redirect(url_for('dashboard'))

    if not req.photo_path:
        flash("No photo available", "warning")
        return redirect(request.referrer or url_for('dashboard'))

    return render_template('view_photo.html', request=req)
#______________________________________
#NTOMBI
#______________________________________

# Add this after your existing send_email function

def send_weekly_digest():
    """Send weekly report to all admins every Monday at 8am"""
    with app.app_context():
        # Calculate current week (Monday to Sunday)
        today = datetime.now().date()
        start_of_week = today - timedelta(days=today.weekday())  # Monday
        end_of_week = start_of_week + timedelta(days=6)  # Sunday
        
        # Get all requests from this week
        weekly_requests = Request.query.filter(
            Request.created_at >= start_of_week,
            Request.created_at <= end_of_week + timedelta(days=1)
        ).all()
        
        # Calculate stats
        total = len(weekly_requests)
        completed = len([r for r in weekly_requests if r.status == 'Completed'])
        pending = len([r for r in weekly_requests if r.status == 'Pending'])
        in_progress = len([r for r in weekly_requests if r.status == 'In Progress'])
        
        # Calculate completion rate
        completion_rate = round((completed / total * 100) if total > 0 else 0)
        
        # Get top issues
        categories = {}
        for req in weekly_requests:
            categories[req.category] = categories.get(req.category, 0) + 1
        top_issue = max(categories.items(), key=lambda x: x[1]) if categories else ("None", 0)
        
        # Get priority breakdown
        priorities = {'Emergency': 0, 'High': 0, 'Medium': 0, 'Low': 0}
        for req in weekly_requests:
            if req.priority in priorities:
                priorities[req.priority] += 1
        
        # Prepare email content
        subject = f"Weekly Maintenance Report - {start_of_week.strftime('%b %d')} to {end_of_week.strftime('%b %d, %Y')}"
        
        # Create HTML email
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background: #f4f7fa; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 12px; overflow: hidden; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }}
                .content {{ padding: 30px; }}
                .stats {{ display: flex; gap: 15px; margin: 20px 0; }}
                .stat-card {{ flex: 1; background: #f8f9fa; padding: 15px; border-radius: 10px; text-align: center; }}
                .stat-number {{ font-size: 32px; font-weight: bold; color: #667eea; }}
                .stat-label {{ color: #6c757d; font-size: 12px; }}
                .priority-box {{ display: inline-block; padding: 5px 10px; border-radius: 20px; font-size: 12px; margin: 3px; }}
                .priority-Emergency {{ background: #dc3545; color: white; }}
                .priority-High {{ background: #fd7e14; color: white; }}
                .priority-Medium {{ background: #ffc107; color: black; }}
                .priority-Low {{ background: #28a745; color: white; }}
                .footer {{ background: #f8f9fa; padding: 20px; text-align: center; font-size: 12px; color: #6c757d; }}
                .btn {{ display: inline-block; background: #667eea; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>📊 Weekly Maintenance Report</h2>
                    <p>{start_of_week.strftime('%B %d, %Y')} - {end_of_week.strftime('%B %d, %Y')}</p>
                </div>
                
                <div class="content">
                    <div class="stats">
                        <div class="stat-card">
                            <div class="stat-number">{total}</div>
                            <div class="stat-label">Total Requests</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number">{completed}</div>
                            <div class="stat-label">Completed</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number">{pending}</div>
                            <div class="stat-label">Pending</div>
                        </div>
                    </div>
                    
                    <div class="stats">
                        <div class="stat-card">
                            <div class="stat-number">{in_progress}</div>
                            <div class="stat-label">In Progress</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number">{completion_rate}%</div>
                            <div class="stat-label">Completion Rate</div>
                        </div>
                    </div>
                    
                    <div style="margin: 20px 0; padding: 15px; background: #f8f9fa; border-radius: 10px;">
                        <strong>🔥 Top Issue This Week:</strong> {top_issue[0].title()} ({top_issue[1]} requests)
                    </div>
                    
                    <div style="margin: 20px 0;">
                        <strong>⚡ Priority Breakdown:</strong><br>
                        <div style="margin-top: 10px;">
                            <span class="priority-box priority-Emergency">Emergency: {priorities['Emergency']}</span>
                            <span class="priority-box priority-High">High: {priorities['High']}</span>
                            <span class="priority-box priority-Medium">Medium: {priorities['Medium']}</span>
                            <span class="priority-box priority-Low">Low: {priorities['Low']}</span>
                        </div>
                    </div>
                    
                    <div style="text-align: center;">
                        <a href="http://127.0.0.1:5000/admin/weekly-report" class="btn">View Full Report →</a>
                    </div>
                </div>
                
                <div class="footer">
                    <p>This is an automated weekly report from Residence Maintenance System.</p>
                    <p>Durban University of Technology</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Get all admin emails
        admins = User.query.filter_by(role='admin').all()
        
        if not admins:
            print("No admin users found to send weekly digest")
            return
        
        # Send email to each admin
        for admin in admins:
            try:
                msg = Message(
                    subject, 
                    sender=app.config['MAIL_USERNAME'], 
                    recipients=[admin.email],
                    html=html_content
                )
                mail.send(msg)
                print(f"Weekly digest sent to {admin.email}")
            except Exception as e:
                print(f"Failed to send to {admin.email}: {e}")
        
        print(f"Weekly digest sent to {len(admins)} admin(s)")



# ────────────────────────────────────────────────
# Run application
# ────────────────────────────────────────────────
# ────────────────────────────────────────────────
# Weekly Report Routes
# ────────────────────────────────────────────────

@app.route('/admin/weekly-report')
@login_required
@admin_required
def weekly_report():
    # Get week offset (0 = current week, -1 = last week, 1 = next week)
    week_offset = request.args.get('week_offset', 0, type=int)
    
    # Calculate week start (Monday) and end (Sunday)
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday())  # Monday
    start_of_week += timedelta(weeks=week_offset)
    end_of_week = start_of_week + timedelta(days=6)
    
    # Get all requests in this week
    weekly_requests = Request.query.filter(
        Request.created_at >= start_of_week,
        Request.created_at <= end_of_week + timedelta(days=1)
    ).all()
    
    # Get last week's requests for comparison
    last_week_start = start_of_week - timedelta(weeks=1)
    last_week_end = end_of_week - timedelta(weeks=1)
    last_week_requests = Request.query.filter(
        Request.created_at >= last_week_start,
        Request.created_at <= last_week_end + timedelta(days=1)
    ).all()
    
    # Weekly stats
    weekly_stats = {
        'total': len(weekly_requests),
        'completed': len([r for r in weekly_requests if r.status == 'Completed']),
        'pending': len([r for r in weekly_requests if r.status == 'Pending']),
        'in_progress': len([r for r in weekly_requests if r.status == 'In Progress']),
        'assigned': len([r for r in weekly_requests if r.status == 'Assigned']),
        'completion_rate': 0,
        'change': 0,
        'priorities': [],
        'top_issues': [],
        'avg_response_time': 'N/A',
        'avg_completion_time': 'N/A'
    }
    
    # Calculate completion rate
    if weekly_stats['total'] > 0:
        weekly_stats['completion_rate'] = round((weekly_stats['completed'] / weekly_stats['total']) * 100)
    
    # Calculate change from last week
    last_week_total = len(last_week_requests)
    if last_week_total > 0:
        weekly_stats['change'] = round(((weekly_stats['total'] - last_week_total) / last_week_total) * 100)
    
    # Priority breakdown
    priorities = {'Emergency': 0, 'High': 0, 'Medium': 0, 'Low': 0}
    for req in weekly_requests:
        if req.priority in priorities:
            priorities[req.priority] += 1
    
    weekly_stats['priorities'] = [
        {'name': k, 'count': v, 'percentage': round((v / weekly_stats['total'] * 100) if weekly_stats['total'] > 0 else 0)}
        for k, v in priorities.items() if v > 0
    ]
    
    # Category breakdown
    categories = {}
    for req in weekly_requests:
        categories[req.category] = categories.get(req.category, 0) + 1
    weekly_stats['top_issues'] = [{'category': k, 'count': v} for k, v in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]]
    
    # Week days data
    week_days = []
    daily_requests = []
    daily_completed = []
    week_labels = []
    
    for i in range(7):
        day_date = start_of_week + timedelta(days=i)
        day_requests = [r for r in weekly_requests if r.created_at.date() == day_date]
        day_completed = len([r for r in day_requests if r.status == 'Completed'])
        
        week_days.append({
            'name': day_date.strftime('%A'),
            'date': day_date,
            'requests': len(day_requests),
            'completed': day_completed,
            'pending': len([r for r in day_requests if r.status == 'Pending'])
        })
        daily_requests.append(len(day_requests))
        daily_completed.append(day_completed)
        week_labels.append(day_date.strftime('%a %d'))
    
    # Category data for pie chart
    category_labels = list(categories.keys())
    category_data = list(categories.values())
    
    # Priority data
    priority_labels = list(priorities.keys())
    priority_data = list(priorities.values())
    
    # Add student names to requests
    for req in weekly_requests:
        student = User.query.get(req.user_id)
        req.student_name = student.full_name if student else 'Unknown'
    
    return render_template('admin/weekly_report.html',
                         weekly_stats=weekly_stats,
                         weekly_requests=weekly_requests,
                         week_days=week_days,
                         daily_requests=daily_requests,
                         daily_completed=daily_completed,
                         week_labels=week_labels,
                         category_labels=category_labels,
                         category_data=category_data,
                         priority_labels=priority_labels,
                         priority_data=priority_data,
                         week_start=start_of_week,
                         week_end=end_of_week,
                         week_offset=week_offset)


@app.route('/admin/export-weekly-report')
@login_required
@admin_required
def export_weekly_report():
    # Get current week data
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    
    weekly_requests = Request.query.filter(
        Request.created_at >= start_of_week,
        Request.created_at <= end_of_week + timedelta(days=1)
    ).all()
    
    # Generate CSV
    import csv
    from io import StringIO
    
    output = StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['ID', 'Room', 'Category', 'Priority', 'Status', 'Description', 'Created At'])
    
    for req in weekly_requests:
        writer.writerow([
            req.id, req.room_number, req.category, req.priority, 
            req.status, req.description, req.created_at.strftime('%Y-%m-%d %H:%M')
        ])
    
    # Create response
    from flask import make_response
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=weekly_report_{start_of_week.strftime("%Y%m%d")}_{end_of_week.strftime("%Y%m%d")}.csv'
    response.headers['Content-Type'] = 'text/csv'
    
    return response
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        default_users = [
            ("Admin User", "admin@gmail.com", "admin123", "admin", None),
            ("Student User", "student@gmail.com", "student123", "student", "101A"),
            ("Plumber User", "plumber@gmail.com", "plumber123", "plumber", None),
            ("Cleaner User", "cleaner@gmail.com", "cleaner123", "cleaner", None),
            ("Electrician User", "electrician@gmail.com", "electrician123", "electrician", None),
            ("Technician User", "tech@gmail.com", "tech123", "technician", None),
            ("Pest Controller User", "pest@gmail.com", "pest123", "pest_controller", None)
        ]

        for name, email, pw, role, room in default_users:
            if not User.query.filter_by(email=email).first():
                user = User(
                    full_name=name,
                    email=email,
                    password_hash=generate_password_hash(pw),
                    role=role,
                    room_number=room
                )
                db.session.add(user)

        db.session.commit()

        # ============================================
        # ADDING  SAMPLE MAINTENANCE REQUESTS (for weekly report)
        # ============================================
        
        student = User.query.filter_by(email="student@gmail.com").first()
        
        if student and Request.query.count() == 0:
            # Create sample requests from this week
            from datetime import timedelta
            today = datetime.now().date()
            start_of_week = today - timedelta(days=today.weekday())
            
            sample_requests = [
                Request(
                    user_id=student.id,
                    room_number="101A",
                    category="plumber",
                    description="Leaking faucet in bathroom",
                    priority="Medium",
                    status="Completed",
                    created_at=datetime(start_of_week.year, start_of_week.month, start_of_week.day, 10, 30)
                ),
                Request(
                    user_id=student.id,
                    room_number="101A",
                    category="electrician",
                    description="Light flickering in bedroom",
                    priority="High",
                    status="In Progress",
                    created_at=datetime(start_of_week.year, start_of_week.month, start_of_week.day + 1, 14, 15)
                ),
                Request(
                    user_id=student.id,
                    room_number="101A",
                    category="cleaner",
                    description="Mold on bathroom ceiling",
                    priority="High",
                    status="Pending",
                    created_at=datetime(start_of_week.year, start_of_week.month, start_of_week.day + 2, 9, 45)
                ),
                Request(
                    user_id=student.id,
                    room_number="101A",
                    category="plumber",
                    description="Toilet not flushing properly",
                    priority="Emergency",
                    status="Assigned",
                    created_at=datetime(start_of_week.year, start_of_week.month, start_of_week.day + 3, 16, 20)
                ),
                Request(
                    user_id=student.id,
                    room_number="101A",
                    category="technician",
                    description="Window handle broken",
                    priority="Medium",
                    status="Pending",
                    created_at=datetime(start_of_week.year, start_of_week.month, start_of_week.day + 4, 11, 0)
                ),
                Request(
                    user_id=student.id,
                    room_number="101A",
                    category="electrician",
                    description="Power outlet not working",
                    priority="Emergency",
                    status="Assigned",
                    created_at=datetime(start_of_week.year, start_of_week.month, start_of_week.day + 5, 8, 30)
                ),
            ]
            
            for req in sample_requests:
                db.session.add(req)
            
            db.session.commit()
            print("✅ Sample requests added for weekly report!")

    app.run(debug=True)