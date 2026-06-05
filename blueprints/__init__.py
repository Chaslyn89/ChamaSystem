# blueprints/__init__.py
"""Blueprints package for route modules"""

from blueprints.invoices.routes import invoices_bp
from blueprints.clients.routes import clients_bp
from blueprints.expenses.routes import expenses_bp

__all__ = ['invoices_bp', 'clients_bp', 'expenses_bp']