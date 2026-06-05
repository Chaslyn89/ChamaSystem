# services/client_service.py
"""Client business logic - stats, search, profile"""

from database import (
    get_client_stats, search_clients, get_recent_clients,
    get_top_clients, get_at_risk_clients, get_client_by_id,
    update_retention_status, get_client_visits
)

def get_client_statistics():
    """Get client statistics for dashboard"""
    return get_client_stats()

def search_clients_by_term(search_term):
    """Search clients by name or phone"""
    if len(search_term) < 2 or len(search_term) > 50:
        return []
    return search_clients(search_term)

def get_recent_clients_list(limit=20):
    """Get most recent clients"""
    return get_recent_clients(limit)

def get_top_spending_clients(limit=20):
    """Get top spending clients"""
    return get_top_clients(limit)

def get_vip_clients(limit=20):
    """Get VIP clients"""
    clients = get_top_clients(limit)
    return [c for c in clients if c.get('category') == 'VIP']

def get_at_risk_clients_list():
    """Get clients needing attention"""
    update_retention_status()
    return get_at_risk_clients()

def get_complete_client_profile(client_id):
    """Get full client profile with history"""
    return get_client_by_id(client_id)

def get_client_visit_count(client_id):
    """Get total visits for a client"""
    return get_client_visits(client_id)