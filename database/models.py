from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Invoice(db.Model):
    __tablename__ = "invoices"

    id = db.Column(db.Integer, primary_key=True)

    # Basic info
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)

    # OCR & extracted data
    extracted_text = db.Column(db.Text)
    invoice_date = db.Column(db.String(50))
    total_amount = db.Column(db.Float)

    # New features (Stage 1)
    currency = db.Column(db.String(10), default="USD")
    category = db.Column(db.String(50), default="General")

    # 🔥 IMPORTANT FEATURE
    status = db.Column(
        db.String(20),
        default="Processed"   # Processed | Pending | Error
    )

    def __repr__(self):
        return f"<Invoice {self.id} - {self.filename}>"