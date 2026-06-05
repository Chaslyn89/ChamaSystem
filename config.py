# config.py
"""Main application configuration"""

import os
from datetime import timedelta

class Config:
    """Application configuration loaded from environment variables"""
    
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    
    # Admin - MUST be set in production
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
    if not ADMIN_PASSWORD:
        print("WARNING: ADMIN_PASSWORD not set. Using default for development.")
        ADMIN_PASSWORD = 'JoyAdmin2026'
    
    # Database
    DATABASE_PATH = os.environ.get('DATABASE_PATH', 'clients.db')
    
    # Business
    BUSINESS_NAME = os.environ.get('BUSINESS_NAME', 'Joy Sisterlocks')
    BUSINESS_PHONE = os.environ.get('BUSINESS_PHONE', '+254 713 700 421')
    BUSINESS_WHATSAPP = os.environ.get('BUSINESS_WHATSAPP', '254713700421')
    BUSINESS_LOCATION = os.environ.get('BUSINESS_LOCATION', 'Mezzanine Floor, Room 8, Highway Mall, Nairobi, Kenya')
    BUSINESS_INSTAGRAM = os.environ.get('BUSINESS_INSTAGRAM', '@joysisterlocks_kenya')
    BUSINESS_EMAIL = os.environ.get('BUSINESS_EMAIL', 'joysistalocks5@gmail.com')
    
    # Tax
    VAT_RATE = float(os.environ.get('VAT_RATE', 0.16))
    
    # Loyalty
    LOYALTY_ENABLED = os.environ.get('LOYALTY_ENABLED', 'true').lower() == 'true'
    LOYALTY_VISITS_FOR_REWARD = int(os.environ.get('LOYALTY_VISITS_FOR_REWARD', 5))
    
    # Rate limiting
    MAX_LOGIN_ATTEMPTS = int(os.environ.get('MAX_LOGIN_ATTEMPTS', 5))
    LOGIN_LOCKOUT_TIME = int(os.environ.get('LOGIN_LOCKOUT_TIME', 900))

# Business dict for templates
BUSINESS = {
    'name': Config.BUSINESS_NAME,
    'phone': Config.BUSINESS_PHONE,
    'whatsapp': Config.BUSINESS_WHATSAPP,
    'location': Config.BUSINESS_LOCATION,
    'instagram': Config.BUSINESS_INSTAGRAM,
    'email': Config.BUSINESS_EMAIL
}

# Service prices (can move to database later)
DEFAULT_SERVICE_PRICES = {
    'Colour': 4500,
    'Retouch': 3500,
    'Installation': 15000
}