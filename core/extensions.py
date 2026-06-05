# core/extensions.py
"""Flask extensions initialization to prevent circular imports"""

# For now, we don't have any third-party extensions.
# This file is a placeholder for future extensions like:
# - Flask-Login for better session management
# - Flask-Migrate for database migrations
# - Flask-Mail for email invoices
# - Flask-Caching for better performance

# When you add extensions, they will be initialized here:
# from flask_sqlalchemy import SQLAlchemy
# db = SQLAlchemy()

# For now, this file just exists to make the core package work.
# Your database functions are in database.py directly.

__all__ = []