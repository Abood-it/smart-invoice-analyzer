from flask import Flask, render_template, request, redirect, url_for, send_file
from config import Config
from database.models import db, Invoice
import os, re
from datetime import datetime
import pandas as pd
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
from pdf2image import convert_from_path

app = Flask(__name__)
app.config.from_object(Config)

# =========================
# DATABASE INIT
# =========================
db.init_app(app)
with app.app_context():
    db.create_all()

# =========================
# OCR (AR + EN) – ENHANCED ✨
# =========================
def extract_text(file_path):

    def preprocess(img):
        # 1️⃣ تحويل إلى رمادي
        img = img.convert("L")

        # 2️⃣ زيادة التباين
        img = ImageEnhance.Contrast(img).enhance(3.0)

        # 3️⃣ تنعيم خفيف لإزالة التشويش
        img = img.filter(ImageFilter.MedianFilter(size=3))

        # 4️⃣ Sharpen
        img = img.filter(ImageFilter.SHARPEN)

        return img

    custom_config = r"""
        --oem 3
        --psm 6
        -c preserve_interword_spaces=1
    """

    text = ""

    # PDF
    if file_path.lower().endswith(".pdf"):
        pages = convert_from_path(file_path, dpi=400)
        for page in pages:
            page = preprocess(page)
            text += pytesseract.image_to_string(
                page,
                lang="ara+eng",
                config=custom_config
            )
        return text.strip()

    # Image
    img = Image.open(file_path)
    img = preprocess(img)

    text = pytesseract.image_to_string(
        img,
        lang="ara+eng",
        config=custom_config
    )

    return text.strip()

# =========================
# DATA EXTRACTION
# =========================
def extract_date(text):
    arabic_digits = "٠١٢٣٤٥٦٧٨٩"
    english_digits = "0123456789"
    text = text.translate(str.maketrans(arabic_digits, english_digits))

    patterns = [
        r"(20\d{2})[-/\.](0?[1-9]|1[0-2])[-/\.](0?[1-9]|[12]\d|3[01])",
        r"(0?[1-9]|[12]\d|3[01])[-/\.](0?[1-9]|1[0-2])[-/\.](20\d{2})",
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+20\d{2}",
        r"(تاريخ|التاريخ)\s*[:\-]?\s*(20\d{2}[-/\.]\d{1,2}[-/\.]\d{1,2})",
    ]

    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
                try:
                    clean = re.sub(r"[^\d/-]", "", m.group())
                    return datetime.strptime(clean, fmt).date().isoformat()
                except:
                    pass
    return "Not Found"

def extract_amount(text):
    arabic_digits = "٠١٢٣٤٥٦٧٨٩"
    english_digits = "0123456789"
    text = text.translate(str.maketrans(arabic_digits, english_digits))
    text = text.replace(",", "").replace("٫", ".")

    keywords = ["TOTAL", "AMOUNT", "GRAND TOTAL", "المجموع", "الإجمالي", "الاجمالي", "المبلغ"]
    amounts = []

    for line in text.splitlines():
        if any(k in line.upper() for k in keywords):
            for n in re.findall(r"\d+(?:\.\d{1,2})?", line):
                try:
                    amounts.append(float(n))
                except:
                    pass

    if amounts:
        return max(amounts)

    fallback = re.findall(r"\d+(?:\.\d{1,2})?", text)
    return float(fallback[-1]) if fallback else 0.0

def detect_currency(text):
    text = text.upper()
    text = text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))

    if any(k in text for k in ["IQD", "دينار", "د.ع"]):
        return "IQD"
    if any(k in text for k in ["USD", "$", "دولار"]):
        return "USD"

    for n in re.findall(r"\d+(?:\.\d+)?", text):
        try:
            if float(n) >= 10000:
                return "IQD"
        except:
            pass

    return "USD"

def classify_category(text):
    t = text.lower()
    if "electric" in t or "كهرباء" in t:
        return "Electricity"
    if "internet" in t or "انترنت" in t:
        return "Internet"
    if "water" in t or "ماء" in t:
        return "Water"
    if "shop" in t or "سوبر" in t:
        return "Shopping"
    return "General"

def detect_language(text):
    return "ar" if re.search(r"[ء-ي]", text) else "en"

# =========================
# UPLOAD
# =========================
@app.route("/", methods=["GET", "POST"])
def upload_invoice():
    if request.method == "POST":
        file = request.files["invoice"]
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
        file.save(path)

        text = extract_text(path)

        invoice = Invoice(
            filename=file.filename,
            file_path=path,
            extracted_text=text,
            invoice_date=extract_date(text),
            total_amount=extract_amount(text),
            currency=detect_currency(text),
            category=classify_category(text),
            status="Processed"
        )

        db.session.add(invoice)
        db.session.commit()
        return redirect(url_for("dashboard"))

    return render_template("upload.html")

# =========================
# DASHBOARD
# =========================
@app.route("/dashboard")
def dashboard():
    invoices = Invoice.query.order_by(Invoice.upload_date.desc()).all()
    total_usd = sum(i.total_amount for i in invoices if i.currency == "USD")
    total_iqd = sum(i.total_amount for i in invoices if i.currency == "IQD")

    return render_template(
        "dashboard.html",
        invoices=invoices,
        total_usd=total_usd,
        total_iqd=total_iqd
    )

# =========================
# EDIT (FIXED ✅)
# =========================
@app.route("/edit/<int:invoice_id>", methods=["GET", "POST"])
def edit_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)

    if request.method == "POST":

        amount_iqd = request.form.get("amount_iqd", "").strip()
        amount_usd = request.form.get("amount_usd", "").strip()

        # إذا أدخل دينار وتغيّر فعلاً
        if amount_iqd and (
            invoice.currency != "IQD"
            or float(amount_iqd) != invoice.total_amount
        ):
            invoice.total_amount = float(amount_iqd)
            invoice.currency = "IQD"

        # إذا أدخل دولار وتغيّر فعلاً
        elif amount_usd and (
            invoice.currency != "USD"
            or float(amount_usd) != invoice.total_amount
        ):
            invoice.total_amount = float(amount_usd)
            invoice.currency = "USD"

        # Category
        category = request.form.get("category")
        if category:
            invoice.category = category

        # Status
        status = request.form.get("status")
        if status:
            invoice.status = status

        db.session.commit()
        return redirect(url_for("dashboard"))

    return render_template("edit.html", invoice=invoice)



# =========================
# EXPORT EXCEL
# =========================
@app.route("/export-excel/<int:invoice_id>")
def export_single_invoice_excel(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    lang = detect_language(invoice.extracted_text)

    if lang == "ar":
        df = pd.DataFrame([{
            "اسم الملف": invoice.filename,
            "تاريخ الفاتورة": invoice.invoice_date,
            "المبلغ": invoice.total_amount,
            "العملة": "دينار عراقي" if invoice.currency == "IQD" else "دولار",
            "التصنيف": invoice.category,
            "الحالة": "تمت المعالجة"
        }])
    else:
        df = pd.DataFrame([{
            "Filename": invoice.filename,
            "Invoice Date": invoice.invoice_date,
            "Amount": invoice.total_amount,
            "Currency": invoice.currency,
            "Category": invoice.category,
            "Status": invoice.status
        }])

    file_name = f"invoice_{invoice.id}.xlsx"
    df.to_excel(file_name, index=False)
    return send_file(file_name, as_attachment=True)

# =========================
# DELETE
# =========================
@app.route("/delete/<int:invoice_id>", methods=["POST"])
def delete_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    db.session.delete(invoice)
    db.session.commit()
    return redirect(url_for("dashboard"))

# =========================
# PREVIEW FILE
# =========================
@app.route("/preview/<int:invoice_id>")
def preview(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    return send_file(invoice.file_path)

# =========================
# VIEW OCR TEXT
# =========================
@app.route("/ocr/<int:invoice_id>")
def view_ocr(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)

    lang = detect_language(invoice.extracted_text)

    return render_template(
        "ocr.html",
        invoice=invoice,
        ocr_text=invoice.extracted_text,
        lang=lang
    )
# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)