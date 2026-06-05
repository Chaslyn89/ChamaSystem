from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, make_response
from functools import wraps
import os
import hashlib
import secrets
from datetime import datetime, timedelta
import json

# Import database functions
from database import (
    init_db, get_dashboard_stats, get_all_members, get_member_by_id,
    add_member, update_member, delete_member, update_member_balance,
    add_contribution, get_all_contributions, get_contributions_by_date,
    add_meeting, get_all_meetings, get_meeting_by_id, update_meeting, mark_attendance, get_attendance_summary,
    add_fine, get_all_fines, get_unpaid_fines, pay_fine,
    request_payout, get_all_payouts, get_pending_payouts, approve_payout, reject_payout,
    request_loan, get_all_loans, get_pending_loans, get_active_loans, approve_loan, reject_loan, repay_loan, get_loan_summary,
    add_expense, get_all_expenses, soft_delete_expense,
    get_member_statement, get_chama_summary,
    get_current_date, generate_receipt_number
)

# Import auth functions
from auth import hash_password, verify_password, get_user_by_username, create_user, update_user_password, create_member_user, get_member_id_by_username

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'chamaledger-secret-key-change-in-production')

# Initialize database when app starts
with app.app_context():
    init_db()

# ============= AUTHENTICATION DECORATOR =============

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def treasurer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'treasurer':
            flash('Access denied. Treasurer only.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def member_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'member':
            flash('Access denied. Members only.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# ============= AUTHENTICATION ROUTES =============

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not name or not phone or not password:
            flash('Name, phone and password are required', 'danger')
            return redirect(url_for('register'))
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('register'))
        
        if len(password) < 4:
            flash('Password must be at least 4 characters', 'danger')
            return redirect(url_for('register'))
        
        success, result = create_member_user(phone, password, email, phone, name)
        
        if success:
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        else:
            flash(f'Registration failed: {result}', 'danger')
    
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = get_user_by_username(username)
        
        if user and verify_password(password, user['password_hash']):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user.get('role', 'member')
            
            if session['role'] == 'member':
                member_id = get_member_id_by_username(username)
                session['member_id'] = member_id
            
            flash(f'Welcome back, {username}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))


@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password != confirm_password:
            flash('New passwords do not match', 'danger')
            return redirect(url_for('change_password'))
        
        user = get_user_by_username(session['username'])
        if verify_password(current_password, user['password_hash']):
            update_user_password(session['username'], new_password)
            flash('Password changed successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Current password is incorrect', 'danger')
    
    return render_template('change_password.html')


# ============= DASHBOARD =============

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    if session.get('role') == 'member':
        return redirect(url_for('member_dashboard'))
    
    stats = get_dashboard_stats()
    return render_template('dashboard.html', stats=stats)


@app.route('/member/dashboard')
@login_required
@member_required
def member_dashboard():
    member_id = session.get('member_id')
    member_data = get_member_by_id(member_id)
    stats = get_dashboard_stats()
    
    return render_template('member_dashboard.html', member=member_data, stats=stats)


# ============= MEMBER VIEWS (Limited Access) =============

@app.route('/member/contributions')
@login_required
@member_required
def member_contributions():
    member_id = session.get('member_id')
    member_data = get_member_by_id(member_id)
    return render_template('member_contributions.html', contributions=member_data['contributions'])


@app.route('/member/meetings')
@login_required
@member_required
def member_meetings():
    all_meetings = get_all_meetings()
    return render_template('member_meetings.html', meetings=all_meetings)


@app.route('/member/loans')
@login_required
@member_required
def member_loans():
    member_id = session.get('member_id')
    member_data = get_member_by_id(member_id)
    return render_template('member_loans.html', loans=member_data['loans'])


@app.route('/member/fines')
@login_required
@member_required
def member_fines():
    member_id = session.get('member_id')
    member_data = get_member_by_id(member_id)
    return render_template('member_fines.html', fines=member_data['fines'])


@app.route('/member/payouts')
@login_required
@member_required
def member_payouts():
    member_id = session.get('member_id')
    member_data = get_member_by_id(member_id)
    return render_template('member_payouts.html', payouts=member_data['payouts'])


@app.route('/member/statement')
@login_required
@member_required
def member_statement_view():
    member_id = session.get('member_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    statement = get_member_statement(member_id, start_date, end_date)
    return render_template('member_statement.html', statement=statement)


# ============= MEMBER ROUTES (Treasurer) =============

@app.route('/members')
@login_required
@treasurer_required
def members():
    all_members = get_all_members()
    return render_template('members.html', members=all_members)


@app.route('/members/add', methods=['GET', 'POST'])
@login_required
@treasurer_required
def add_member_view():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        email = request.form.get('email')
        notes = request.form.get('notes')
        
        if not name or not phone:
            flash('Name and phone are required', 'danger')
            return redirect(url_for('add_member_view'))
        
        try:
            member_id = add_member(name, phone, email, notes)
            flash(f'Member {name} added successfully!', 'success')
            return redirect(url_for('member_profile', member_id=member_id))
        except Exception as e:
            flash(f'Error adding member: {str(e)}', 'danger')
    
    return render_template('add_member.html')


@app.route('/members/<int:member_id>')
@login_required
def member_profile(member_id):
    if session.get('role') == 'member' and session.get('member_id') != member_id:
        flash('You can only view your own profile', 'danger')
        return redirect(url_for('member_dashboard'))
    
    member_data = get_member_by_id(member_id)
    if not member_data:
        flash('Member not found', 'danger')
        return redirect(url_for('members'))
    return render_template('member_profile.html', member_data=member_data)


@app.route('/members/<int:member_id>/edit', methods=['GET', 'POST'])
@login_required
@treasurer_required
def edit_member(member_id):
    member_data = get_member_by_id(member_id)
    if not member_data:
        flash('Member not found', 'danger')
        return redirect(url_for('members'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        email = request.form.get('email')
        notes = request.form.get('notes')
        
        update_member(member_id, name, phone, email, notes)
        update_member_balance(member_id)
        flash('Member updated successfully!', 'success')
        return redirect(url_for('member_profile', member_id=member_id))
    
    return render_template('edit_member.html', member=member_data['member'])


@app.route('/members/<int:member_id>/delete', methods=['POST'])
@login_required
@treasurer_required
def delete_member_view(member_id):
    delete_member(member_id)
    flash('Member removed', 'success')
    return redirect(url_for('members'))


# ============= CONTRIBUTION ROUTES =============

@app.route('/contributions')
@login_required
@treasurer_required
def contributions():
    all_contributions = get_all_contributions()
    return render_template('contributions.html', contributions=all_contributions)


@app.route('/contributions/add', methods=['GET', 'POST'])
@login_required
@treasurer_required
def add_contribution_view():
    members_list = get_all_members()
    meetings = get_all_meetings()
    
    if request.method == 'POST':
        member_id = request.form.get('member_id')
        amount = request.form.get('amount')
        payment_method = request.form.get('payment_method', 'cash')
        meeting_id = request.form.get('meeting_id') or None
        notes = request.form.get('notes')
        
        if not member_id or not amount:
            flash('Member and amount are required', 'danger')
            return redirect(url_for('add_contribution_view'))
        
        try:
            receipt = add_contribution(int(member_id), int(amount), payment_method, meeting_id, session['username'], notes)
            flash(f'Contribution recorded! Receipt: {receipt}', 'success')
            return redirect(url_for('contributions'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
    
    return render_template('add_contribution.html', members=members_list, meetings=meetings)


# ============= MEETING ROUTES =============

@app.route('/meetings')
@login_required
@treasurer_required
def meetings():
    all_meetings = get_all_meetings()
    return render_template('meetings.html', meetings=all_meetings)


@app.route('/meetings/add', methods=['GET', 'POST'])
@login_required
@treasurer_required
def add_meeting_view():
    if request.method == 'POST':
        meeting_date = request.form.get('meeting_date')
        venue = request.form.get('venue')
        agenda = request.form.get('agenda')
        
        if not meeting_date or not venue:
            flash('Date and venue are required', 'danger')
            return redirect(url_for('add_meeting_view'))
        
        meeting_id = add_meeting(meeting_date, venue, agenda)
        flash('Meeting scheduled!', 'success')
        return redirect(url_for('meeting_detail', meeting_id=meeting_id))
    
    return render_template('add_meeting.html')


@app.route('/meetings/<int:meeting_id>')
@login_required
@treasurer_required
def meeting_detail(meeting_id):
    meeting = get_meeting_by_id(meeting_id)
    if not meeting:
        flash('Meeting not found', 'danger')
        return redirect(url_for('meetings'))
    
    members_list = get_all_members()
    attendance_summary = get_attendance_summary(meeting_id)
    
    return render_template('meeting_detail.html', meeting=meeting, members=members_list, summary=attendance_summary)


@app.route('/meetings/<int:meeting_id>/attendance', methods=['POST'])
@login_required
@treasurer_required
def record_attendance(meeting_id):
    member_id = request.form.get('member_id')
    attended = request.form.get('attended', '0')
    
    mark_attendance(meeting_id, int(member_id), int(attended))
    flash('Attendance recorded', 'success')
    return redirect(url_for('meeting_detail', meeting_id=meeting_id))


@app.route('/meetings/<int:meeting_id>/minutes', methods=['POST'])
@login_required
@treasurer_required
def save_minutes(meeting_id):
    minutes = request.form.get('minutes')
    update_meeting(meeting_id, minutes=minutes)
    flash('Meeting minutes saved', 'success')
    return redirect(url_for('meeting_detail', meeting_id=meeting_id))


# ============= FINE ROUTES =============

@app.route('/fines')
@login_required
@treasurer_required
def fines():
    all_fines = get_all_fines()
    unpaid_fines = get_unpaid_fines()
    return render_template('fines.html', fines=all_fines, unpaid_fines=unpaid_fines)


@app.route('/fines/add', methods=['GET', 'POST'])
@login_required
@treasurer_required
def add_fine_view():
    members_list = get_all_members()
    meetings = get_all_meetings()
    
    if request.method == 'POST':
        member_id = request.form.get('member_id')
        amount = request.form.get('amount')
        reason = request.form.get('reason')
        meeting_id = request.form.get('meeting_id') or None
        
        add_fine(int(member_id), int(amount), reason, meeting_id)
        flash('Fine issued successfully!', 'success')
        return redirect(url_for('fines'))
    
    return render_template('add_fine.html', members=members_list, meetings=meetings)


@app.route('/fines/<int:fine_id>/pay', methods=['POST'])
@login_required
@treasurer_required
def pay_fine_view(fine_id):
    pay_fine(fine_id)
    flash('Fine marked as paid', 'success')
    return redirect(url_for('fines'))


# ============= PAYOUT ROUTES =============

@app.route('/payouts')
@login_required
@treasurer_required
def payouts():
    all_payouts = get_all_payouts()
    pending = get_pending_payouts()
    return render_template('payouts.html', payouts=all_payouts, pending=pending)


@app.route('/payouts/request', methods=['GET', 'POST'])
@login_required
def request_payout_view():
    if session.get('role') == 'member':
        member_id = session.get('member_id')
        members_list = [{'id': member_id, 'name': session.get('username')}]
    else:
        members_list = get_all_members()
    
    meetings = get_all_meetings()
    
    if request.method == 'POST':
        member_id = request.form.get('member_id')
        amount = request.form.get('amount')
        purpose = request.form.get('purpose')
        meeting_id = request.form.get('meeting_id') or None
        
        request_payout(int(member_id), int(amount), purpose, meeting_id)
        flash('Payout request submitted!', 'success')
        return redirect(url_for('payouts') if session.get('role') == 'treasurer' else url_for('member_dashboard'))
    
    return render_template('request_payout.html', members=members_list, meetings=meetings)


@app.route('/payouts/<int:payout_id>/approve', methods=['POST'])
@login_required
@treasurer_required
def approve_payout_view(payout_id):
    approve_payout(payout_id, session['username'])
    flash('Payout approved!', 'success')
    return redirect(url_for('payouts'))


@app.route('/payouts/<int:payout_id>/reject', methods=['POST'])
@login_required
@treasurer_required
def reject_payout_view(payout_id):
    reject_payout(payout_id)
    flash('Payout rejected', 'success')
    return redirect(url_for('payouts'))


# ============= LOAN ROUTES =============

@app.route('/loans')
@login_required
@treasurer_required
def loans():
    all_loans = get_all_loans()
    pending = get_pending_loans()
    active = get_active_loans()
    summary = get_loan_summary()
    return render_template('loans.html', loans=all_loans, pending=pending, active=active, summary=summary)


@app.route('/loans/request', methods=['GET', 'POST'])
@login_required
def request_loan_view():
    if session.get('role') == 'member':
        member_id = session.get('member_id')
        members_list = [{'id': member_id, 'name': session.get('username')}]
    else:
        members_list = get_all_members()
    
    if request.method == 'POST':
        member_id = request.form.get('member_id')
        loan_amount = request.form.get('loan_amount')
        interest_rate = request.form.get('interest_rate', '0')
        due_date = request.form.get('due_date')
        notes = request.form.get('notes')
        
        request_loan(int(member_id), int(loan_amount), int(interest_rate), due_date, notes)
        flash('Loan request submitted!', 'success')
        return redirect(url_for('loans') if session.get('role') == 'treasurer' else url_for('member_dashboard'))
    
    return render_template('request_loan.html', members=members_list)


@app.route('/loans/<int:loan_id>/approve', methods=['POST'])
@login_required
@treasurer_required
def approve_loan_view(loan_id):
    approve_loan(loan_id, session['username'])
    flash('Loan approved!', 'success')
    return redirect(url_for('loans'))


@app.route('/loans/<int:loan_id>/reject', methods=['POST'])
@login_required
@treasurer_required
def reject_loan_view(loan_id):
    reject_loan(loan_id)
    flash('Loan rejected', 'success')
    return redirect(url_for('loans'))


@app.route('/loans/<int:loan_id>/repay', methods=['POST'])
@login_required
def repay_loan_view(loan_id):
    amount = request.form.get('amount')
    repay_loan(loan_id, int(amount))
    flash('Loan repayment recorded!', 'success')
    return redirect(url_for('loans') if session.get('role') == 'treasurer' else url_for('member_dashboard'))


# ============= EXPENSE ROUTES =============

@app.route('/expenses')
@login_required
@treasurer_required
def expenses():
    all_expenses = get_all_expenses()
    return render_template('expenses.html', expenses=all_expenses)


@app.route('/expenses/add', methods=['GET', 'POST'])
@login_required
@treasurer_required
def add_expense_view():
    if request.method == 'POST':
        category = request.form.get('category')
        amount = request.form.get('amount')
        description = request.form.get('description')
        expense_date = request.form.get('expense_date', get_current_date())
        
        add_expense(category, int(amount), description, expense_date)
        flash('Expense added!', 'success')
        return redirect(url_for('expenses'))
    
    return render_template('add_expense.html')


@app.route('/expenses/<int:expense_id>/delete', methods=['POST'])
@login_required
@treasurer_required
def delete_expense_view(expense_id):
    soft_delete_expense(expense_id)
    flash('Expense deleted', 'success')
    return redirect(url_for('expenses'))


# ============= REPORT ROUTES =============

@app.route('/reports')
@login_required
@treasurer_required
def reports():
    return render_template('reports.html')


@app.route('/reports/member-statement/<int:member_id>')
@login_required
@treasurer_required
def member_statement(member_id):
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    statement = get_member_statement(member_id, start_date, end_date)
    return render_template('member_statement.html', statement=statement)


@app.route('/reports/chama-summary')
@login_required
@treasurer_required
def chama_summary():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    summary = get_chama_summary(start_date, end_date)
    return render_template('chama_summary.html', summary=summary)


@app.route('/reports/contributions-by-date')
@login_required
@treasurer_required
def contributions_by_date():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if start_date and end_date:
        contributions = get_contributions_by_date(start_date, end_date)
        total = sum(c['amount'] for c in contributions)
        return render_template('contributions_report.html', contributions=contributions, total=total, start_date=start_date, end_date=end_date)
    
    return render_template('date_range_report.html', report_type='contributions')


# ============= SEARCH =============

@app.route('/search')
@login_required
@treasurer_required
def search():
    query = request.args.get('q', '')
    if not query:
        return redirect(url_for('dashboard'))
    
    members_list = get_all_members()
    results = [m for m in members_list if query.lower() in m['name'].lower() or query in m.get('phone', '')]
    
    return render_template('search_results.html', results=results, query=query)


# ============= API ENDPOINTS (JSON) =============

@app.route('/api/members')
@login_required
@treasurer_required
def api_members():
    members_list = get_all_members()
    return jsonify(members_list)


@app.route('/api/members/<int:member_id>/balance')
@login_required
def api_member_balance(member_id):
    member = get_member_by_id(member_id)
    if member:
        return jsonify({'balance': member['member']['current_balance']})
    return jsonify({'error': 'Member not found'}), 404


@app.route('/api/dashboard/stats')
@login_required
def api_dashboard_stats():
    stats = get_dashboard_stats()
    return jsonify(stats)


# ============= ERROR HANDLERS =============

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(error):
    return render_template('500.html'), 500


# ============= RUN APPLICATION =============

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)