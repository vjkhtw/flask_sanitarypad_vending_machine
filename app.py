from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import os
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
import calendar
from sqlalchemy import func
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///vending.db'
db = SQLAlchemy(app)
socketio = SocketIO(app)

app.secret_key = 'your-secret-key-here'

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    rfid = db.Column(db.String(50), unique=True)
    transactions = db.relationship('Transaction', backref='user', lazy=True)
    pad_count = db.Column(db.Integer, default=0)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    transaction_date = db.Column(db.Date, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    daily_usage = db.Column(db.String(50))
    location = db.Column(db.String(50))

    def __init__(self, user_id, transaction_date, quantity, daily_usage, location):
        self.user_id = user_id
        self.transaction_date = transaction_date
        self.quantity = quantity
        self.daily_usage = daily_usage
        self.location = location
        self.user = User.query.get(user_id)
        self.user.pad_count += self.quantity
        db.session.add(self)
        db.session.add(self.user)
        db.session.commit()

class VendingMachine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    total_pads = db.Column(db.Integer, nullable=False)

def get_daily_consumption_data(product_id):
    # Get the start and end date of the current day
    today = date.today()
    start_date = datetime.combine(today, datetime.min.time())
    end_date = datetime.combine(today, datetime.max.time())

    # Query the database for the consumption data for the given product and date range
    daily_data = db.session.query(func.sum(Transaction.quantity), func.extract('hour', Transaction.transaction_date)). \
        filter(Transaction.id == product_id). \
        filter(Transaction.transaction_date >= start_date). \
        filter(Transaction.transaction_date <= end_date). \
        group_by(func.extract('hour', Transaction.transaction_date)). \
        all()

    # Format the data into a list of consumption values for each hour of the day
    daily_consumption = [0] * 24
    daily_labels = [f"{i:02d}:00" for i in range(24)]
    for data in daily_data:
        hour = data[1]
        daily_consumption[hour] = data[0]

    return daily_labels, daily_consumption

def get_weekly_consumption_data(product_id):
    # Get the start and end date of the current week
    today = date.today()
    start_date = today - timedelta(days=today.weekday())
    end_date = start_date + timedelta(days=6)

    # Query the database for the consumption data for the given product and date range
    weekly_data = db.session.query(func.sum(Transaction.quantity)). \
        filter(Transaction.id == product_id). \
        filter(Transaction.transaction_date >= start_date). \
        filter(Transaction.transaction_date <= end_date). \
        group_by(Transaction.transaction_date). \
        all()

    # Format the data into a list of consumption values for each week
    weekly_consumption = [data[0] for data in weekly_data]
    weekly_labels = [start_date + timedelta(days=i) for i in range(7)]

    return weekly_labels, weekly_consumption

def get_monthly_consumption_data(product_id):
    # Get the start and end date of the current month
    today = date.today()
    start_date = today.replace(day=1)
    end_date = start_date + relativedelta(months=1) - timedelta(days=1)

    # Query the database for the consumption data for the given product and date range
    monthly_data = db.session.query(func.sum(Transaction.quantity)). \
        filter(Transaction.id == product_id). \
        filter(Transaction.transaction_date >= start_date). \
        filter(Transaction.transaction_date <= end_date). \
        group_by(Transaction.transaction_date). \
        all()

    # Format the data into a list of consumption values for each month
    monthly_consumption = [data[0] for data in monthly_data]
    monthly_labels = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]

    return monthly_labels, monthly_consumption

def get_total_consumption_data(product_id):
    # Query the database for the total consumption data for the given product
    total_data = db.session.query(func.sum(Transaction.quantity)). \
        filter(Transaction.id == product_id). \
        scalar()

    # Format the data into a list of consumption values for the total period
    total_consumption = [total_data] if total_data else []
    total_labels = ["Total"]

    return total_labels, total_consumption

@app.route('/')
def index():
    return redirect(url_for('admin_panel'))

@app.route('/add_user', methods=['POST']) 
def add_user():
    name = request.form.get('name')
    rfid = request.form.get('rfid')
    new_user = User(name=name, rfid=rfid)
    db.session.add(new_user)
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/stock_machine', methods=['POST'])
def stock_machine():
    total_pads = request.form.get('total_pads')
    machine = VendingMachine.query.first()
    if machine:
        machine.total_pads = total_pads
    else:
        machine = VendingMachine(total_pads=total_pads)
        db.session.add(machine)
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/dispense_pad', methods=['POST'])
def dispense_pad():
    rfid = request.form.get('rfid')
    user = User.query.filter_by(rfid=rfid).first()
    machine = VendingMachine.query.first()
    if user and machine.total_pads > 0:
        transaction = Transaction(user_id=user.id)
        db.session.add(transaction)
        machine.total_pads -= 1
        db.session.commit()
        socketio.emit('pad_dispensed', {'user_id': user.id, 'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
        return 'Pad dispensed'
    elif machine.total_pads == 0:
        return 'Machine is empty'
    else:
        return 'Invalid RFID'

@app.route('/admin')
def admin():
    users = User.query.all()
    machine = VendingMachine.query.first()
    pads_dispensed = 0

    @socketio.on('pad_dispensed')
    def handle_pad_dispensed(data):
        nonlocal pads_dispensed
        pads_dispensed += 1
    return render_template('admin.html', users=users, machine=machine, pads_dispensed=pads_dispensed)

@app.route('/vend', methods=['POST'])
def vend():
    rfid = request.form.get('rfid')
    location = request.form.get('location')
    user = User.query.filter_by(rfid=rfid).first()
    if user:
        new_transaction = Transaction(user_id=user.id, transaction_date=date.today(), quantity=1, location=location)
        db.session.add(new_transaction)
        db.session.commit()
        return 'Success'
    else:
        return 'Invalid RFID'

@app.route('/consumption_statistics', methods=['GET', 'POST'])
def consumption_statistics():
    if request.method == 'POST':
        product_id = request.form.get('product_id')
        selected_interval = request.form.get('interval')
    else:
        product_id = request.args.get('product_id')
        selected_interval = request.args.get('interval')

    # Retrieve the consumption data based on the selected interval
    if selected_interval == 'daily':
        daily_labels, daily_data = get_daily_consumption_data(product_id)
        return render_template('consumption_statistics.html',
                               interval='daily',
                               daily_labels=daily_labels,
                               daily_data=daily_data,
                               product_id=product_id)
    elif selected_interval == 'weekly':
        weekly_labels, weekly_data = get_weekly_consumption_data(product_id)
        return render_template('consumption_statistics.html',
                               interval='weekly',
                               weekly_labels=weekly_labels,
                               weekly_data=weekly_data,
                               product_id=product_id)
    elif selected_interval == 'monthly':
        monthly_labels, monthly_data = get_monthly_consumption_data(product_id)
        return render_template('consumption_statistics.html',
                               interval='monthly',
                               monthly_labels=monthly_labels,
                               monthly_data=monthly_data,
                               product_id=product_id)
    elif selected_interval == 'total':
        total_labels, total_data = get_total_consumption_data(product_id)
        return render_template('consumption_statistics.html',
                               interval='total',
                               total_labels=total_labels,
                               total_data=total_data,
                               product_id=product_id)

    return render_template('consumption_statistics.html', product_id=product_id)


@app.route('/user_pads/<int:user_id>/<interval>')
def user_pads(user_id, interval):
    user = User.query.get(user_id)
    if user is None:
        return f'User with id {user_id} not found', 404

    today = date.today()
    if interval == 'total':
        pads_used = user.pad_count
    elif interval == 'daily':
        pads_used = len(Transaction.query.filter_by(user_id=user_id, transaction_date=today).all())
    elif interval == 'weekly':
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        pads_used = len(Transaction.query.filter_by(user_id=user_id).filter(Transaction.transaction_date.between(start_of_week, end_of_week)).all())
    elif interval == 'monthly':
        start_of_month = date(today.year, today.month, 1)
        end_of_month = date(today.year, today.month + 1, 1) - timedelta(days=1)
        pads_used = len(Transaction.query.filter_by(user_id=user_id).filter(Transaction.transaction_date.between(start_of_month, end_of_month)).all())
    else:
        return f'Invalid interval {interval}', 400

    return str(pads_used)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)