from flask import Blueprint, render_template, request, jsonify
from utils.security import login_required
from database import get_db, return_db, add_expense, soft_delete_expense

# Create blueprint with no prefix - API routes will be at /api/expenses directly
expenses_bp = Blueprint('expenses', __name__)

@expenses_bp.route('/expenses')
@login_required
def expenses_page():
    """Expense management page"""
    return render_template('expenses.html')

@expenses_bp.route('/api/expenses')
@login_required
def api_get_expenses():
    """Get expenses with pagination and filters"""
    page = request.args.get('page', 1, type=int)
    limit = min(request.args.get('limit', 50, type=int), 100)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    offset = (page - 1) * limit
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Base query parts
    where_clauses = []
    params = []
    
    if start_date:
        where_clauses.append("expense_date >= %s")
        params.append(start_date)
    if end_date:
        where_clauses.append("expense_date <= %s")
        params.append(end_date)
    
    where_sql = ""
    if where_clauses:
        where_sql = " AND " + " AND ".join(where_clauses)
    
    # Get total count
    count_query = f"SELECT COUNT(*) FROM expenses WHERE deleted_at IS NULL{where_sql}"
    cursor.execute(count_query, params)
    total = cursor.fetchone()[0]
    
    # Get paginated results
    query = f"SELECT * FROM expenses WHERE deleted_at IS NULL{where_sql} ORDER BY expense_date DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    cursor.execute(query, params)
    
    # Get column names
    columns = [desc[0] for desc in cursor.description]
    expenses = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    return_db(conn)
    
    return jsonify({
        'expenses': expenses,
        'total': total,
        'page': page,
        'limit': limit,
        'total_pages': (total + limit - 1) // limit
    })

@expenses_bp.route('/api/expense', methods=['POST'])
@login_required
def add_expense_record():
    """Add a new expense"""
    data = request.get_json()
    category = data.get('category')
    amount = data.get('amount')
    description = data.get('description', '')
    expense_date = data.get('date')
    
    if not category or not amount or not expense_date:
        return jsonify({"error": "Category, amount, and date are required"}), 400
    
    if amount <= 0:
        return jsonify({"error": "Invalid amount"}), 400
    
    add_expense(category, amount, description, expense_date)
    
    return jsonify({"success": True})

@expenses_bp.route('/api/expense/<int:expense_id>', methods=['DELETE'])
@login_required
def delete_expense(expense_id):
    """Soft delete an expense"""
    soft_delete_expense(expense_id)
    return jsonify({"success": True})

@expenses_bp.route('/api/expense-categories')
@login_required
def get_expense_categories():
    """Get expense categories with totals"""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT category, SUM(amount) as total
            FROM expenses
            WHERE deleted_at IS NULL
            GROUP BY category
            ORDER BY total DESC
        ''')
        
        columns = ['category', 'total']
        categories = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return jsonify(categories)
    finally:
        return_db(conn)

@expenses_bp.route('/api/revenue-summary')
@login_required
def get_revenue_summary():
    """Get revenue summary for a date range"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date or not end_date:
        return jsonify({"error": "Missing date range"}), 400
    
    conn = get_db()
    try:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COALESCE(SUM(amount_paid), 0) as total_revenue 
            FROM service_history 
            WHERE service_date BETWEEN %s AND %s
        ''', (start_date, end_date))
        revenue = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COALESCE(SUM(amount), 0) as total_expenses 
            FROM expenses 
            WHERE expense_date BETWEEN %s AND %s AND deleted_at IS NULL
        ''', (start_date, end_date))
        expenses = cursor.fetchone()[0]
        
        return jsonify({
            'revenue': revenue,
            'expenses': expenses
        })
    finally:
        return_db(conn)