import os
import traceback
from flask import Flask, render_template, request, send_file, redirect, url_for, flash
from werkzeug.utils import secure_filename
from deep_translator import GoogleTranslator
from PyPDF2 import PdfReader
from docx import Document
from docx.shared import Pt
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# -------------------------
# Logging helper
# -------------------------
def log(step, *msg):
    print(f"[DEBUG] {step}:", *msg)

# -------------------------
# Config & folders
# -------------------------
ALLOWED_EXT = {'.pdf', '.docx'}
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
FONTS_FOLDER = 'fonts'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(FONTS_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = "change_this_secret"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

# Default GoogleTranslator
translator = GoogleTranslator(source='auto', target='en')

# Language dropdown
LANGUAGES = [
    ('en', 'English'), ('hi', 'Hindi'), ('bn', 'Bengali'), ('gu', 'Gujarati'),
    ('ta', 'Tamil'), ('te', 'Telugu'), ('ml', 'Malayalam'), ('fr', 'French'),
    ('de', 'German'), ('es', 'Spanish')
]

# -------------------------
# Utility functions
# -------------------------
def allowed_file(filename):
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_EXT

def extract_pdf_text(path):
    log("EXTRACT_PDF", path)
    reader = PdfReader(path)
    txt = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            txt.append(t)
    return "\n".join(txt)

def extract_docx_text(path):
    log("EXTRACT_DOCX", path)
    doc = Document(path)
    return "\n".join([p.text for p in doc.paragraphs])

def chunk_text(text, max_chars=4000):
    if len(text) <= max_chars:
        return [text]
    lines = text.splitlines(True)
    chunks, cur = [], ""
    for ln in lines:
        if len(cur) + len(ln) > max_chars:
            chunks.append(cur)
            cur = ln
        else:
            cur += ln
    if cur:
        chunks.append(cur)
    return chunks

def translate_text(text, lang):
    log("TRANSLATION", f"Target -> {lang}")
    translated = []
    for chunk in chunk_text(text):
        res = GoogleTranslator(source="auto", target=lang).translate(chunk)
        translated.append(res)
    return "\n".join(translated)

def save_as_docx(text, path):
    log("SAVE_DOCX", path)
    doc = Document()
    font = doc.styles["Normal"].font
    font.name = "NotoSans"
    font.size = Pt(12)
    for line in text.split("\n"):
        doc.add_paragraph(line)
    doc.save(path)

def register_font_if_exists(ttf_file, alias):
    font_path = os.path.join(FONTS_FOLDER, ttf_file)
    if os.path.exists(font_path):
        try:
            pdfmetrics.registerFont(TTFont(alias, font_path))
            log("FONT", f"Registered -> {alias}")
            return True
        except Exception as e:
            log("FONT_ERROR", str(e))
    return False

def save_as_pdf(text, out_file, font="Helvetica"):
    log("SAVE_PDF", out_file)
    c = canvas.Canvas(out_file)
    c.setFont(font, 12)
    width, height = 595, 842
    margin, y, lh = 40, 802, 15
    for line in text.split("\n"):
        c.drawString(margin, y, line)
        y -= lh
        if y < margin:
            c.showPage()
            c.setFont(font, 12)
            y = 802
    c.save()

# -------------------------
# Routes
# -------------------------
@app.route('/', methods=['GET', 'POST'])
def index():
    try:
        if request.method == 'POST':
            log("REQUEST", "Form submitted")

            lang = request.form.get('language')
            fmt = request.form.get('out_format', 'docx')
            file = request.files.get('file')

            log("INPUT_LANG", lang)
            log("OUTPUT_FORMAT", fmt)

            if not file or not allowed_file(file.filename):
                log("ERROR", "Invalid / no file")
                flash("Please upload PDF or DOCX file")
                return redirect('/')

            filename = secure_filename(file.filename)
            input_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(input_path)
            log("FILE_SAVED", input_path)

            # extract
            if filename.lower().endswith(".pdf"):
                text = extract_pdf_text(input_path)
            else:
                text = extract_docx_text(input_path)
            log("EXTRACTED_TEXT_LENGTH", len(text))

            if not text.strip():
                flash("No extractable text found in file. If PDF is scanned, OCR required.")
                return redirect('/')

            # translate
            translated = translate_text(text, lang)
            log("TRANSLATED_TEXT_LENGTH", len(translated))

            base = os.path.splitext(filename)[0]
            out_file = f"{secure_filename(base)}_translated_{lang}.{fmt}"
            out_path = os.path.join(OUTPUT_FOLDER, out_file)

            if fmt == "docx":
                save_as_docx(translated, out_path)
            else:
                registered = register_font_if_exists("NotoSansDevanagari-Regular.ttf", "NotoDeva")
                save_as_pdf(translated, out_path, font=("NotoDeva" if registered else "Helvetica"))

            log("OUTPUT_SAVED", out_path)
            return render_template("result.html", download_url=url_for('download_file', filename=out_file))

        return render_template("index.html", languages=LANGUAGES)

    except Exception as e:
        log("FATAL_ERROR", str(e))
        traceback.print_exc()
        flash("CRITICAL ERROR: " + str(e))
        return redirect('/')

@app.route('/download/<filename>')
def download_file(filename):
    path = os.path.join(OUTPUT_FOLDER, filename)
    if os.path.exists(path):
        log("DOWNLOAD", path)
        return send_file(path, as_attachment=True)
    else:
        flash("File not found.")
        return redirect('/')

# -------------------------
# Main
# -------------------------
if __name__ == '__main__':
    log("SERVER", "App started on http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
