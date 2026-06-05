# blueprints/clients/routes.py
"""Client routes - list, profile, search, API endpoints"""

from flask import Blueprint, render_template, jsonify, request
from services.client_service import (
    get_client_statistics, search_clients_by_term, get_recent_clients_list,
    get_top_spending_clients, get_at_risk_clients_list, get_complete_client_profile
)
from database import update_retention_status, add_client_note, add_allergy, log_communication, get_db, get_current_date
from utils.security import login_required
from utils.formatters import validate_kenyan_phone, format_phone

clients_bp = Blueprint('clients', __name__, url_prefix='/')

@clients_bp.route("/clients")
@login_required
def clients_page():
    """Client management page"""
    return render_template("clients.html")

@clients_bp.route("/client/<int:client_id>")
@login_required
def client_profile(client_id):
    """Individual client profile page"""
    profile = get_complete_client_profile(client_id)
    if not profile:
        return "Client not found", 404
    return render_template("client_profile.html", profile=profile)

# ============ API ENDPOINTS ============

@clients_bp.route("/api/stats")
@login_required
def api_stats():
    """Get client statistics"""
    stats = get_client_statistics()
    return jsonify({
        'total_clients': stats['total_clients'],
        'vip_count': stats['vip_count'],
        'regular_count': stats['regular_count'],
        'new_this_month': stats['new_this_month'],
        'gross_revenue': stats['gross_revenue'],
        'cash_collected': stats['cash_collected'],
        'outstanding': stats['outstanding'],
        'avg_visit': stats['avg_visit'],
        'at_risk': stats['at_risk'],
        'lost': stats['lost']
    })

@clients_bp.route("/api/recent")
@login_required
def api_recent():
    """Get recent clients"""
    limit = request.args.get('limit', 20, type=int)
    results = get_recent_clients_list(limit)
    return jsonify([dict(row) for row in results])

@clients_bp.route("/api/top")
@login_required
def api_top():
    """Get top spending clients"""
    limit = request.args.get('limit', 20, type=int)
    results = get_top_spending_clients(limit)
    return jsonify([dict(row) for row in results])

@clients_bp.route("/api/search")
@login_required
def api_search():
    """Search clients by name or phone"""
    query = request.args.get("q", "")
    results = search_clients_by_term(query)
    return jsonify([dict(row) for row in results])

@clients_bp.route("/api/at-risk-clients")
@login_required
def api_at_risk_clients():
    """Get at-risk clients"""
    update_retention_status()
    results = get_at_risk_clients_list()
    return jsonify([dict(row) for row in results])

# ============ CLIENT NOTE & ALLERGY API ============

@clients_bp.route("/api/client/<int:client_id>/note", methods=["POST"])
@login_required
def add_note(client_id):
    """Add a note to client profile"""
    data = request.get_json()
    note = data.get("note", "")
    add_client_note(client_id, note)
    log_communication(client_id, 'Note', f'Added note: {note[:100]}...', 'Joy')
    return jsonify({"success": True})

@clients_bp.route("/api/client/<int:client_id>/allergy", methods=["POST"])
@login_required
def add_allergy_record(client_id):
    """Add allergy record for client"""
    data = request.get_json()
    add_allergy(client_id, data.get("type"), data.get("description"), data.get("severity", "Medium"))
    return jsonify({"success": True})

# ============ EDIT & DELETE CLIENT ============

@clients_bp.route("/api/client/<int:client_id>/edit", methods=["PUT"])
@login_required
def edit_client(client_id):
    """Edit client details"""
    data = request.get_json()
    
    new_name = data.get('name', '').strip()
    new_phone = data.get('phone', '').strip()
    new_email = data.get('email', '').strip()
    
    if not new_name:
        return jsonify({"error": "Client name is required"}), 400
    if not new_phone:
        return jsonify({"error": "Phone number is required"}), 400
    
    if not validate_kenyan_phone(new_phone):
        return jsonify({"error": "Invalid Kenyan phone number"}), 400
    
    formatted_phone = format_phone(new_phone)
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check if phone number already exists for another client
        cursor.execute('SELECT id FROM clients WHERE client_phone = ? AND id != ?', (formatted_phone, client_id))
        if cursor.fetchone():
            return jsonify({"error": "Phone number already used by another client"}), 400
        
        cursor.execute('''
            UPDATE clients 
            SET client_name = ?, client_phone = ?, client_email = ?, updated_at = ?
            WHERE id = ?
        ''', (new_name, formatted_phone, new_email, get_current_date(), client_id))
        
        conn.commit()
        
        log_communication(client_id, 'Edit', f'Client details updated: {new_name}', 'Joy')
        
        return jsonify({"success": True})


@clients_bp.route("/api/client/<int:client_id>/delete", methods=["DELETE"])
@login_required
def delete_client(client_id):
    """Delete client and all associated data"""
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check if client exists
        cursor.execute('SELECT client_name FROM clients WHERE id = ?', (client_id,))
        client = cursor.fetchone()
        if not client:
            return jsonify({"error": "Client not found"}), 404
        
        # Delete will cascade to service_history, client_health, communications, appointments
        cursor.execute('DELETE FROM clients WHERE id = ?', (client_id,))
        conn.commit()
        
        from database import _cache
        _cache.clear()
        
        return jsonify({"success": True})