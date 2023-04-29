from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from datetime import datetime, timedelta, date
import calendar
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField
from wtforms.validators import DataRequired

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///vending.db'
db = SQLAlchemy(app)
app.secret_key = 'your-secret-key-here'

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    rfid = db.Column(db.String(120), unique=True, nullable=False)
    location_name = db.Column(db.String(50), db.ForeignKey('location.name'), nullable=False)
    location = db.relationship('Location', backref=db.backref('users', lazy=True))
    
    def __repr__(self):
        return f"User(name={self.name}, location={self.location})"

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) 
    transaction_date = db.Column(db.Date, nullable=False)
    daily_usage = db.Column(db.Date, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)  
    machine_id = db.Column(db.Integer, db.ForeignKey('machine.id'), nullable=False)

    user = db.relationship('User',backref=db.backref('transactions', lazy=True))
    machine = db.relationship('Machine', backref=db.backref('transactions', lazy=True))

class AddUserForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    rfid = StringField('RFID', validators=[DataRequired()])
    location = SelectField('Location', coerce=str)

class Machine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    location_name = db.Column(db.String(50), db.ForeignKey('location.name'), nullable=False)
    pad_count = db.Column(db.Integer, nullable=False)
    total_pads = db.Column(db.Integer, nullable=False)

    location = db.relationship('Location', backref=db.backref('machines', lazy=True))

    def __repr__(self):
        return f"Machine(name={self.name}, location={self.location}, pad_count={self.pad_count}, total_pads={self.total_pads})"

class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f"Location(name={self.name})"

class AddLocationForm(FlaskForm):
    location = StringField('Location', validators=[DataRequired()])
    submit = SubmitField('Add Location')

#access records of users to machines
class Access(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    machine_id = db.Column(db.Integer, db.ForeignKey('machine.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('accesses', lazy=True))
    machine = db.relationship('Machine', backref=db.backref('accesses', lazy=True))

    def __repr__(self):
        return f"Access(user={self.user}, machine={self.machine}, timestamp={self.timestamp})"

class Consumption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"Consumption(user_id={self.user_id}, amount={self.amount}, timestamp={self.timestamp})"

def get_consumption_stats(period='day'):
    # Determine the start and end dates for the selected period
    today = datetime.today().date()
    if period == 'day':
        start_date = today
        end_date = today + timedelta(days=1)
    elif period == 'week':
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(weeks=1)
    elif period == 'month':
        start_date = today.replace(day=1)
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year+1, month=1)
        else:
            end_date = start_date.replace(month=start_date.month+1)
        # Convert end date to datetime to allow filtering by range
        end_date = datetime.combine(end_date, datetime.min.time())
    else:
        raise ValueError('Invalid period')

    # Query the consumption data for the selected period
    stats = db.session.query(Consumption.user_id, db.func.sum(Consumption.amount))\
                      .filter(Consumption.timestamp >= start_date, Consumption.timestamp < end_date)\
                      .group_by(Consumption.user_id)\
                      .all()

    return stats

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    # Get the selected location from the query string
    location_name = request.args.get('location')

    # Get the list of locations and machines
    locations = Location.query.all()
    machines = Machine.query.all()

    # Filter the machines by location
    if location_name is not None:
        machines = Machine.query.join(Location).filter_by(name=location_name).all()
        # Get the list of users for the selected location and their RFID
        users = User.query.join(Access).join(Machine).join(Location).\
            filter(Location.name == location_name).\
            with_entities(User.id, User.name, User.rfid).\
            distinct().all()
    else:
        # Get the list of all users and their RFID
        users = User.query.with_entities(User.id, User.name, User.rfid).distinct().all()

    # Get the pad count for each user
    user_pad_counts = db.session.query(User.id, func.count(Access.id)).join(Access).join(Machine).join(Location).filter(Location.name == location_name, Location.name == User.location)\
                        .group_by(User.id).all()
    for user in users:
        pad_count = Access.query.join(Machine).join(Location).\
                    filter(Location.name == location_name, Access.user_id == user.id).count()
        user_pad_counts[user.id] = pad_count

    return render_template('admin.html', locations=locations, machines=machines, 
                           users=users, user_pad_counts=user_pad_counts)

@app.route('/add_user', methods=['GET', 'POST'])
def add_user():
    form = AddUserForm()
    # Set choices for location field
    form.location.choices = [(location.name, location.name) for location in Location.query.all()]
    if form.validate_on_submit():
        # Process form data and add new user to database
        return redirect(url_for('admin'))
    return render_template('add_user.html', form=form)

@app.route('/add_location', methods=['GET', 'POST'])
def add_location():
    form = AddLocationForm()
    if form.validate_on_submit():
        # Add the new location to the database
        location = form.location.data
        db.session.add(Location(name=location))
        db.session.commit()
        flash(f'Location "{location}" added successfully!', 'success')
        return redirect(url_for('admin'))

    return render_template('add_location.html', form=form)

@app.route('/update_pad_count', methods=['POST'])
def update_pad_count():
    machine_id = request.form.get('machine_id')
    pad_count = request.form.get('pad_count')
    machine = Machine.query.get(machine_id)
    if machine:
        machine.pad_count = pad_count
        db.session.commit()
        return 'Success'
    else:
        return 'Machine not found'

@app.route('/vend', methods=['POST'])
def vend():
    rfid = request.form.get('rfid')
    machine_id = request.form.get('machine_id')
    user = User.query.filter_by(rfid=rfid).first()
    machine = Machine.query.get(machine_id)
    if user and machine:
        new_transaction = Transaction(user_id=user.id, transaction_date=date.today(), quantity=1, machine_id=machine.id)
        machine.pad_count -= 1
        db.session.add(new_transaction)
        db.session.commit()
        return 'Success'
    else:
        return 'Invalid RFID or machine ID'

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)