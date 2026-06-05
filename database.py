import os
from datetime import datetime, timedelta
import uuid
from functools import wraps
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool

# Database connection pool
db_pool = None

def init_db_pool():
    """Initialize connection pool for PostgreSQL"""
    global db_pool
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    
    db_pool = SimpleConnectionPool(
        minconn=2,
        maxconn=20,
        dsn=database_url
    )
    return db_pool

def get_db():
    """Get database connection from pool"""
    global db_pool
    if db_pool is None:
        init_db_pool()
    return db_pool.getconn()

def return_db(conn):
    """Return connection to pool"""
    global db_pool
    if db_pool:
        db_pool.putconn(conn)

# Cache for dashboard stats
_cache = {}
CACHE_TTL = 60

def cache_result(ttl=CACHE_TTL):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{args}:{kwargs}"
            now = time.time()
            if cache_key in _cache:
                result, timestamp = _cache[cache_key]
                if now - timestamp < ttl:
                    return result
            result = func(*args, **kwargs)
            _cache[cache_key] = (result, now)
            return result
        return wrapper
    return decorator

def get_current_date():
    """Get current date as string for DATE fields"""
    return datetime.now().strftime('%Y-%m-%d')

def get_current_datetime():
    """Get current datetime for TIMESTAMP fields"""
    return datetime.now().isoformat()

def init_db():
    """Initialize database with all tables for ChamaLedger"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # 1. Members table with member_number
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS members (
                id SERIAL PRIMARY KEY,
                member_number TEXT UNIQUE,
                name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                join_date DATE,
                total_contributions INTEGER DEFAULT 0,
                total_payouts INTEGER DEFAULT 0,
                total_fines_paid INTEGER DEFAULT 0,
                current_balance INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                notes TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        ''')
        
        # 2. Contributions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contributions (
                id SERIAL PRIMARY KEY,
                member_id INTEGER REFERENCES members(id) ON DELETE CASCADE,
                receipt_number TEXT UNIQUE,
                amount INTEGER NOT NULL,
                payment_method TEXT DEFAULT 'cash',
                meeting_id INTEGER,
                recorded_by TEXT,
                notes TEXT,
                contribution_date DATE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        ''')
        
        # 3. Meetings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS meetings (
                id SERIAL PRIMARY KEY,
                meeting_date DATE NOT NULL,
                venue TEXT,
                agenda TEXT,
                minutes TEXT,
                status TEXT DEFAULT 'upcoming',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        ''')
        
        # 4. Attendance table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id SERIAL PRIMARY KEY,
                meeting_id INTEGER REFERENCES meetings(id) ON DELETE CASCADE,
                member_id INTEGER REFERENCES members(id) ON DELETE CASCADE,
                attended INTEGER DEFAULT 0,
                UNIQUE(meeting_id, member_id)
            )
        ''')
        
        # 5. Fines table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fines (
                id SERIAL PRIMARY KEY,
                member_id INTEGER REFERENCES members(id) ON DELETE CASCADE,
                amount INTEGER NOT NULL,
                reason TEXT,
                meeting_id INTEGER REFERENCES meetings(id),
                paid_status INTEGER DEFAULT 0,
                paid_date DATE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        ''')
        
        # 6. Payouts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payouts (
                id SERIAL PRIMARY KEY,
                member_id INTEGER REFERENCES members(id) ON DELETE CASCADE,
                amount INTEGER NOT NULL,
                purpose TEXT,
                meeting_id INTEGER REFERENCES meetings(id),
                approved_by TEXT,
                status TEXT DEFAULT 'pending',
                payout_date DATE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        ''')
        
        # 7. Expenses table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id SERIAL PRIMARY KEY,
                category TEXT,
                amount INTEGER,
                description TEXT,
                expense_date DATE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                deleted_at TIMESTAMP WITH TIME ZONE
            )
        ''')
        
        # 8. Loans table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS loans (
                id SERIAL PRIMARY KEY,
                member_id INTEGER REFERENCES members(id) ON DELETE CASCADE,
                loan_amount INTEGER NOT NULL,
                interest_rate INTEGER DEFAULT 0,
                amount_due INTEGER NOT NULL,
                amount_paid INTEGER DEFAULT 0,
                remaining_balance INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                issue_date DATE,
                due_date DATE,
                approved_by TEXT,
                notes TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        ''')
        
        # 9. Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                email TEXT,
                role TEXT DEFAULT 'treasurer',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        ''')
        
        # INDEXES for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_member_number ON members(member_number)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_member_phone ON members(phone)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_member_name ON members(name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_member_status ON members(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_contribution_member ON contributions(member_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_contribution_date ON contributions(contribution_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_meeting_date ON meetings(meeting_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_meeting_status ON meetings(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fines_member ON fines(member_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fines_status ON fines(paid_status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_payouts_member ON payouts(member_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_payouts_status ON payouts(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_loans_member ON loans(member_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_loans_status ON loans(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_expense_date ON expenses(expense_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_expense_deleted ON expenses(deleted_at)')
        
        # Insert default user (treasurer) if not exists
        cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'treasurer'")
        if cursor.fetchone()[0] == 0:
            import hashlib
            import secrets
            salt = secrets.token_hex(16)
            default_password = 'Chama2026'
            hash_obj = hashlib.sha256((default_password + salt).encode())
            default_password_hash = f"{salt}:{hash_obj.hexdigest()}"
            cursor.execute('''
                INSERT INTO users (username, password_hash, email, role, created_at)
                VALUES (%s, %s, %s, %s, NOW())
            ''', ('treasurer', default_password_hash, 'chama@gmail.com', 'treasurer'))
        
        # Update existing members to have member numbers
        cursor.execute("UPDATE members SET member_number = CONCAT('CHM-', LPAD(id::TEXT, 3, '0')) WHERE member_number IS NULL")
        
        conn.commit()
        print("✅ ChamaLedger database initialized successfully!")
    except Exception as e:
        print(f"❌ Database init error: {e}")
        conn.rollback()
        raise e
    finally:
        return_db(conn)


# ============= MEMBER OPERATIONS =============

def add_member(name, phone, email=None, notes=None):
    """Add a new member with auto-generated member number"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # Generate member number
        cursor.execute("SELECT COALESCE(MAX(CAST(SUBSTRING(member_number FROM 5) AS INTEGER)), 0) FROM members WHERE member_number LIKE 'CHM-%'")
        max_num = cursor.fetchone()[0]
        new_num = max_num + 1
        member_number = f"CHM-{str(new_num).zfill(3)}"
        
        cursor.execute('''
            INSERT INTO members (member_number, name, phone, email, join_date, status, notes, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            RETURNING id
        ''', (member_number, name, phone, email, get_current_date(), 'active', notes))
        member_id = cursor.fetchone()[0]
        conn.commit()
        _cache.clear()
        return member_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        return_db(conn)


def get_all_members():
    """Get all active members with member number"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, member_number, name, phone, email, join_date, total_contributions, total_payouts, current_balance, status, notes
            FROM members 
            WHERE status = 'active'
            ORDER BY member_number
        ''')
        columns = ['id', 'member_number', 'name', 'phone', 'email', 'join_date', 'total_contributions', 
                  'total_payouts', 'current_balance', 'status', 'notes']
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        return_db(conn)


def get_member_by_id(member_id):
    """Get member details with their contribution history"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT id, member_number, name, phone, email, join_date, total_contributions, total_payouts, total_fines_paid, current_balance, status, notes, created_at, updated_at FROM members WHERE id = %s', (member_id,))
        member_row = cursor.fetchone()
        if not member_row:
            return None
        
        member_columns = ['id', 'member_number', 'name', 'phone', 'email', 'join_date', 'total_contributions', 
                         'total_payouts', 'total_fines_paid', 'current_balance', 'status', 
                         'notes', 'created_at', 'updated_at']
        member = dict(zip(member_columns, member_row))
        
        # Format dates for display
        if member.get('join_date'):
            member['join_date'] = str(member['join_date'])
        
        # Get contribution history
        cursor.execute('''
            SELECT * FROM contributions WHERE member_id = %s ORDER BY contribution_date DESC LIMIT 20
        ''', (member_id,))
        contrib_columns = ['id', 'member_id', 'receipt_number', 'amount', 'payment_method', 
                          'meeting_id', 'recorded_by', 'notes', 'contribution_date', 'created_at']
        contributions = []
        for row in cursor.fetchall():
            contrib = dict(zip(contrib_columns, row))
            if contrib.get('contribution_date'):
                contrib['contribution_date'] = str(contrib['contribution_date'])
            contributions.append(contrib)
        
        # Get fine history
        cursor.execute('SELECT * FROM fines WHERE member_id = %s ORDER BY created_at DESC', (member_id,))
        fine_columns = ['id', 'member_id', 'amount', 'reason', 'meeting_id', 'paid_status', 'paid_date', 'created_at']
        fines = []
        for row in cursor.fetchall():
            fine = dict(zip(fine_columns, row))
            if fine.get('paid_date'):
                fine['paid_date'] = str(fine['paid_date'])
            fines.append(fine)
        
        # Get payout history
        cursor.execute('SELECT * FROM payouts WHERE member_id = %s ORDER BY created_at DESC', (member_id,))
        payout_columns = ['id', 'member_id', 'amount', 'purpose', 'meeting_id', 'approved_by', 'status', 'payout_date', 'created_at']
        payouts = []
        for row in cursor.fetchall():
            payout = dict(zip(payout_columns, row))
            if payout.get('payout_date'):
                payout['payout_date'] = str(payout['payout_date'])
            payouts.append(payout)
        
        # Get loan history
        cursor.execute('SELECT * FROM loans WHERE member_id = %s ORDER BY created_at DESC', (member_id,))
        loan_columns = ['id', 'member_id', 'loan_amount', 'interest_rate', 'amount_due', 'amount_paid', 
                       'remaining_balance', 'status', 'issue_date', 'due_date', 'approved_by', 'notes', 'created_at', 'updated_at']
        loans = []
        for row in cursor.fetchall():
            loan = dict(zip(loan_columns, row))
            if loan.get('issue_date'):
                loan['issue_date'] = str(loan['issue_date'])
            if loan.get('due_date'):
                loan['due_date'] = str(loan['due_date'])
            loans.append(loan)
        
        return {
            'member': member,
            'contributions': contributions,
            'fines': fines,
            'payouts': payouts,
            'loans': loans
        }
    finally:
        return_db(conn)


def update_member_balance(member_id):
    """Recalculate member's current balance"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # Total contributions
        cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM contributions WHERE member_id = %s', (member_id,))
        total_in = cursor.fetchone()[0]
        
        # Total payouts approved
        cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM payouts WHERE member_id = %s AND status = %s', 
                      (member_id, 'approved'))
        total_out = cursor.fetchone()[0]
        
        # Total unpaid fines
        cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM fines WHERE member_id = %s AND paid_status = 0', (member_id,))
        total_fines = cursor.fetchone()[0]
        
        # Total fines paid
        cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM fines WHERE member_id = %s AND paid_status = 1', (member_id,))
        total_fines_paid = cursor.fetchone()[0]
        
        balance = total_in - total_out - total_fines
        
        cursor.execute('''
            UPDATE members SET 
                current_balance = %s, 
                total_contributions = %s, 
                total_payouts = %s,
                total_fines_paid = %s,
                updated_at = NOW()
            WHERE id = %s
        ''', (balance, total_in, total_out, total_fines_paid, member_id))
        
        conn.commit()
        _cache.clear()
        return balance
    finally:
        return_db(conn)


def update_member(member_id, name=None, phone=None, email=None, notes=None):
    """Update member information"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # Build dynamic update query
        updates = []
        params = []
        
        if name:
            updates.append("name = %s")
            params.append(name)
        if phone:
            updates.append("phone = %s")
            params.append(phone)
        if email is not None:
            updates.append("email = %s")
            params.append(email)
        if notes is not None:
            updates.append("notes = %s")
            params.append(notes)
        
        if not updates:
            return False
        
        updates.append("updated_at = NOW()")
        params.append(member_id)
        
        query = f"UPDATE members SET {', '.join(updates)} WHERE id = %s"
        cursor.execute(query, params)
        conn.commit()
        _cache.clear()
        return True
    finally:
        return_db(conn)


def delete_member(member_id):
    """Soft delete a member (set status to inactive)"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('UPDATE members SET status = %s, updated_at = NOW() WHERE id = %s', 
                      ('inactive', member_id))
        conn.commit()
        _cache.clear()
        return True
    finally:
        return_db(conn)


# ============= CONTRIBUTION OPERATIONS =============

def generate_receipt_number():
    """Generate unique receipt number"""
    return f"CHM-{uuid.uuid4().hex[:8].upper()}"


def add_contribution(member_id, amount, payment_method='cash', meeting_id=None, recorded_by=None, notes=None):
    """Record a member contribution"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        receipt_number = generate_receipt_number()
        
        cursor.execute('''
            INSERT INTO contributions (member_id, receipt_number, amount, payment_method, meeting_id, recorded_by, notes, contribution_date, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ''', (member_id, receipt_number, amount, payment_method, meeting_id, recorded_by, notes, get_current_date()))
        
        conn.commit()
        _cache.clear()
        
        # Update member balance
        update_member_balance(member_id)
        
        return receipt_number
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        return_db(conn)


def get_all_contributions(limit=100):
    """Get all contributions with member names and numbers"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.*, m.name as member_name, m.member_number
            FROM contributions c
            JOIN members m ON c.member_id = m.id
            ORDER BY c.contribution_date DESC
            LIMIT %s
        ''', (limit,))
        columns = ['id', 'member_id', 'receipt_number', 'amount', 'payment_method', 
                  'meeting_id', 'recorded_by', 'notes', 'contribution_date', 'created_at', 'member_name', 'member_number']
        results = []
        for row in cursor.fetchall():
            result = dict(zip(columns, row))
            if result.get('contribution_date'):
                result['contribution_date'] = str(result['contribution_date'])
            results.append(result)
        return results
    finally:
        return_db(conn)


def get_contributions_by_date(start_date, end_date):
    """Get contributions within date range"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.*, m.name as member_name, m.member_number
            FROM contributions c
            JOIN members m ON c.member_id = m.id
            WHERE c.contribution_date BETWEEN %s AND %s
            ORDER BY c.contribution_date DESC
        ''', (start_date, end_date))
        columns = ['id', 'member_id', 'receipt_number', 'amount', 'payment_method', 
                  'meeting_id', 'recorded_by', 'notes', 'contribution_date', 'created_at', 'member_name', 'member_number']
        results = []
        for row in cursor.fetchall():
            result = dict(zip(columns, row))
            if result.get('contribution_date'):
                result['contribution_date'] = str(result['contribution_date'])
            results.append(result)
        return results
    finally:
        return_db(conn)


# ============= MEETING OPERATIONS =============

def add_meeting(meeting_date, venue, agenda=None):
    """Schedule a new meeting"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO meetings (meeting_date, venue, agenda, status, created_at)
            VALUES (%s, %s, %s, %s, NOW())
            RETURNING id
        ''', (meeting_date, venue, agenda, 'upcoming'))
        meeting_id = cursor.fetchone()[0]
        conn.commit()
        _cache.clear()
        return meeting_id
    finally:
        return_db(conn)


def get_all_meetings():
    """Get all meetings"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM meetings ORDER BY meeting_date DESC')
        columns = ['id', 'meeting_date', 'venue', 'agenda', 'minutes', 'status', 'created_at']
        results = []
        for row in cursor.fetchall():
            result = dict(zip(columns, row))
            if result.get('meeting_date'):
                result['meeting_date'] = str(result['meeting_date'])
            results.append(result)
        return results
    finally:
        return_db(conn)


def get_meeting_by_id(meeting_id):
    """Get meeting details with attendance"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM meetings WHERE id = %s', (meeting_id,))
        meeting_row = cursor.fetchone()
        if not meeting_row:
            return None
        
        columns = ['id', 'meeting_date', 'venue', 'agenda', 'minutes', 'status', 'created_at']
        meeting = dict(zip(columns, meeting_row))
        if meeting.get('meeting_date'):
            meeting['meeting_date'] = str(meeting['meeting_date'])
        
        # Get attendance
        cursor.execute('''
            SELECT a.*, m.name as member_name, m.member_number
            FROM attendance a
            JOIN members m ON a.member_id = m.id
            WHERE a.meeting_id = %s
        ''', (meeting_id,))
        attendance_columns = ['id', 'meeting_id', 'member_id', 'attended', 'member_name', 'member_number']
        meeting['attendance'] = [dict(zip(attendance_columns, row)) for row in cursor.fetchall()]
        
        return meeting
    finally:
        return_db(conn)


def update_meeting(meeting_id, meeting_date=None, venue=None, agenda=None, minutes=None, status=None):
    """Update meeting information"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        updates = []
        params = []
        
        if meeting_date:
            updates.append("meeting_date = %s")
            params.append(meeting_date)
        if venue:
            updates.append("venue = %s")
            params.append(venue)
        if agenda is not None:
            updates.append("agenda = %s")
            params.append(agenda)
        if minutes is not None:
            updates.append("minutes = %s")
            params.append(minutes)
        if status:
            updates.append("status = %s")
            params.append(status)
        
        if not updates:
            return False
        
        params.append(meeting_id)
        query = f"UPDATE meetings SET {', '.join(updates)} WHERE id = %s"
        cursor.execute(query, params)
        conn.commit()
        _cache.clear()
        return True
    finally:
        return_db(conn)


def mark_attendance(meeting_id, member_id, attended):
    """Mark if a member attended a meeting"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO attendance (meeting_id, member_id, attended)
            VALUES (%s, %s, %s)
            ON CONFLICT (meeting_id, member_id) 
            DO UPDATE SET attended = %s
        ''', (meeting_id, member_id, attended, attended))
        conn.commit()
        _cache.clear()
        return True
    finally:
        return_db(conn)


def get_attendance_summary(meeting_id):
    """Get attendance summary for a meeting"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                COUNT(*) as total_members,
                SUM(CASE WHEN attended = 1 THEN 1 ELSE 0 END) as present_count,
                SUM(CASE WHEN attended = 0 THEN 1 ELSE 0 END) as absent_count
            FROM attendance a
            JOIN members m ON a.member_id = m.id
            WHERE a.meeting_id = %s AND m.status = 'active'
        ''', (meeting_id,))
        row = cursor.fetchone()
        return {
            'total_members': row[0] or 0,
            'present_count': row[1] or 0,
            'absent_count': row[2] or 0
        }
    finally:
        return_db(conn)


# ============= FINE OPERATIONS =============

def add_fine(member_id, amount, reason, meeting_id=None):
    """Add a fine for a member"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO fines (member_id, amount, reason, meeting_id, paid_status, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            RETURNING id
        ''', (member_id, amount, reason, meeting_id, 0))
        fine_id = cursor.fetchone()[0]
        conn.commit()
        _cache.clear()
        update_member_balance(member_id)
        return fine_id
    finally:
        return_db(conn)


def get_all_fines():
    """Get all fines with member names and numbers"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT f.*, m.name as member_name, m.member_number
            FROM fines f
            JOIN members m ON f.member_id = m.id
            ORDER BY f.created_at DESC
        ''')
        columns = ['id', 'member_id', 'amount', 'reason', 'meeting_id', 'paid_status', 'paid_date', 'created_at', 'member_name', 'member_number']
        results = []
        for row in cursor.fetchall():
            result = dict(zip(columns, row))
            if result.get('paid_date'):
                result['paid_date'] = str(result['paid_date'])
            results.append(result)
        return results
    finally:
        return_db(conn)


def get_unpaid_fines():
    """Get all unpaid fines"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT f.*, m.name as member_name, m.phone as member_phone, m.member_number
            FROM fines f
            JOIN members m ON f.member_id = m.id
            WHERE f.paid_status = 0
            ORDER BY f.created_at DESC
        ''')
        columns = ['id', 'member_id', 'amount', 'reason', 'meeting_id', 'paid_status', 'paid_date', 'created_at', 'member_name', 'member_phone', 'member_number']
        results = []
        for row in cursor.fetchall():
            result = dict(zip(columns, row))
            if result.get('paid_date'):
                result['paid_date'] = str(result['paid_date'])
            results.append(result)
        return results
    finally:
        return_db(conn)


def pay_fine(fine_id, paid_date=None):
    """Mark a fine as paid"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        paid_on = paid_date or get_current_date()
        cursor.execute('''
            UPDATE fines SET paid_status = 1, paid_date = %s
            WHERE id = %s
            RETURNING member_id
        ''', (paid_on, fine_id))
        result = cursor.fetchone()
        if result:
            member_id = result[0]
            conn.commit()
            _cache.clear()
            update_member_balance(member_id)
            return True
        return False
    finally:
        return_db(conn)


# ============= PAYOUT OPERATIONS =============

def request_payout(member_id, amount, purpose, meeting_id=None):
    """Request a payout/withdrawal"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO payouts (member_id, amount, purpose, meeting_id, status, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            RETURNING id
        ''', (member_id, amount, purpose, meeting_id, 'pending'))
        payout_id = cursor.fetchone()[0]
        conn.commit()
        _cache.clear()
        return payout_id
    finally:
        return_db(conn)


def get_all_payouts():
    """Get all payouts with member names and numbers"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.*, m.name as member_name, m.member_number
            FROM payouts p
            JOIN members m ON p.member_id = m.id
            ORDER BY p.created_at DESC
        ''')
        columns = ['id', 'member_id', 'amount', 'purpose', 'meeting_id', 'approved_by', 'status', 'payout_date', 'created_at', 'member_name', 'member_number']
        results = []
        for row in cursor.fetchall():
            result = dict(zip(columns, row))
            if result.get('payout_date'):
                result['payout_date'] = str(result['payout_date'])
            results.append(result)
        return results
    finally:
        return_db(conn)


def get_pending_payouts():
    """Get all pending payout requests"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.*, m.name as member_name, m.current_balance, m.member_number
            FROM payouts p
            JOIN members m ON p.member_id = m.id
            WHERE p.status = 'pending'
            ORDER BY p.created_at ASC
        ''')
        columns = ['id', 'member_id', 'amount', 'purpose', 'meeting_id', 'approved_by', 'status', 'payout_date', 'created_at', 'member_name', 'current_balance', 'member_number']
        results = []
        for row in cursor.fetchall():
            result = dict(zip(columns, row))
            if result.get('payout_date'):
                result['payout_date'] = str(result['payout_date'])
            results.append(result)
        return results
    finally:
        return_db(conn)


def approve_payout(payout_id, approved_by):
    """Approve a payout request"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # Get member_id and amount before updating
        cursor.execute('SELECT member_id, amount FROM payouts WHERE id = %s', (payout_id,))
        result = cursor.fetchone()
        if not result:
            return False
        
        member_id, amount = result
        
        cursor.execute('''
            UPDATE payouts SET status = %s, approved_by = %s, payout_date = %s
            WHERE id = %s
        ''', ('approved', approved_by, get_current_date(), payout_id))
        
        conn.commit()
        _cache.clear()
        
        # Update member balance
        update_member_balance(member_id)
        
        return True
    finally:
        return_db(conn)


def reject_payout(payout_id):
    """Reject a payout request"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('UPDATE payouts SET status = %s WHERE id = %s', ('rejected', payout_id))
        conn.commit()
        _cache.clear()
        return True
    finally:
        return_db(conn)


# ============= LOAN OPERATIONS =============

def request_loan(member_id, loan_amount, interest_rate, due_date, notes=None):
    """Member requests a loan"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        amount_due = loan_amount + (loan_amount * interest_rate // 100)
        remaining_balance = amount_due
        
        cursor.execute('''
            INSERT INTO loans (member_id, loan_amount, interest_rate, amount_due, remaining_balance, due_date, status, notes, issue_date, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            RETURNING id
        ''', (member_id, loan_amount, interest_rate, amount_due, remaining_balance, due_date, 'pending', notes, get_current_date()))
        
        loan_id = cursor.fetchone()[0]
        conn.commit()
        _cache.clear()
        return loan_id
    finally:
        return_db(conn)


def get_all_loans():
    """Get all loans with member names and numbers"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT l.*, m.name as member_name, m.phone as member_phone, m.member_number
            FROM loans l
            JOIN members m ON l.member_id = m.id
            ORDER BY l.created_at DESC
        ''')
        columns = ['id', 'member_id', 'loan_amount', 'interest_rate', 'amount_due', 'amount_paid', 
                  'remaining_balance', 'status', 'issue_date', 'due_date', 'approved_by', 'notes', 
                  'created_at', 'updated_at', 'member_name', 'member_phone', 'member_number']
        results = []
        for row in cursor.fetchall():
            result = dict(zip(columns, row))
            if result.get('issue_date'):
                result['issue_date'] = str(result['issue_date'])
            if result.get('due_date'):
                result['due_date'] = str(result['due_date'])
            results.append(result)
        return results
    finally:
        return_db(conn)


def get_pending_loans():
    """Get all pending loan requests"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT l.*, m.name as member_name, m.current_balance, m.member_number
            FROM loans l
            JOIN members m ON l.member_id = m.id
            WHERE l.status = 'pending'
            ORDER BY l.created_at ASC
        ''')
        columns = ['id', 'member_id', 'loan_amount', 'interest_rate', 'amount_due', 'amount_paid', 
                  'remaining_balance', 'status', 'issue_date', 'due_date', 'approved_by', 'notes', 
                  'created_at', 'updated_at', 'member_name', 'current_balance', 'member_number']
        results = []
        for row in cursor.fetchall():
            result = dict(zip(columns, row))
            if result.get('issue_date'):
                result['issue_date'] = str(result['issue_date'])
            if result.get('due_date'):
                result['due_date'] = str(result['due_date'])
            results.append(result)
        return results
    finally:
        return_db(conn)


def get_active_loans():
    """Get all active (approved but not completed) loans"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT l.*, m.name as member_name, m.member_number
            FROM loans l
            JOIN members m ON l.member_id = m.id
            WHERE l.status = 'approved'
            ORDER BY l.due_date ASC
        ''')
        columns = ['id', 'member_id', 'loan_amount', 'interest_rate', 'amount_due', 'amount_paid', 
                  'remaining_balance', 'status', 'issue_date', 'due_date', 'approved_by', 'notes', 
                  'created_at', 'updated_at', 'member_name', 'member_number']
        results = []
        for row in cursor.fetchall():
            result = dict(zip(columns, row))
            if result.get('issue_date'):
                result['issue_date'] = str(result['issue_date'])
            if result.get('due_date'):
                result['due_date'] = str(result['due_date'])
            results.append(result)
        return results
    finally:
        return_db(conn)


def approve_loan(loan_id, approved_by):
    """Approve a loan request"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE loans SET status = %s, approved_by = %s, updated_at = NOW()
            WHERE id = %s
        ''', ('approved', approved_by, loan_id))
        conn.commit()
        _cache.clear()
        return True
    finally:
        return_db(conn)


def reject_loan(loan_id):
    """Reject a loan request"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('UPDATE loans SET status = %s, updated_at = NOW() WHERE id = %s', ('rejected', loan_id))
        conn.commit()
        _cache.clear()
        return True
    finally:
        return_db(conn)


def repay_loan(loan_id, amount_paid):
    """Record loan repayment"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE loans 
            SET amount_paid = amount_paid + %s,
                remaining_balance = amount_due - (amount_paid + %s),
                updated_at = NOW()
            WHERE id = %s
            RETURNING member_id, remaining_balance
        ''', (amount_paid, amount_paid, loan_id))
        
        result = cursor.fetchone()
        if not result:
            return False
        
        member_id, remaining_balance = result
        
        # If loan is fully paid, mark as completed
        if remaining_balance <= 0:
            cursor.execute('UPDATE loans SET status = %s, updated_at = NOW() WHERE id = %s', ('completed', loan_id))
        
        conn.commit()
        _cache.clear()
        
        # Update member balance
        update_member_balance(member_id)
        
        return True
    finally:
        return_db(conn)


def get_member_loans(member_id):
    """Get loans for a specific member"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM loans WHERE member_id = %s ORDER BY created_at DESC', (member_id,))
        columns = ['id', 'member_id', 'loan_amount', 'interest_rate', 'amount_due', 'amount_paid', 
                  'remaining_balance', 'status', 'issue_date', 'due_date', 'approved_by', 'notes', 'created_at', 'updated_at']
        results = []
        for row in cursor.fetchall():
            result = dict(zip(columns, row))
            if result.get('issue_date'):
                result['issue_date'] = str(result['issue_date'])
            if result.get('due_date'):
                result['due_date'] = str(result['due_date'])
            results.append(result)
        return results
    finally:
        return_db(conn)


def get_loan_summary():
    """Get summary statistics for loans"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COALESCE(SUM(loan_amount), 0) FROM loans WHERE status IN ('pending', 'approved')")
        total_requested = cursor.fetchone()[0]
        
        cursor.execute("SELECT COALESCE(SUM(loan_amount), 0) FROM loans WHERE status = 'approved'")
        total_approved = cursor.fetchone()[0]
        
        cursor.execute("SELECT COALESCE(SUM(remaining_balance), 0) FROM loans WHERE status = 'approved'")
        total_outstanding = cursor.fetchone()[0]
        
        cursor.execute("SELECT COALESCE(SUM(amount_paid), 0) FROM loans WHERE status IN ('approved', 'completed')")
        total_repaid = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM loans WHERE status = 'pending'")
        pending_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM loans WHERE status = 'approved'")
        active_count = cursor.fetchone()[0]
        
        return {
            'total_requested': total_requested,
            'total_approved': total_approved,
            'total_outstanding': total_outstanding,
            'total_repaid': total_repaid,
            'pending_count': pending_count,
            'active_count': active_count
        }
    finally:
        return_db(conn)


# ============= EXPENSE OPERATIONS =============

def add_expense(category, amount, description, expense_date):
    """Add an expense record"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO expenses (category, amount, description, expense_date, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        ''', (category, amount, description, expense_date))
        conn.commit()
        _cache.clear()
        return True
    finally:
        return_db(conn)


def get_all_expenses(limit=100):
    """Get all expenses (non-deleted only)"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM expenses 
            WHERE deleted_at IS NULL
            ORDER BY expense_date DESC 
            LIMIT %s
        ''', (limit,))
        columns = ['id', 'category', 'amount', 'description', 'expense_date', 'created_at', 'deleted_at']
        results = []
        for row in cursor.fetchall():
            result = dict(zip(columns, row))
            if result.get('expense_date'):
                result['expense_date'] = str(result['expense_date'])
            results.append(result)
        return results
    finally:
        return_db(conn)


def soft_delete_expense(expense_id):
    """Soft delete an expense"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('UPDATE expenses SET deleted_at = NOW() WHERE id = %s', (expense_id,))
        conn.commit()
        _cache.clear()
        return True
    finally:
        return_db(conn)


# ============= DASHBOARD STATS =============

@cache_result(ttl=CACHE_TTL)
def get_dashboard_stats():
    """Get all dashboard statistics"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        # Total active members
        cursor.execute("SELECT COUNT(*) FROM members WHERE status = 'active'")
        total_members = cursor.fetchone()[0]
        
        # Total contributions
        cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM contributions")
        total_contributions = cursor.fetchone()[0]
        
        # Total payouts approved
        cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM payouts WHERE status = 'approved'")
        total_payouts = cursor.fetchone()[0]
        
        # Total unpaid fines
        cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM fines WHERE paid_status = 0")
        total_unpaid_fines = cursor.fetchone()[0]
        
        # Total expenses
        cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE deleted_at IS NULL")
        total_expenses = cursor.fetchone()[0]
        
        # Current balance
        current_balance = total_contributions - total_payouts - total_expenses - total_unpaid_fines
        
        # Members with outstanding fines
        cursor.execute('SELECT COUNT(DISTINCT member_id) FROM fines WHERE paid_status = 0')
        members_with_fines = cursor.fetchone()[0]
        
        # Loan statistics
        cursor.execute("SELECT COALESCE(SUM(loan_amount), 0) FROM loans WHERE status = 'approved'")
        total_loans_active = cursor.fetchone()[0]
        
        cursor.execute("SELECT COALESCE(SUM(remaining_balance), 0) FROM loans WHERE status = 'approved'")
        total_loan_balance = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM loans WHERE status = 'pending'")
        pending_loans = cursor.fetchone()[0]
        
        # Recent contributions
        cursor.execute('''
            SELECT c.*, m.name as member_name, m.member_number
            FROM contributions c
            JOIN members m ON c.member_id = m.id
            ORDER BY c.created_at DESC 
            LIMIT 5
        ''')
        recent_cols = ['id', 'member_id', 'receipt_number', 'amount', 'payment_method', 
                      'meeting_id', 'recorded_by', 'notes', 'contribution_date', 'created_at', 'member_name', 'member_number']
        recent_contributions = []
        for row in cursor.fetchall():
            rc = dict(zip(recent_cols, row))
            if rc.get('contribution_date'):
                rc['contribution_date'] = str(rc['contribution_date'])
            recent_contributions.append(rc)
        
        # Upcoming meetings
        cursor.execute('''
            SELECT * FROM meetings 
            WHERE meeting_date >= %s AND status = 'upcoming'
            ORDER BY meeting_date ASC 
            LIMIT 3
        ''', (get_current_date(),))
        meeting_cols = ['id', 'meeting_date', 'venue', 'agenda', 'minutes', 'status', 'created_at']
        upcoming_meetings = []
        for row in cursor.fetchall():
            um = dict(zip(meeting_cols, row))
            if um.get('meeting_date'):
                um['meeting_date'] = str(um['meeting_date'])
            upcoming_meetings.append(um)
        
        # Recent fines
        cursor.execute('''
            SELECT f.*, m.name as member_name, m.member_number
            FROM fines f
            JOIN members m ON f.member_id = m.id
            WHERE f.paid_status = 0
            ORDER BY f.created_at DESC 
            LIMIT 5
        ''')
        fine_cols = ['id', 'member_id', 'amount', 'reason', 'meeting_id', 'paid_status', 'paid_date', 'created_at', 'member_name', 'member_number']
        recent_fines = []
        for row in cursor.fetchall():
            rf = dict(zip(fine_cols, row))
            if rf.get('paid_date'):
                rf['paid_date'] = str(rf['paid_date'])
            recent_fines.append(rf)
        
        return {
            'total_members': total_members,
            'total_contributions': total_contributions,
            'total_payouts': total_payouts,
            'total_expenses': total_expenses,
            'total_unpaid_fines': total_unpaid_fines,
            'current_balance': current_balance,
            'members_with_fines': members_with_fines,
            'total_loans_active': total_loans_active,
            'total_loan_balance': total_loan_balance,
            'pending_loans': pending_loans,
            'recent_contributions': recent_contributions,
            'upcoming_meetings': upcoming_meetings,
            'recent_fines': recent_fines
        }
    finally:
        return_db(conn)


# ============= REPORT OPERATIONS =============

def get_member_statement(member_id, start_date=None, end_date=None):
    """Get complete member statement for a date range"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = get_current_date()
        
        cursor.execute('''
            SELECT 'contribution' as type, contribution_date as date, amount, receipt_number as reference, NULL as fine_reason
            FROM contributions 
            WHERE member_id = %s AND contribution_date BETWEEN %s AND %s
        ''', (member_id, start_date, end_date))
        contributions = cursor.fetchall()
        
        cursor.execute('''
            SELECT 'fine' as type, created_at::date as date, amount, reason as reference, reason as fine_reason
            FROM fines 
            WHERE member_id = %s AND created_at::date BETWEEN %s AND %s
        ''', (member_id, start_date, end_date))
        fines = cursor.fetchall()
        
        cursor.execute('''
            SELECT 'payout' as type, payout_date as date, amount, purpose as reference, NULL as fine_reason
            FROM payouts 
            WHERE member_id = %s AND status = 'approved' AND payout_date BETWEEN %s AND %s
        ''', (member_id, start_date, end_date))
        payouts = cursor.fetchall()
        
        all_transactions = list(contributions) + list(fines) + list(payouts)
        all_transactions.sort(key=lambda x: x[1] if x[1] else '')
        
        cursor.execute('SELECT name, member_number, phone, email, current_balance FROM members WHERE id = %s', (member_id,))
        member_info = cursor.fetchone()
        
        return {
            'member_name': member_info[0] if member_info else 'Unknown',
            'member_number': member_info[1] if member_info else '',
            'member_phone': member_info[2] if member_info else '',
            'member_email': member_info[3] if member_info else '',
            'current_balance': member_info[4] if member_info else 0,
            'start_date': start_date,
            'end_date': end_date,
            'transactions': all_transactions
        }
    finally:
        return_db(conn)


def get_chama_summary(start_date=None, end_date=None):
    """Get overall chama financial summary"""
    conn = get_db()
    try:
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = get_current_date()
        
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                TO_CHAR(contribution_date, 'YYYY-MM') as month,
                COUNT(*) as transaction_count,
                SUM(amount) as total
            FROM contributions
            WHERE contribution_date BETWEEN %s AND %s
            GROUP BY TO_CHAR(contribution_date, 'YYYY-MM')
            ORDER BY month DESC
        ''', (start_date, end_date))
        monthly_summary = cursor.fetchall()
        
        cursor.execute('''
            SELECT m.name, m.member_number, SUM(c.amount) as total_contributed
            FROM contributions c
            JOIN members m ON c.member_id = m.id
            WHERE c.contribution_date BETWEEN %s AND %s
            GROUP BY m.id, m.name, m.member_number
            ORDER BY total_contributed DESC
            LIMIT 10
        ''', (start_date, end_date))
        top_contributors = cursor.fetchall()
        
        cursor.execute('''
            SELECT category, SUM(amount) as total
            FROM expenses
            WHERE deleted_at IS NULL AND expense_date BETWEEN %s AND %s
            GROUP BY category
            ORDER BY total DESC
        ''', (start_date, end_date))
        expenses_by_category = cursor.fetchall()
        
        return {
            'start_date': start_date,
            'end_date': end_date,
            'monthly_summary': monthly_summary,
            'top_contributors': top_contributors,
            'expenses_by_category': expenses_by_category
        }
    finally:
        return_db(conn)