import os
from flask import Flask, render_template, request, send_file, redirect, url_for, flash
from werkzeug.utils import secure_filename
from deep_translator import GoogleTranslator
from PyPDF2 import PdfReader
from docx import Document
from docx.shared import Pt
from fpdf import FPDF  # PDF generation

# ----------------- CONFIGURATION -----------------
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXT = {'.pdf', '.docx'}  # Allowed uploads
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ----------------- HELPERS -----------------
def allowed_file(filename):
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_EXT

def extract_pdf_text(path):
    print("Extracting PDF text from:", path)
    text = ''
    reader = PdfReader(path)
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + '\n'
    return text

def read_docx(file_path):
    print("Reading DOCX:", file_path)
    doc = Document(file_path)
    text = ''
    for para in doc.paragraphs:
        text += para.text + '\n'
    return text

def write_docx(text, filename):
    print("Writing DOCX:", filename)
    doc = Document()
    for line in text.split('\n'):
        para = doc.add_paragraph(line)
        para.style.font.size = Pt(12)
    doc.save(filename)

def write_pdf(text, filename):
    print("Writing PDF:", filename)
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", size=12)
    for line in text.split('\n'):
        pdf.multi_cell(0, 10, line)
    pdf.output(filename)

# ----------------- ROUTES -----------------
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        print("POST request received")
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            print("File saved:", file_path)

            # Read file content
            _, ext = os.path.splitext(filename.lower())
            if ext == '.pdf':
                text = extract_pdf_text(file_path)
            else:  # .docx
                text = read_docx(file_path)

            # Translate text
            target_lang = request.form.get('language', 'en')
            print(f"Translating to {target_lang}...")
            translated_text = GoogleTranslator(source='auto', target=target_lang).translate(text)

            # Output format
            output_format = request.form.get('format', 'docx')  # default DOCX
            base_name = filename.rsplit('.', 1)[0]
            translated_filename = f"translated_{base_name}.{output_format}"
            translated_path = os.path.join(app.config['UPLOAD_FOLDER'], translated_filename)

            if output_format == 'pdf':
                write_pdf(translated_text, translated_path)
            else:
                write_docx(translated_text, translated_path)

            print("Translation complete")
            return send_file(translated_path, as_attachment=True)
        else:
            flash('File type not allowed')
            return redirect(request.url)
    return render_template('index.html')

# ----------------- MAIN -----------------
if __name__ == '__main__':
    app.run(debug=True)
