import os
from reportlab.pdfgen import canvas
from reportlab.lib import colors

def create_exact_baridimob_pdf(filepath, amount_str, date_str, recipient_rip, external_id):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    # Exact A4 dimensions matching pdf-receipt.pdf: [0, 0, 595, 842]
    c = canvas.Canvas(filepath, pagesize=(595, 842))
    
    # 1. Header (Centered, Helvetica 13pt)
    c.setFont("Helvetica", 13)
    c.setFillColor(colors.black)
    c.drawCentredString(595 / 2.0, 724.0, "Algeria Poste")
    c.drawCentredString(595 / 2.0, 709.0, "Receipt for operation in the system «BaridiMob»")
    
    # 2. Horizontal divider line: exactly (36, 690) to (559, 690), line width 1
    c.setLineWidth(1)
    c.setStrokeColor(colors.black)
    c.line(36, 690, 559, 690)
    
    # 3. Two-column key/value table (x=90.3 for label, x=247.2 for value, font 13pt)
    c.setFont("Helvetica", 13)
    
    # Amount
    c.drawString(90.3, 649.0, "Amount")
    c.drawString(247.2, 649.0, amount_str)
    
    # Operation date
    c.drawString(90.3, 625.5, "Operation date:")
    c.drawString(247.2, 625.5, date_str)
    
    # Recipient
    c.drawString(90.3, 602.0, "Recipient:")
    c.drawString(247.2, 602.0, recipient_rip)
    
    # Operation type
    c.drawString(90.3, 578.5, "Operation type:")
    c.drawString(247.2, 578.5, "TRANSFER")
    
    # External id
    c.drawString(90.3, 555.0, "External id:")
    c.drawString(247.2, 555.0, external_id)
    
    # 4. Footer (Centered, Helvetica 13pt)
    c.drawCentredString(595 / 2.0, 56.0, "Baridimob")
    c.drawCentredString(595 / 2.0, 36.0, "Quartier des affaires, 16024, Bab Ezzouar, Algeria")
    
    c.save()
    print(f"Generated exact replica BaridiMob receipt: {filepath}")

if __name__ == '__main__':
    base_dir = '/home/rabah/Desktop/project3/SofizAdmin/sofizAdmin_fronted/public/test_receipts'
    
    # 1. faming Test Receipt (Quota Refill - 50,000.00 DZD)
    create_exact_baridimob_pdf(
        os.path.join(base_dir, 'recu_test_faming_quota.pdf'),
        amount_str="50000.00",
        date_str="22.10.2026 15:30:00",
        recipient_rip="00799999001738866535",
        external_id="TEST-faming-99901"
    )
    
    # 2. gaming Test Receipt (Complete Lifecycle Sweep - 100,000.00 DZD)
    create_exact_baridimob_pdf(
        os.path.join(base_dir, 'recu_test_gaming_sweep.pdf'),
        amount_str="100000.00",
        date_str="22.10.2026 16:00:00",
        recipient_rip="00799999001738866535",
        external_id="TEST-gaming-88801"
    )
