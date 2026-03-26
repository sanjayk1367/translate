import os
import io
import textwrap
import subprocess
import tempfile
from pathlib import Path

import pymupdf
from flask import Flask, render_template, request, send_file, redirect, url_for, flash
from werkzeug.utils import secure_filename
from deep_translator import GoogleTranslator
from PyPDF2 import PdfReader
from docx import Document
from docx.shared import Pt
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
OUTPUT_FOLDER = BASE_DIR / "output"
TEMPLATES_FOLDER = BASE_DIR / "templates"

ALLOWED_EXTENSIONS = {".pdf", ".docx"}

UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)
TEMPLATES_FOLDER.mkdir(exist_ok=True)

app = Flask(__name__, template_folder=str(TEMPLATES_FOLDER))
app.secret_key = "change-this-secret-key"

app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["OUTPUT_FOLDER"] = str(OUTPUT_FOLDER)

TESSERACT_PATH = os.environ.get(
    "TESSERACT_PATH",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


def debug(msg: str) -> None:
    print(f"[DEBUG] {msg}")


def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def extract_text_from_pdf(file_path: str) -> str:
    debug(f"Trying normal PDF extraction: {file_path}")
    text_parts = []
    reader = PdfReader(file_path)

    for i, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        debug(f"Page {i}: extracted {len(page_text)} chars")
        if page_text.strip():
            text_parts.append(page_text)

    return "\n".join(text_parts).strip()


def run_tesseract_on_png(png_path: str, lang: str = "eng+hin") -> str:
    if not Path(TESSERACT_PATH).exists():
        raise RuntimeError(
            f"Tesseract not found at: {TESSERACT_PATH}. "
            "Install Tesseract OCR or set TESSERACT_PATH."
        )

    command = [
        TESSERACT_PATH,
        png_path,
        "stdout",
        "-l",
        lang,
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore"
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Tesseract OCR failed.")

    return result.stdout.strip()


def ocr_extract_text_from_pdf(file_path: str) -> str:
    debug(f"Trying OCR with PyMuPDF: {file_path}")
    text_parts = []

    with pymupdf.open(file_path) as doc:
        with tempfile.TemporaryDirectory() as temp_dir:
            for i, page in enumerate(doc, start=1):
                pix = page.get_pixmap(dpi=300)
                png_path = Path(temp_dir) / f"page_{i}.png"
                pix.save(str(png_path))

                debug(f"OCR page {i}")
                text = run_tesseract_on_png(str(png_path), lang="eng+hin")
                if text.strip():
                    text_parts.append(text)

    return "\n".join(text_parts).strip()


def extract_text_from_docx(file_path: str) -> str:
    debug(f"Reading DOCX: {file_path}")
    doc = Document(file_path)
    text_parts = []

    for para in doc.paragraphs:
        if para.text.strip():
            text_parts.append(para.text)

    return "\n".join(text_parts).strip()


def translate_long_text(text: str, target_lang: str) -> str:
    debug(f"Translating to: {target_lang}")

    if not text.strip():
        raise ValueError("No readable text found in file.")

    chunk_size = 3000
    chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
    translated_chunks = []

    for idx, chunk in enumerate(chunks, start=1):
        debug(f"Translating chunk {idx}/{len(chunks)}")
        translated = GoogleTranslator(source="auto", target=target_lang).translate(chunk)
        translated_chunks.append(translated if translated else "")

    return "\n".join(translated_chunks)


def write_docx(text: str, output_path: str) -> None:
    debug(f"Writing DOCX: {output_path}")
    doc = Document()

    for line in text.splitlines():
        para = doc.add_paragraph()
        run = para.add_run(line)
        run.font.size = Pt(12)

    doc.save(output_path)


def register_font() -> str:
    candidates = [
        BASE_DIR / "fonts" / "DejaVuSans.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/arialuni.ttf"),
        Path("C:/Windows/Fonts/Nirmala.ttf"),
    ]

    for font_path in candidates:
        if font_path.exists():
            try:
                pdfmetrics.registerFont(TTFont("CustomUnicode", str(font_path)))
                debug(f"Using font: {font_path}")
                return "CustomUnicode"
            except Exception as e:
                debug(f"Font register failed: {e}")

    debug("Using fallback font: Helvetica")
    return "Helvetica"


def write_pdf(text: str, output_path: str) -> None:
    debug(f"Writing PDF: {output_path}")

    font_name = register_font()
    pdf = canvas.Canvas(output_path, pagesize=A4)
    _, height = A4

    left_margin = 40
    top_margin = height - 50
    bottom_margin = 50
    line_height = 16
    max_chars = 90

    pdf.setTitle("Translated PDF")
    pdf.setFont(font_name, 11)

    y = top_margin

    for paragraph in text.splitlines():
        wrapped_lines = textwrap.wrap(paragraph, width=max_chars) or [""]

        for line in wrapped_lines:
            if y < bottom_margin:
                pdf.showPage()
                pdf.setFont(font_name, 11)
                y = top_margin

            pdf.drawString(left_margin, y, line)
            y -= line_height

        y -= 4

    pdf.save()


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        debug("Form submitted")

        if "file" not in request.files:
            flash("No file selected.")
            return redirect(url_for("index"))

        file = request.files["file"]
        target_lang = request.form.get("language", "en").strip()
        output_format = request.form.get("format", "pdf").strip().lower()

        if file.filename == "":
            flash("Please choose a file.")
            return redirect(url_for("index"))

        if not allowed_file(file.filename):
            flash("Only PDF and DOCX files are allowed.")
            return redirect(url_for("index"))

        if output_format not in {"pdf", "docx"}:
            flash("Invalid output format.")
            return redirect(url_for("index"))

        filename = secure_filename(file.filename)
        input_path = UPLOAD_FOLDER / filename
        file.save(input_path)

        debug(f"Uploaded file saved: {input_path}")

        try:
            ext = input_path.suffix.lower()

            if ext == ".pdf":
                extracted_text = extract_text_from_pdf(str(input_path))
                if not extracted_text.strip():
                    debug("Normal extraction failed, switching to OCR")
                    extracted_text = ocr_extract_text_from_pdf(str(input_path))
            else:
                extracted_text = extract_text_from_docx(str(input_path))

            if not extracted_text.strip():
                raise ValueError("OCR ke baad bhi text nahi mila.")

            translated_text = translate_long_text(extracted_text, target_lang)

            output_name = f"translated_{input_path.stem}.{output_format}"
            output_path = OUTPUT_FOLDER / output_name

            if output_format == "pdf":
                write_pdf(translated_text, str(output_path))
            else:
                write_docx(translated_text, str(output_path))

            debug(f"Output created: {output_path}")

            return render_template(
                "result.html",
                filename=output_name,
                preview=translated_text[:3000]
            )

        except Exception as e:
            debug(f"ERROR: {e}")
            flash(f"Error: {str(e)}")
            return redirect(url_for("index"))

    return render_template("index.html")


@app.route("/download/<filename>")
def download_file(filename):
    file_path = OUTPUT_FOLDER / filename

    if not file_path.exists():
        flash("File not found.")
        return redirect(url_for("index"))

    return send_file(str(file_path), as_attachment=True)


if __name__ == "__main__":
    debug("App started at http://127.0.0.1:5000")
    app.run(debug=True)