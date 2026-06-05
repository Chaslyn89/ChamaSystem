# services/expense_service.py
"""Expense business logic - add, get, delete, analytics"""

from database import (
    add_expense, get_expenses, soft_delete_expense,
    get_expenses_by_category, get_profit_summary
)

def create_expense(category, amount, description, expense_date):
    """Add a new expense"""
    if amount <= 0:
        return False, "Amount must be greater than 0"
    add_expense(category, amount, description, expense_date)
    return True, None

def get_expense_list(limit=50):
    """Get recent expenses"""
    return get_expenses(limit)

def delete_expense(expense_id):
    """Soft delete an expense"""
    soft_delete_expense(expense_id)
    return True

def get_category_breakdown():
    """Get expenses grouped by category"""
    return get_expenses_by_category()

def get_monthly_profit_summary():
    """Get profit summary by month"""
    return get_profit_summary()

def calculate_total_expenses(expenses):
    """Calculate total from expense list"""
    return sum(e.get('amount', 0) for e in expenses)