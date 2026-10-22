import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors

def create_baridimob_pdf(filepath, amount_str, date_str, recipient_rip, external_id, title_note=""):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    c = canvas.Canvas(filepath, pagesize=A4)
    width, height = A4
    
    # Background and Border
    c.setStrokeColor(colors.HexColor('#003366'))
    c.setLineWidth(1.5)
    c.roundRect(40, 160, width - 80, height - 200, 12, stroke=1, fill=0)
    
    # Top Header
    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(colors.HexColor('#003366'))
    c.drawString(60, height - 75, "Algerie Poste")
    
    c.setFont("Helvetica", 11)
    c.setFillColor(colors.HexColor('#555555'))
    c.drawString(60, height - 95, "Receipt for operation in the system «BaridiMob»")
    
    # Decorative line
    c.setStrokeColor(colors.HexColor('#e2e8f0'))
    c.setLineWidth(1)
    c.line(60, height - 110, width - 60, height - 110)
    
    y = height - 145
    
    # Amount
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.HexColor('#64748b'))
    c.drawString(60, y, "Amount")
    y -= 25
    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(colors.HexColor('#0f172a'))
    c.drawString(60, y, f"{amount_str} DZD")
    y -= 40
    
    # Operation Date
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.HexColor('#64748b'))
    c.drawString(60, y, "Operation date:")
    y -= 20
    c.setFont("Helvetica", 12)
    c.setFillColor(colors.HexColor('#1e293b'))
    c.drawString(60, y, date_str)
    y -= 35
    
    # Recipient
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.HexColor('#64748b'))
    c.drawString(60, y, "Recipient:")
    y -= 20
    c.setFont("Helvetica", 12)
    c.setFillColor(colors.HexColor('#1e293b'))
    c.drawString(60, y, recipient_rip)
    y -= 35
    
    # Operation Type
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.HexColor('#64748b'))
    c.drawString(60, y, "Operation type:")
    y -= 20
    c.setFont("Helvetica", 12)
    c.setFillColor(colors.HexColor('#1e293b'))
    c.drawString(60, y, "TRANSFER")
    y -= 35
    
    # External ID
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.HexColor('#64748b'))
    c.drawString(60, y, "External id:")
    y -= 20
    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(colors.HexColor('#0284c7'))
    c.drawString(60, y, external_id)
    y -= 35
    
    # Standard Fee
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.HexColor('#64748b'))
    c.drawString(60, y, "Fee:")
    y -= 20
    c.setFont("Helvetica", 12)
    c.setFillColor(colors.HexColor('#1e293b'))
    c.drawString(60, y, "50.00 DZD")
    y -= 45
    
    if title_note:
        c.setFont("Helvetica-Oblique", 10)
        c.setFillColor(colors.HexColor('#b45309'))
        c.drawString(60, y, f"Note: {title_note}")
        y -= 35
        
    # Footer
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor('#003366'))
    c.drawString(60, 200, "Baridimob")
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor('#64748b'))
    c.drawString(60, 185, "Quartier des affaires, 16024, Bab Ezzouar, Algeria")
    
    c.save()
    print(f"Generated test receipt: {filepath}")

if __name__ == '__main__':
    base_dir = '/home/rabah/Desktop/project3/SofizAdmin/sofizAdmin_fronted/public/test_receipts'
    
    # 1. Walid Test Receipt (Quota Refill)
    create_baridimob_pdf(
        os.path.join(base_dir, 'recu_test_walid_quota.pdf'),
        amount_str="50000.00",
        date_str="22.10.2026 15:30:00",
        recipient_rip="00799999001738866535",
        external_id="TEST-WALID-99901",
        title_note="Test Quota Refill by Treasury Officer Walid"
    )
    
    # 2. Salah Test Receipt (Complete Lifecycle Sweep)
    create_baridimob_pdf(
        os.path.join(base_dir, 'recu_test_salah_sweep.pdf'),
        amount_str="100000.00",
        date_str="22.10.2026 16:00:00",
        recipient_rip="00799999001738866535",
        external_id="TEST-SALAH-88801",
        title_note="Test Operational Sweep & Withdrawal by Salah Account"
    )
