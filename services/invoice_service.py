# services/invoice_service.py
"""Invoice business logic - creation, PDF generation, calculations"""

from datetime import datetime
import io
from flask import render_template

from database import (
    get_or_create_client, save_service_record, get_client_visits,
    generate_invoice_number, log_communication
)
from utils.formatters import calculate_vat_inclusive, format_phone
from utils.loyalty import calculate_loyalty_stars, get_reward_message
from utils.qrcode import generate_qr_code
from config import BUSINESS, DEFAULT_SERVICE_PRICES

def process_invoice(form_data):
    """
    Process invoice from form data and generate PDF
    
    Returns:
        tuple: (pdf_file, invoice_number, success, error_message)
    """
    # Extract form data
    client_name = form_data.get("client_name", "").strip()
    client_phone = form_data.get("client_phone", "").strip()
    client_email = form_data.get("client_email", "").strip()
    
    # Process services
    service_names_raw = form_data.getlist("service_name[]")
    service_prices = form_data.getlist("service_price[]")
    
    service_names = []
    for i, name in enumerate(service_names_raw):
        if name == "Other":
            custom_name = form_data.get(f"other_service_name_{i+1}", "")
            service_names.append(custom_name if custom_name else name)
        else:
            service_names.append(name)
    
    # Validation
    if not client_name:
        return None, None, False, "Client name is required"
    if not client_phone:
        return None, None, False, "Phone number is required"
    if not service_names or not service_names[0]:
        return None, None, False, "Please select at least one service"
    
    # Calculate totals
    total_amount = 0
    services_list = []
    for i, name in enumerate(service_names):
        if name and i < len(service_prices):
            price = int(service_prices[i]) if service_prices[i] else 0
            total_amount += price
            services_list.append({"name": name, "price": price})
    
    # VAT calculation
    subtotal, vat_amount = calculate_vat_inclusive(total_amount)
    
    # Payment details
    appointment_date = form_data.get("appointment_date", "")
    payment_method = form_data.get("payment_method", "Cash")
    amount_paid = form_data.get("amount_paid", 0)
    notes = form_data.get("notes", "")
    mpesa_code = form_data.get("mpesa_code", "")
    
    try:
        amount_paid_int = int(amount_paid) if amount_paid else 0
    except ValueError:
        amount_paid_int = 0
    
    balance = total_amount - amount_paid_int
    formatted_phone = format_phone(client_phone)
    invoice_number = generate_invoice_number()
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    # Save client and record
    client_data = {
        'client_name': client_name,
        'client_phone': formatted_phone,
        'client_email': client_email
    }
    client_id = get_or_create_client(client_data)
    client_visits = get_client_visits(client_id)
    
    invoice_data = {
        'invoice_number': invoice_number,
        'date': current_date,
        'service_name': ", ".join([s["name"] for s in services_list]),
        'service_details': "",
        'total': total_amount,
        'amount_paid': amount_paid_int,
        'balance': balance,
        'payment_method': payment_method,
        'stylist_name': 'Joy',
        'notes': notes,
        'mpesa_code': mpesa_code
    }
    save_service_record(client_id, invoice_data)
    log_communication(client_id, 'Invoice', f'Invoice {invoice_number} generated', 'Joy')
    
    # Generate HTML for PDF
    loyalty_stars = calculate_loyalty_stars(client_visits + 1)
    reward_message = get_reward_message(client_visits + 1)
    whatsapp_url = f"https://wa.me/{BUSINESS['whatsapp']}"
    qr_code_url = generate_qr_code(whatsapp_url)
    
    html = render_template("invoice.html",
        invoice_number=invoice_number,
        date=current_date,
        client_name=client_name,
        client_phone=formatted_phone,
        service_name=", ".join([s["name"] for s in services_list]),
        service_details="",
        appointment_date=appointment_date,
        total=total_amount,
        amount_paid=amount_paid_int,
        balance=balance,
        payment_method=payment_method,
        notes=notes,
        stylist_name="Joy",
        mpesa_code=mpesa_code,
        services_list=services_list,
        subtotal=subtotal,
        vat_amount=vat_amount,
        total_with_vat=total_amount,
        loyalty_stars=loyalty_stars,
        reward_message=reward_message,
        qr_code_url=qr_code_url,
        business=BUSINESS,
        client_visits=client_visits + 1
    )
    
    # Try to generate PDF, fallback to HTML if WeasyPrint fails
    try:
        from weasyprint import HTML
        pdf_file = io.BytesIO()
        HTML(string=html).write_pdf(pdf_file)
        pdf_file.seek(0)
        return pdf_file, invoice_number, True, None
    except ImportError:
        # WeasyPrint not available - return HTML as fallback
        return None, invoice_number, False, "PDF generation not available. Please install GTK+ libraries."
    except Exception as e:
        return None, None, False, f"Error generating PDF: {str(e)}"