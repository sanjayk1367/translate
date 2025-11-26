import os
from flask import Flask, render_template, request, send_file, redirect, url_for, flash
from werkzeug.utils import secure_filename
from deep_translator import GoogleTranslator
from PyPDF2 import PdfReader
from docx import Document
from docx.shared import Pt
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


from deep_translator import GoogleTranslator

def translate_text(text, dest_lang):
    translated_chunks = []
    for ch in chunk_text(text):
        translated_chunks.append(
            GoogleTranslator(source="auto", target=dest_lang).translate(ch)
        )
    return "\n".join(translated_chunks)


ALLOWED_EXT = {'.pdf', '.docx'}
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
FONTS_FOLDER = 'fonts'  # optional: place TTF fonts here for Unicode PDFs

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(FONTS_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = "change_this_secret_in_prod"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

translator = Translator()

# --- Utility functions --- #

def allowed_file(filename):
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_EXT

def extract_pdf_text(path):
    reader = PdfReader(path)
    text_parts = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_parts.append(page_text)
    return "\n".join(text_parts)

def extract_docx_text(path):
    doc = Document(path)
    parts = []
    for para in doc.paragraphs:
        parts.append(para.text)
    return "\n".join(parts)

def chunk_text(text, max_chars=4000):
    """Split text into chunks not exceeding max_chars (preserving whole lines when possible)."""
    if len(text) <= max_chars:
        return [text]
    lines = text.splitlines(True)
    chunks = []
    cur = ""
    for ln in lines:
        if len(cur) + len(ln) > max_chars:
            if cur:
                chunks.append(cur)
            cur = ln
        else:
            cur += ln
    if cur:
        chunks.append(cur)
    return chunks

def translate_text(text, dest_lang):
    """Translate large text by chunking to avoid limits."""
    chunks = chunk_text(text, max_chars=4000)
    translated_chunks = []
    for ch in chunks:
        # googletrans Translator may accept strings up to a limit; chunking reduces errors
        res = translator.translate(ch, dest=dest_lang)
        translated_chunks.append(res.text)
    return "\n".join(translated_chunks)

def save_as_docx(text, out_path, font_name='NotoSans'):  # font_name used for style, may vary by system
    doc = Document()
    style = doc.styles['Normal']
    font = style.font
    font.name = font_name
    font.size = Pt(12)

    for para_text in text.split('\n'):
        doc.add_paragraph(para_text)
    doc.save(out_path)

def register_font_if_exists(ttf_filename, font_alias):
    """If the TTF exists in fonts folder, register with reportlab and return True."""
    path = os.path.join(FONTS_FOLDER, ttf_filename)
    if os.path.exists(path):
        try:
            pdfmetrics.registerFont(TTFont(font_alias, path))
            return True
        except Exception as e:
            print("Font register failed:", e)
            return False
    return False

def save_as_pdf_unicode(text, out_path, font_alias='NotoDeva', fallback_font='Helvetica'):
    """
    Save text to PDF. If a registered TrueType font alias is available, use it for Unicode.
    Otherwise use default (may not render Indic scripts correctly).
    """
    use_font = fallback_font
    if font_alias in pdfmetrics.getRegisteredFontNames():
        use_font = font_alias

    c = canvas.Canvas(out_path)
    c.setFont(use_font, 12)
    width, height = 595, 842  # A4 approx
    margin = 40
    y = height - margin
    line_height = 14

    for paragraph in text.split('\n'):
        # simple word-wrapping
        words = paragraph.split(' ')
        line = ""
        for w in words:
            test_line = (line + ' ' + w).strip()
            if c.stringWidth(test_line, use_font, 12) > (width - 2 * margin):
                c.drawString(margin, y, line)
                y -= line_height
                line = w
                if y < margin:
                    c.showPage()
                    c.setFont(use_font, 12)
                    y = height - margin
            else:
                line = test_line
        # draw last line
        if line:
            c.drawString(margin, y, line)
            y -= line_height
        # extra gap after paragraph
        y -= 4
        if y < margin:
            c.showPage()
            c.setFont(use_font, 12)
            y = height - margin

    c.save()


# --- Routes --- #

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        lang = request.form.get('language')
        file = request.files.get('file')
        out_format = request.form.get('out_format', 'docx')  # 'docx' or 'pdf'

        if not file or file.filename == '':
            flash("No file selected")
            return redirect(request.url)

        filename = secure_filename(file.filename)
        if not allowed_file(filename):
            flash("Unsupported file type. Allowed: .pdf, .docx")
            return redirect(request.url)

        input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(input_path)

        # Extract text
        try:
            if filename.lower().endswith('.pdf'):
                text = extract_pdf_text(input_path)
            else:
                text = extract_docx_text(input_path)
        except Exception as e:
            flash("Error extracting text: " + str(e))
            return redirect(request.url)

        if not text.strip():
            flash("No extractable text found in the file. If the PDF is scanned, OCR is required.")
            return redirect(request.url)

        # Translate
        try:
            translated = translate_text(text, lang)
        except Exception as e:
            flash("Translation failed: " + str(e))
            return redirect(request.url)

        base_name = os.path.splitext(filename)[0]
        safe_base = secure_filename(base_name)
        if out_format == 'docx':
            out_filename = f"{safe_base}_translated_{lang}.docx"
            out_path = os.path.join(app.config['OUTPUT_FOLDER'], out_filename)
            save_as_docx(translated, out_path)
        else:
            # Try to register a font (user can place a TTF in fonts/ directory and name it here)
            # Example: place 'NotoSansDevanagari-Regular.ttf' in fonts/ and call register_font_if_exists with that name.
            # We'll attempt common fonts if present.
            # You can change ttf_name to the actual file you put in fonts folder.
            ttf_name = 'NotoSansDevanagari-Regular.ttf'
            registered = register_font_if_exists(ttf_name, 'NotoDeva')
            out_filename = f"{safe_base}_translated_{lang}.pdf"
            out_path = os.path.join(app.config['OUTPUT_FOLDER'], out_filename)
            if registered:
                save_as_pdf_unicode(translated, out_path, font_alias='NotoDeva')
            else:
                # fallback: use default font (may not render complex scripts)
                save_as_pdf_unicode(translated, out_path, font_alias='Helvetica')

        return render_template('result.html', download_url=url_for('download_file', filename=out_filename))

    # GET
    languages = [
        ('en', 'English'), ('hi', 'Hindi'), ('bn', 'Bengali'), ('gu', 'Gujarati'),
        ('ta', 'Tamil'), ('te', 'Telugu'), ('ml', 'Malayalam'), ('fr', 'French'),
        ('de', 'German'), ('es', 'Spanish')
    ]
    return render_template('index.html', languages=languages)


@app.route('/download/<path:filename>')
def download_file(filename):
    path = os.path.join(app.config['OUTPUT_FOLDER'], filename)
    if os.path.exists(path):
        return send_file(path, as_attachment=True)
    else:
        flash("File not found")
        return redirect(url_for('index'))


if __name__ == '__main__':
    # debug=True only for development
    app.run(host='0.0.0.0', port=5000, debug=True)
