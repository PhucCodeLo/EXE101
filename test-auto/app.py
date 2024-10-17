from flask import Flask, render_template, redirect, url_for, request, session, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from datetime import timezone as dt_timezone
from datetime import datetime, timedelta
import pytz
import random
import pandas as pd
from io import BytesIO

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SECRET_KEY'] = 'your_secret_key'

# Configuration for the first database: users.db
app.config['SQLALCHEMY_BINDS'] = {
    'users': 'sqlite:///users.db',
    'schedules': 'sqlite:///schedule.db'
}

db = SQLAlchemy(app)

# Define the User model for the 'users' database
class User(db.Model):
    __bind_key__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)  # Store plain text password
    role = db.Column(db.String(20), nullable=False)
    full_name = db.Column(db.String(100))
    phone_number = db.Column(db.String(20))
    dob = db.Column(db.String(20))
    current_address = db.Column(db.String(200))
    gmail = db.Column(db.String(100))

    def __repr__(self):
        return f'<User {self.username}>'

# Define the Schedule model for the 'schedule' database
class Schedule(db.Model):
    __bind_key__ = 'schedules'
    __tablename__ = 'schedules'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False)
    monday = db.Column(db.String(50), nullable=True)
    tuesday = db.Column(db.String(50), nullable=True)
    wednesday = db.Column(db.String(50), nullable=True)
    thursday = db.Column(db.String(50), nullable=True)
    friday = db.Column(db.String(50), nullable=True)
    saturday = db.Column(db.String(50), nullable=True)
    sunday = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Schedule {self.username} - {self.created_at}>'

@app.route('/init_db')
def init_db():
    db.create_all(bind='users')  # Create the users table in users.db
    db.create_all(bind='schedules')  # Create the schedules table in schedule.db
    return 'Databases initialized!'

shifts = {
    'morning': [(7, 12), (8, 12), (7, 15)],
    'afternoon': [(12, 18), (13, 18), (15, 22)],
    'evening': [(18, 22), (19, 22)],
}

# Define the scheduling logic function
def generate_schedule_for_employee(busy_schedules):
    assigned_shifts = {}
    for day in range(7):  # 0=Monday, 6=Sunday
        if busy_schedules.get(day) == "OFF":
            assigned_shifts[day] = 'OFF'
        else:
            available_shifts = []
            busy_time = busy_schedules.get(day)
            for shift_type, timings in shifts.items():
                for start, end in timings:
                    if not busy_time:
                        available_shifts.append(f'{shift_type} ({start}-{end})')
                    else:
                        try:
                            busy_start, busy_end = map(int, busy_time.split('-'))
                            # Check for overlap between the shift and the busy time
                            if not (start < busy_end and end > busy_start):
                                available_shifts.append(f'{shift_type} ({start}-{end})')
                        except ValueError:
                            continue

            assigned_shifts[day] = random.choice(available_shifts) if available_shifts else 'No available shifts'
    return assigned_shifts


@app.route('/preview_schedule', methods=['POST'])
def preview_schedule():
    if 'username' not in session or session.get('role') != 'Manager':
        flash('You must be logged in as a manager to view this page.')
        return redirect(url_for('login'))

    selected_year = request.form.get('year')
    selected_week = request.form.get('week')
    selected_start_date = datetime.strptime(selected_week, "%Y-%m-%d")
    selected_end_date = selected_start_date + timedelta(days=6)

    # Get schedules based on selected week
    schedules = Schedule.query.filter(
        Schedule.created_at >= selected_start_date,
        Schedule.created_at <= selected_end_date
    ).all()

    # Prepare data for preview with auto-scheduling logic
    schedule_data = []
    for schedule in schedules:
        user = User.query.filter_by(username=schedule.username).first()
        full_name = user.full_name if user else schedule.username
        busy_schedules = {
            0: schedule.monday,
            1: schedule.tuesday,
            2: schedule.wednesday,
            3: schedule.thursday,
            4: schedule.friday,
            5: schedule.saturday,
            6: schedule.sunday
        }
        assigned_shifts = generate_schedule_for_employee(busy_schedules)
        schedule_data.append({
            'full_name': full_name,
            'assigned_shifts': assigned_shifts,
            'created_at': schedule.created_at.strftime('%Y-%m-%d')
        })

    return render_template('preview_schedule.html', schedules=schedule_data, selected_year=selected_year, selected_week=selected_week)

@app.route('/export_excel', methods=['POST'])
def export_excel():
    selected_year = request.form.get('year')
    selected_week = request.form.get('week')
    selected_start_date = datetime.strptime(selected_week, "%Y-%m-%d")
    selected_end_date = selected_start_date + timedelta(days=6)

    # Query the schedules
    schedules = Schedule.query.filter(
        Schedule.created_at >= selected_start_date,
        Schedule.created_at <= selected_end_date
    ).all()

    # Prepare the data for export
    data = []
    for schedule in schedules:
        user = User.query.filter_by(username=schedule.username).first()
        full_name = user.full_name if user else schedule.username
        busy_schedules = {
            0: schedule.monday,
            1: schedule.tuesday,
            2: schedule.wednesday,
            3: schedule.thursday,
            4: schedule.friday,
            5: schedule.saturday,
            6: schedule.sunday
        }
        assigned_shifts = generate_schedule_for_employee(busy_schedules)
        data.append({
            'Full Name': full_name,
            'Monday': assigned_shifts[0],
            'Tuesday': assigned_shifts[1],
            'Wednesday': assigned_shifts[2],
            'Thursday': assigned_shifts[3],
            'Friday': assigned_shifts[4],
            'Saturday': assigned_shifts[5],
            'Sunday': assigned_shifts[6],
            'Created At': schedule.created_at.strftime('%Y-%m-%d')
        })

    # Create a DataFrame and export to Excel
    df = pd.DataFrame(data)
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Schedules')

    # Save the writer and seek to the beginning of the stream
    writer.close()
    output.seek(0)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='employee_schedules.xlsx'
    )


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        # Directly check the plain text password (not secure)
        if user and user.password == password:
            session['username'] = username
            session['role'] = user.role  # Ensure the role is set correctly

            if user.role == "Manager":
                return redirect(url_for('manager_dashboard'))
            elif user.role == "Employee":
                return redirect(url_for('employee_dashboard'))
        else:
            flash("Invalid credentials. Please try again.")
            return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/bookings', methods=['GET'])
def bookings():
    if 'username' not in session:
        return redirect(url_for('login'))

    # Get current time in GMT+7
    timezone = pytz.timezone('Asia/Bangkok')
    now = datetime.now(timezone)
    
    # Calculate the start of the week (Monday)
    start_of_week = now - timedelta(days=now.weekday())  # Start of this week (Monday)
    dates = [(start_of_week + timedelta(days=i)).strftime("%B %d") for i in range(7)]

    # Days of the week
    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    # Combine days with their respective dates
    week_data = list(zip(days_of_week, dates))

    # Check if the user has a booking for the current week
    existing_schedule = Schedule.query.filter(
        Schedule.username == session['username'],
        Schedule.created_at >= start_of_week,
        Schedule.created_at <= start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)
    ).first()

    # Convert schedule to a dictionary for easier access in the template, if it exists
    existing_schedule_dict = {
        'monday': existing_schedule.monday,
        'tuesday': existing_schedule.tuesday,
        'wednesday': existing_schedule.wednesday,
        'thursday': existing_schedule.thursday,
        'friday': existing_schedule.friday,
        'saturday': existing_schedule.saturday,
        'sunday': existing_schedule.sunday,
    } if existing_schedule else None

    schedule_id = existing_schedule.id if existing_schedule else None

    # Render the template with the combined week data
    return render_template('employee_booking.html', schedule=existing_schedule_dict, schedule_id=schedule_id, now=now, week_data=week_data)



@app.route('/edit_booking/<int:schedule_id>', methods=['GET', 'POST'])
def edit_booking(schedule_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    # Get the current schedule
    schedule = Schedule.query.get_or_404(schedule_id)

    # Get current time in GMT+7
    timezone = pytz.timezone('Asia/Bangkok')
    now = datetime.now(timezone)
    booking_deadline = now.replace(hour=23, minute=59, second=59, microsecond=0)

    # Check if it's Thursday after 24:00 and prevent editing if true
    if now.weekday() == 3 and now.time() > booking_deadline.time():
        flash('You can no longer edit this week\'s schedule after Thursday 24:00.')
        return redirect(url_for('bookings'))

    # Handle POST request for updating the schedule
    if request.method == 'POST':
        try:
            # Retrieve form data and update the schedule
            schedule.monday = request.form.get('monday', schedule.monday).strip()
            schedule.tuesday = request.form.get('tuesday', schedule.tuesday).strip()
            schedule.wednesday = request.form.get('wednesday', schedule.wednesday).strip()
            schedule.thursday = request.form.get('thursday', schedule.thursday).strip()
            schedule.friday = request.form.get('friday', schedule.friday).strip()
            schedule.saturday = request.form.get('saturday', schedule.saturday).strip()
            schedule.sunday = request.form.get('sunday', schedule.sunday).strip()

            # Commit changes to the database
            db.session.commit()
            flash('Your schedule has been updated successfully.')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating schedule: {str(e)}')
        
        return redirect(url_for('bookings'))

    # Prepare date information for display
    start_of_week = now - timedelta(days=now.weekday())
    dates = [(start_of_week + timedelta(days=i)).strftime("%B %d") for i in range(7)]
    days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    week_data = list(zip(days_of_week, dates))

    # Convert schedule into a dictionary for easier template handling
    schedule_data = {
        'monday': schedule.monday,
        'tuesday': schedule.tuesday,
        'wednesday': schedule.wednesday,
        'thursday': schedule.thursday,
        'friday': schedule.friday,
        'saturday': schedule.saturday,
        'sunday': schedule.sunday,
    }

    return render_template('edit_booking.html', schedule=schedule_data, week_data=week_data, schedule_id=schedule.id)



@app.route('/submit_booking', methods=['POST'])
def submit_booking():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    monday = request.form.get('monday')
    tuesday = request.form.get('tuesday')
    wednesday = request.form.get('wednesday')
    thursday = request.form.get('thursday')
    friday = request.form.get('friday')
    saturday = request.form.get('saturday')
    sunday = request.form.get('sunday')

    # Check if a schedule already exists for the week
    existing_schedule = Schedule.query.filter_by(username=username).first()

    if existing_schedule:
        # Update the existing schedule
        existing_schedule.monday = monday
        existing_schedule.tuesday = tuesday
        existing_schedule.wednesday = wednesday
        existing_schedule.thursday = thursday
        existing_schedule.friday = friday
        existing_schedule.saturday = saturday
        existing_schedule.sunday = sunday
        existing_schedule.created_at = datetime.utcnow()  # Update the timestamp
    else:
        # Create a new schedule entry
        new_schedule = Schedule(
            username=username,
            monday=monday,
            tuesday=tuesday,
            wednesday=wednesday,
            thursday=thursday,
            friday=friday,
            saturday=saturday,
            sunday=sunday,
            created_at=datetime.utcnow()
        )
        db.session.add(new_schedule)

    db.session.commit()
    flash('Schedule saved successfully.')
    return redirect(url_for('employee_dashboard'))



@app.route('/view_schedules', methods=['GET'])
def view_schedules():
    # Ensure the user is logged in and is a manager
    if 'username' not in session or session.get('role') != 'Manager':
        flash('You must be logged in as a manager to view this page.')
        return redirect(url_for('login'))

    # Get current time in GMT+7 and make it timezone-aware
    timezone = pytz.timezone('Asia/Bangkok')
    now = datetime.now(timezone)

    # Determine the selected year and week from the form
    selected_year = request.args.get('year', str(now.year))
    selected_week = request.args.get('week')

    # Generate week options for the selected year
    weeks = []
    start_date = datetime(int(selected_year), 1, 1, tzinfo=timezone)
    start_date += timedelta(days=(0 - start_date.weekday()))  # Adjust to the first Monday of the year

    while start_date.year == int(selected_year):
        end_date = start_date + timedelta(days=6)
        week_label = f"{start_date.strftime('%d/%m')} to {end_date.strftime('%d/%m')}"
        week_value = f"{start_date.strftime('%Y-%m-%d')}"
        weeks.append({'label': week_label, 'value': week_value})
        start_date += timedelta(weeks=1)

    # Default to the current week if no week is selected
    if not selected_week:
        # Find the current week based on the real-time date
        for week in weeks:
            week_start_date = datetime.strptime(week['value'], "%Y-%m-%d").replace(tzinfo=timezone)
            if week_start_date <= now <= week_start_date + timedelta(days=6):
                selected_week = week['value']
                break

    # Parse the selected week start date and make it timezone-aware
    selected_start_date = datetime.strptime(selected_week, "%Y-%m-%d").replace(tzinfo=timezone)
    selected_end_date = selected_start_date + timedelta(days=6)

    # Create a list of dates for each day of the selected week
    dates = [(selected_start_date + timedelta(days=i)).strftime('%B %d') for i in range(7)]

    # Retrieve schedules from the database based on the selected week
    schedules = Schedule.query.filter(
        Schedule.created_at >= selected_start_date,
        Schedule.created_at <= selected_end_date
    ).all()

    # Retrieve user full names for each schedule
    schedule_with_fullname = []
    for schedule in schedules:
        user = User.query.filter_by(username=schedule.username).first()
        full_name = user.full_name if user else schedule.username
        schedule_with_fullname.append({
            'full_name': full_name,
            'monday': schedule.monday,
            'tuesday': schedule.tuesday,
            'wednesday': schedule.wednesday,
            'thursday': schedule.thursday,
            'friday': schedule.friday,
            'saturday': schedule.saturday,
            'sunday': schedule.sunday,
            'created_at': schedule.created_at.strftime('%Y-%m-%d')
        })

    return render_template(
        'view_schedules.html',
        schedules=schedule_with_fullname,
        dates=dates,  # Pass the individual dates list here
        now=now,
        weeks=weeks,
        selected_week=selected_week
    )


@app.route('/manager_dashboard')
def manager_dashboard():
    if 'username' not in session or session.get('role') != 'Manager':
        flash('You must be logged in as a manager to view this page.')
        return redirect(url_for('login'))

    # Retrieve the manager's information using the username from the session
    manager = User.query.filter_by(username=session['username']).first()

    if not manager:
        flash('Manager not found.')
        return redirect(url_for('login'))

    # Render the manager_dashboard.html and pass the manager object
    return render_template('manager_dashboard.html', manager=manager)


@app.route('/employee/dashboard')
def employee_dashboard():
    if 'username' not in session or session['role'] != "Employee":
        return redirect(url_for('login'))
    user = User.query.filter_by(username=session['username']).first()
    return render_template('employee_dashboard.html',user=user)

@app.route('/register/employee', methods=['GET', 'POST'])
def register_employee():
    if 'username' not in session or session['role'] != "Manager":
        return redirect(url_for('login'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        full_name = request.form['full_name']
        phone_number = request.form['phone_number']
        dob = request.form['dob']
        current_address = request.form['current_address']
        gmail = request.form['gmail']
        role = "Employee"

        # Check if the user already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash("Username already exists.")
            return redirect(url_for('register_employee'))

        # Create a new employee with the provided details
        new_employee = User(
            username=username,
            password=password,
            role=role,
            full_name=full_name,
            phone_number=phone_number,
            dob=dob,
            current_address=current_address,
            gmail=gmail
        )
        db.session.add(new_employee)
        db.session.commit()
        flash("Employee registered successfully.")
        return redirect(url_for('manager_dashboard'))

    return render_template('register_employee.html')

@app.route('/create/manager', methods=['GET', 'POST'])
def create_manager():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        full_name = request.form['full_name']
        phone_number = request.form['phone_number']
        dob = request.form['dob']
        current_address = request.form['current_address']
        gmail = request.form['gmail']
        role = "Manager"

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash("Manager account already exists.")
            return redirect(url_for('create_manager'))

        new_manager = User(
            username=username,
            password=password,
            role=role,
            full_name=full_name,
            phone_number=phone_number,
            dob=dob,
            current_address=current_address,
            gmail=gmail
        )
        db.session.add(new_manager)
        db.session.commit()
        flash("Manager account created successfully. You can now log in.")
        return redirect(url_for('login'))

    return render_template('create_manager.html')

@app.route('/profile')
def profile():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    user = User.query.filter_by(username=session['username']).first()
    return render_template('profile.html', user=user)

@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'username' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(username=session['username']).first()

    if request.method == 'POST':
        user.full_name = request.form['full_name']
        user.dob = request.form['dob']
        user.phone_number = request.form['phone_number']
        user.gmail = request.form['gmail']
        user.current_address = request.form['current_address']
        db.session.commit()
        flash("Profile updated successfully.")
        return redirect(url_for('profile'))

    return render_template('edit_profile.html', user=user)

@app.route('/view_employees')
def view_employees():
    if 'username' not in session or session['role'] != 'Manager':
        return redirect(url_for('login'))

    employees = User.query.filter_by(role='Employee').all()
    return render_template('view_employees.html', employees=employees)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Create the database and tables within the application context
    app.run(debug=True)

