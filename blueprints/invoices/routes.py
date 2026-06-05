# blueprints/invoices/routes.py
"""Invoice routes - create, download, manage"""

from flask import Blueprint, render_template, request, send_file, jsonify, session
from services.invoice_service import process_invoice
from services.client_service import get_client_statistics, get_recent_clients_list
from database import get_db, log_communication
from utils.security import login_required
from config import DEFAULT_SERVICE_PRICES

invoices_bp = Blueprint('invoices', __name__, url_prefix='/')

@invoices_bp.route("/", methods=["GET", "POST"])
def index():
    """Main invoice page - GET shows form, POST generates PDF"""
    if request.method == "POST":
        pdf_file, invoice_number, success, error = process_invoice(request.form)
        
        if success:
            return send_file(
                pdf_file,
                as_attachment=True,
                download_name=f"invoice_{invoice_number}.pdf",
                mimetype='application/pdf'
            )
        else:
            return error, 400
    
    # GET request - show form
    recent_clients = get_recent_clients_list(5)
    stats = get_client_statistics()
    return render_template("form.html", 
                          services=DEFAULT_SERVICE_PRICES, 
                          recent_clients=recent_clients, 
                          stats=stats)

@invoices_bp.route("/api/invoice/<invoice_number>", methods=["GET"])
@login_required
def get_invoice(invoice_number):
    """Get invoice details for editing"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT sh.*, c.client_name, c.client_phone, c.client_email
            FROM service_history sh
            JOIN clients c ON sh.client_id = c.id
            WHERE sh.invoice_number = ?
        ''', (invoice_number,))
        invoice = cursor.fetchone()
        if not invoice:
            return jsonify({"error": "Invoice not found"}), 404
        return jsonify(dict(invoice))

@invoices_bp.route("/api/invoice/<invoice_number>", methods=["PUT"])
@login_required
def update_invoice(invoice_number):
    """Update existing invoice"""
    data = request.get_json()
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM service_history WHERE invoice_number = ?', (invoice_number,))
        current = cursor.fetchone()
        if not current:
            return jsonify({"error": "Invoice not found"}), 404
        
        new_amount = data.get('amount', current['amount'])
        new_paid = data.get('amount_paid', current['amount_paid'])
        new_balance = new_amount - new_paid
        
        cursor.execute('''
            UPDATE service_history 
            SET amount = ?, amount_paid = ?, balance = ?,
                payment_method = ?, notes = ?, mpesa_code = ?
            WHERE invoice_number = ?
        ''', (new_amount, new_paid, new_balance, 
              data.get('payment_method', current['payment_method']),
              data.get('notes', current['notes']),
              data.get('mpesa_code', current['mpesa_code']),
              invoice_number))
        
        if new_amount != current['amount']:
            diff = new_amount - current['amount']
            cursor.execute('''
                UPDATE clients 
                SET gross_spent = gross_spent + ?,
                    total_paid = total_paid + ?
                WHERE id = ?
            ''', (diff, new_paid - current['amount_paid'], current['client_id']))
        
        conn.commit()
        from database import _cache
        _cache.clear()
        
        log_communication(current['client_id'], 'Invoice Edit', 
                         f'Invoice {invoice_number} updated', 'Joy')
        
        return jsonify({"success": True, "new_balance": new_balance})

@invoices_bp.route("/api/invoice/<invoice_number>/pay", methods=["POST"])
@login_required
def record_payment(invoice_number):
    """Record a payment on existing invoice"""
    data = request.get_json()
    payment_amount = data.get('amount', 0)
    payment_method = data.get('payment_method', 'Cash')
    mpesa_code = data.get('mpesa_code', '')
    
    if payment_amount <= 0:
        return jsonify({"error": "Invalid payment amount"}), 400
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM service_history WHERE invoice_number = ?', (invoice_number,))
        invoice = cursor.fetchone()
        if not invoice:
            return jsonify({"error": "Invoice not found"}), 404
        
        if payment_amount > invoice['balance']:
            return jsonify({"error": "Payment exceeds balance"}), 400
        
        new_paid = invoice['amount_paid'] + payment_amount
        new_balance = invoice['balance'] - payment_amount
        
        cursor.execute('''
            UPDATE service_history 
            SET amount_paid = ?, balance = ?, payment_method = ?, mpesa_code = ?
            WHERE invoice_number = ?
        ''', (new_paid, new_balance, payment_method, mpesa_code, invoice_number))
        
        cursor.execute('''
            UPDATE clients 
            SET total_paid = total_paid + ?
            WHERE id = ?
        ''', (payment_amount, invoice['client_id']))
        
        conn.commit()
        from database import _cache
        _cache.clear()
        
        log_communication(invoice['client_id'], 'Payment', 
                         f'Payment of {payment_amount} received for invoice {invoice_number}', 'Joy')
        
        return jsonify({
            "success": True, 
            "remaining_balance": new_balance,
            "total_paid": new_paid
        })