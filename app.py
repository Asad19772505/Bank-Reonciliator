# app.py
# ---------------------------------------------
# Bank Reconciliation App (EN/AR + OCR + PDF/Excel/CSV exports)
# ---------------------------------------------
# Run: streamlit run app.py
# Notes:
# - For scanned PDFs, install Tesseract (with 'eng' + 'ara' data) and Poppler.
#   Ubuntu: sudo apt-get update && sudo apt-get install -y tesseract-ocr tesseract-ocr-ara poppler-utils
#   Windows: install Tesseract & Poppler; then set the Tesseract path in the app sidebar if needed.
# ---------------------------------------------
import io
import os
import math
import tempfile
from datetime import datetime, timedelta
from typing import Optional, Tuple, List

import numpy as np
import pandas as pd
import streamlit as st

# Optional libs for PDF parse/OCR and PDF export (loaded lazily)
PDF_AVAILABLE = True
OCR_AVAILABLE = True
PDF_EXPORT_AVAILABLE = True

try:
    import pdfplumber
except Exception:
    PDF_AVAILABLE = False

try:
    from pdf2image import convert_from_bytes
    import pytesseract
    from PIL import Image, ImageOps, ImageFilter
except Exception:
    OCR_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import arabic_reshaper
    from bidi.algorithm import get_display
except Exception:
    PDF_EXPORT_AVAILABLE = False

try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_OK = True
except Exception:
    RAPIDFUZZ_OK = False

st.set_page_config(page_title="Bank Reconciliation", layout="wide")

# ----------------------------
# I18N (English / Arabic)
# ----------------------------
T = {
    "en": {
        "title": "Bank Reconciliation App",
        "intro": "Upload your GL and Bank statement, map columns, set tolerances, and reconcile. Handles Excel/CSV/PDF (incl. scanned via OCR).",
        "ui_lang": "UI Language",
        "gl_file": "Upload GL file (Excel/CSV/PDF)",
        "bank_file": "Upload Bank Statement (Excel/CSV/PDF)",
        "font_file": "Optional: Upload Arabic TTF font (for PDF export)",
        "tess_path": "Optional: Tesseract path (if not in PATH)",
        "parse_pdf": "If PDF, try table extraction (pdfplumber)",
        "use_ocr": "If PDF parsing fails, try OCR (needs Tesseract with 'eng' + 'ara', and Poppler)",
        "ocr_langs": "OCR languages (comma-separated, e.g., eng,ara)",
        "ocr_psm": "OCR page segmentation mode (e.g., 6)",
        "column_mapping": "Column Mapping",
        "map_hint": "Select which columns represent Date, Amount (or Debit/Credit), Description, and Reference.",
        "date_col": "Date column",
        "amount_col": "Amount column (signed if available)",
        "debit_col": "Debit column",
        "credit_col": "Credit column",
        "desc_col": "Description column",
        "ref_col": "Reference/Check No. column",
        "invert_sign": "Invert signs (common if bank credits are positive but need to be negative in GL)",
        "date_fmt": "Date format (leave blank to auto-detect)",
        "tol": "Reconciliation Tolerances",
        "date_tol": "Date tolerance (days)",
        "amt_tol": "Amount tolerance",
        "fuzz": "Description match (optional)",
        "fuzz_thresh": "Fuzzy description threshold (0-100)",
        "run": "Run Reconciliation",
        "results": "Results",
        "preview_gl": "Preview: Normalized GL (top 10)",
        "preview_bank": "Preview: Normalized Bank (top 10)",
        "summary": "Summary",
        "matched_count": "Matched pairs",
        "gl_unrec_count": "Unreconciled GL items",
        "bank_unrec_count": "Unreconciled Bank items",
        "downloads": "Downloads",
        "dl_excel": "Download Excel report",
        "dl_csv_gl": "Download CSV: GL Unreconciled",
        "dl_csv_bank": "Download CSV: Bank Unreconciled",
        "dl_pdf": "Download PDF summary",
        "notes": "Notes",
        "notes_txt": "For OCR: install Tesseract (with eng+ara) and Poppler. For Arabic PDF text, upload a Unicode TTF (e.g., Noto Naskh Arabic).",
        "section_mapping_gl": "GL Mapping",
        "section_mapping_bank": "Bank Mapping",
        "adv": "Advanced",
        "parsed_msg": "Parsed {rows} rows and {cols} columns.",
        "err_parse": "Could not parse this PDF into a table. Enable OCR or provide CSV/Excel.",
        "ocr_parsed": "OCR extracted {rows} rows from PDF text. Verify and adjust mapping if needed.",
        "recon_ready": "Reconciliation complete.",
        "choose_one": "— None / Not Applicable —",
        "tbl_hint": "If OCR produced one 'line' column, use the 'Smart split' option below to split into columns by multi-spaces.",
        "smart_split": "Attempt smart split of OCR lines (split on 2+ spaces)",
    },
    "ar": {
        "title": "تسوية الحساب البنكي",
        "intro": "ارفع ملف دفتر الأستاذ وكشف الحساب البنكي، عَيِّن الأعمدة، حدّد الحدود المسموح بها، ثم نفّذ التسوية. يدعم Excel/CSV/PDF (مع OCR للمسح الضوئي).",
        "ui_lang": "لغة الواجهة",
        "gl_file": "تحميل دفتر الأستاذ (Excel/CSV/PDF)",
        "bank_file": "تحميل كشف الحساب البنكي (Excel/CSV/PDF)",
        "font_file": "اختياري: تحميل خط عربي TTF (للتصدير إلى PDF)",
        "tess_path": "اختياري: مسار Tesseract (إذا لم يكن ضمن PATH)",
        "parse_pdf": "إذا كان PDF، جرب استخراج الجداول (pdfplumber)",
        "use_ocr": "إذا فشل الاستخراج، جرب OCR (يتطلب Tesseract بلغتي eng+ara و Poppler)",
        "ocr_langs": "لغات OCR (مثال: eng,ara)",
        "ocr_psm": "وضع تقسيم الصفحة OCR (مثال: 6)",
        "column_mapping": "تعيين الأعمدة",
        "map_hint": "اختر أعمدة التاريخ والمبلغ (أو مدين/دائن) والوصف والمرجع.",
        "date_col": "عمود التاريخ",
        "amount_col": "عمود المبلغ (بإشارة موجبة/سالبة إن وُجد)",
        "debit_col": "عمود المدين",
        "credit_col": "عمود الدائن",
        "desc_col": "عمود الوصف",
        "ref_col": "عمود المرجع/رقم الشيك",
        "invert_sign": "عكس الإشارات (شائع إذا كان الدائن موجب في كشف البنك لكنه سالب في الدفاتر)",
        "date_fmt": "صيغة التاريخ (اتركه فارغاً لاكتشاف تلقائي)",
        "tol": "حدود التسوية",
        "date_tol": "تسامح التاريخ (أيام)",
        "amt_tol": "تسامح المبلغ",
        "fuzz": "مطابقة الوصف (اختياري)",
        "fuzz_thresh": "حد المطابقة الضبابية (0-100)",
        "run": "تنفيذ التسوية",
        "results": "النتائج",
        "preview_gl": "عرض تمهيدي: دفتر الأستاذ (أول 10)",
        "preview_bank": "عرض تمهيدي: كشف البنك (أول 10)",
        "summary": "الملخص",
        "matched_count": "عدد المطابقات",
        "gl_unrec_count": "عناصر دفتر الأستاذ غير المسوّاة",
        "bank_unrec_count": "عناصر كشف البنك غير المسوّاة",
        "downloads": "التنزيلات",
        "dl_excel": "تنزيل تقرير Excel",
        "dl_csv_gl": "تنزيل CSV: عناصر دفتر الأستاذ غير المسوّاة",
        "dl_csv_bank": "تنزيل CSV: عناصر كشف البنك غير المسوّاة",
        "dl_pdf": "تنزيل ملخص PDF",
        "notes": "ملاحظات",
        "notes_txt": "للـ OCR: ثبّت Tesseract (eng+ara) و Poppler. وللنص العربي في PDF، ارفع خطاً عربياً (مثل Noto Naskh Arabic).",
        "section_mapping_gl": "تعيين أعمدة دفتر الأستاذ",
        "section_mapping_bank": "تعيين أعمدة كشف البنك",
        "adv": "متقدم",
        "parsed_msg": "تم استخراج {rows} صفاً و {cols} عموداً.",
        "err_parse": "تعذّر استخراج الجداول من PDF. فعّل OCR أو استخدم CSV/Excel.",
        "ocr_parsed": "استخرج OCR عدد {rows} صفوف من PDF. يرجى المراجعة وضبط التعيين إن لزم.",
        "recon_ready": "اكتملت عملية التسوية.",
        "choose_one": "— لا شيء / غير متاح —",
        "tbl_hint": "إذا نتج عن OCR عمود واحد باسم 'line'، استخدم خيار 'التقسيم الذكي' أدناه لتقسيمه إلى أعمدة حسب المسافات المتعددة.",
        "smart_split": "محاولة التقسيم الذكي لأسطر OCR (تقسيم عند مسافتين فأكثر)",
    },
}

# ----------------------------
# Helpers: file loading
# ----------------------------
def _read_excel(file) -> pd.DataFrame:
    return pd.read_excel(file)

def _read_csv(file) -> pd.DataFrame:
    return pd.read_csv(file)

def _read_pdf_tabular(file_bytes: bytes) -> Optional[pd.DataFrame]:
    if not PDF_AVAILABLE:
        return None
    try:
        out_frames = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if table:
                    df = pd.DataFrame(table[1:], columns=table[0])
                    out_frames.append(df)
        if out_frames:
            dfc = pd.concat(out_frames, ignore_index=True)
            return dfc
        return None
    except Exception:
        return None

def _img_preprocess(img: Image.Image) -> Image.Image:
    # Light denoise + contrast boost
    gray = ImageOps.grayscale(img)
    gray = gray.filter(ImageFilter.MedianFilter(size=3))
    gray = ImageOps.autocontrast(gray)
    return gray

def _ocr_pdf_lines(file_bytes: bytes, langs: str = "eng,ara", psm: str = "6", tesseract_cmd: Optional[str]=None) -> List[str]:
    if not OCR_AVAILABLE:
        return []
    if tesseract_cmd:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    lang = "+".join([s.strip() for s in langs.split(",") if s.strip()])
    images = convert_from_bytes(file_bytes, fmt="png", dpi=300)
    lines = []
    for img in images:
        proc = _img_preprocess(img)
        txt = pytesseract.image_to_string(proc, lang=lang, config=f"--psm {psm}")
        # Normalize line endings
        for line in txt.splitlines():
            line = line.strip()
            if line:
                lines.append(line)
    return lines

def _ocr_lines_to_df(lines: List[str], smart_split: bool=True) -> pd.DataFrame:
    if not lines:
        return pd.DataFrame()
    if smart_split:
        # Split by 2+ spaces; infer headers if first line looks like headers
        import re
        rows = []
        for ln in lines:
            parts = re.split(r"\s{2,}|\t+", ln.strip())
            rows.append(parts)
        # Determine max columns
        width = max(len(r) for r in rows)
        rows = [r + [""]*(width - len(r)) for r in rows]
        # If first row contains any non-numeric tokens, treat as header
        header_candidate = rows[0]
        nonnum = sum(1 for x in header_candidate if not _looks_like_number(x))
        if nonnum >= max(1, round(len(header_candidate)*0.5)):
            cols = [c if c else f"col{i+1}" for i, c in enumerate(header_candidate)]
            body = rows[1:]
        else:
            cols = [f"col{i+1}" for i in range(width)]
            body = rows
        return pd.DataFrame(body, columns=cols)
    else:
        return pd.DataFrame({"line": lines})

def _looks_like_number(s: str) -> bool:
    try:
        float(s.replace(",", "").replace(" ", ""))
        return True
    except Exception:
        return False

def load_any(file, try_pdf=True, try_ocr=True, ocr_langs="eng,ara", ocr_psm="6", tesseract_path=None, smart_split=True) -> Tuple[pd.DataFrame, str]:
    name = file.name.lower()
    data = file.getvalue() if hasattr(file, "getvalue") else file.read()
    if name.endswith((".xlsx", ".xls")):
        return _read_excel(io.BytesIO(data)), "excel"
    if name.endswith(".csv"):
        return _read_csv(io.BytesIO(data)), "csv"
    if name.endswith(".pdf"):
        if try_pdf:
            df = _read_pdf_tabular(data)
            if df is not None and len(df) > 0:
                return df, "pdf-tables"
        if try_ocr:
            lines = _ocr_pdf_lines(data, ocr_langs, ocr_psm, tesseract_cmd=tesseract_path)
            df = _ocr_lines_to_df(lines, smart_split=smart_split)
            return df, "pdf-ocr"
        # Fallback
        return pd.DataFrame(), "pdf-none"
    # Unknown
    return pd.DataFrame(), "unknown"

# ----------------------------
# Normalization & reconciliation
# ----------------------------
def normalize_df(df: pd.DataFrame,
                 date_col: Optional[str],
                 amount_col: Optional[str],
                 debit_col: Optional[str],
                 credit_col: Optional[str],
                 desc_col: Optional[str],
                 ref_col: Optional[str],
                 date_format: Optional[str],
                 invert_sign: bool) -> pd.DataFrame:
    out = df.copy()
    # Strip col names
    out.columns = [str(c).strip() for c in out.columns]

    # Create DATE
    if date_col and date_col in out.columns:
        if date_format:
            out["_date"] = pd.to_datetime(out[date_col], format=date_format, errors="coerce")
        else:
            out["_date"] = pd.to_datetime(out[date_col], errors="coerce", dayfirst=True)
    else:
        out["_date"] = pd.NaT

    # Create AMOUNT
    amt = None
    if amount_col and amount_col in out.columns:
        amt = pd.to_numeric(_clean_num(out[amount_col]), errors="coerce")
    else:
        deb = pd.to_numeric(_clean_num(out[debit_col])) if debit_col and debit_col in out.columns else 0
        cre = pd.to_numeric(_clean_num(out[credit_col])) if credit_col and credit_col in out.columns else 0
        # Common sign convention: positive debit, negative credit
        amt = (deb.fillna(0) - cre.fillna(0))
    out["_amount"] = amt

    if invert_sign:
        out["_amount"] = -out["_amount"]

    # Description / Reference
    out["_desc"] = out[desc_col].astype(str) if desc_col and (desc_col in out.columns) else ""
    out["_ref"]  = out[ref_col].astype(str) if ref_col and (ref_col in out.columns) else ""

    # Keep only usable rows
    out = out[~out["_amount"].isna()].copy()
    return out

def _clean_num(series) -> pd.Series:
    return series.astype(str).str.replace(r"[^\d\-\.\,]", "", regex=True).str.replace(",", "", regex=False)

def reconcile(gl: pd.DataFrame,
              bank: pd.DataFrame,
              date_tol_days: int,
              amt_tol: float,
              use_fuzzy: bool=False,
              fuzz_thresh: int=80) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Greedy best-match:
      For each GL item, find unmatched bank items with |amount|<=amt_tol and |date diff|<=date_tol,
      choose minimum score = (abs(amount_diff) + date_diff_days).
      If use_fuzzy: require description similarity >= fuzz_thresh when both non-empty.
    Returns: matches_df, gl_unrec_df, bank_unrec_df
    """
    gl = gl.reset_index(drop=True).copy()
    bank = bank.reset_index(drop=True).copy()
    gl["_matched"] = False
    bank["_matched"] = False

    matches = []
    # Index bank by amount buckets to prune search
    bank_index = {}
    bucket_size = max(0.01, amt_tol if amt_tol > 0 else 0.01)
    def bucket(v): return round(v / bucket_size)

    for bi, row in bank.iterrows():
        b = bucket(row["_amount"])
        bank_index.setdefault(b, []).append(bi)

    for gi, grow in gl.iterrows():
        candidates = []
        bmain = bucket(grow["_amount"])
        bkeys = [bmain]
        if amt_tol > 0:
            # include neighbor buckets
            bkeys += [bmain-1, bmain+1]
        for bk in bkeys:
            for bi in bank_index.get(bk, []):
                if bank.loc[bi, "_matched"]:
                    continue
                b_amount = bank.loc[bi, "_amount"]
                a_diff = abs(float(grow["_amount"]) - float(b_amount))
                if a_diff > amt_tol:
                    continue
                gdate = grow["_date"]
                bdate = bank.loc[bi, "_date"]
                if pd.isna(gdate) or pd.isna(bdate):
                    d_diff = 0 if (pd.isna(gdate) and pd.isna(bdate)) else 9999
                else:
                    d_diff = abs((gdate - bdate).days)
                if d_diff > date_tol_days:
                    continue
                if use_fuzzy and RAPIDFUZZ_OK:
                    d1 = str(grow.get("_desc", "") or "")
                    d2 = str(bank.loc[bi, "_desc"] or "")
                    if d1 and d2:
                        score = fuzz.token_set_ratio(d1, d2)
                        if score < fuzz_thresh:
                            continue
                score_val = a_diff + (d_diff/100.0)
                candidates.append((score_val, bi))
        if candidates:
            candidates.sort(key=lambda x: x[0])
            best_bi = candidates[0][1]
            gl.loc[gi, "_matched"] = True
            bank.loc[best_bi, "_matched"] = True
            matches.append({
                "gl_index": gi,
                "bank_index": best_bi,
                "gl_date": grow["_date"],
                "bank_date": bank.loc[best_bi, "_date"],
                "gl_amount": grow["_amount"],
                "bank_amount": bank.loc[best_bi, "_amount"],
                "gl_desc": grow.get("_desc", ""),
                "bank_desc": bank.loc[best_bi, "_desc"],
                "gl_ref": grow.get("_ref", ""),
                "bank_ref": bank.loc[best_bi, "_ref"],
                "amount_diff": float(grow["_amount"]) - float(bank.loc[best_bi, "_amount"]),
                "date_diff_days": ( (grow["_date"] - bank.loc[best_bi, "_date"]).days
                                    if not (pd.isna(grow["_date"]) or pd.isna(bank.loc[best_bi, "_date"]))
                                    else np.nan )
            })

    matches_df = pd.DataFrame(matches)
    gl_unrec = gl[~gl["_matched"]].copy()
    bank_unrec = bank[~bank["_matched"]].copy()
    return matches_df, gl_unrec, bank_unrec

# ----------------------------
# Exports
# ----------------------------
def make_excel_report(matches_df, gl_unrec, bank_unrec, summary_dict) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        pd.DataFrame([summary_dict]).to_excel(writer, index=False, sheet_name="Summary")
        matches_df.to_excel(writer, index=False, sheet_name="Matches")
        gl_unrec.to_excel(writer, index=False, sheet_name="GL_Unreconciled")
        bank_unrec.to_excel(writer, index=False, sheet_name="Bank_Unreconciled")
        # Simple formatting
        wb  = writer.book
        for sh in ["Summary", "Matches", "GL_Unreconciled", "Bank_Unreconciled"]:
            ws = writer.sheets[sh]
            ws.set_zoom(110)
            for i, col in enumerate(pd.read_excel(io.BytesIO(writer._save().getvalue()), sheet_name=sh).columns):
                ws.set_column(i, i, 18)
    return output.getvalue()

def make_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")

def reshape_ar(text: str) -> str:
    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text

def make_pdf_summary(lang: str, summary_dict, gl_unrec, bank_unrec, font_bytes: Optional[bytes]) -> bytes:
    if not PDF_EXPORT_AVAILABLE:
        return b""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    margin = 2*cm
    y = H - margin

    # Fonts
    base_font = "Helvetica"
    if font_bytes:
        # Register uploaded TTF
        ttf_path = os.path.join(tempfile.gettempdir(), f"user_font_{datetime.now().timestamp()}.ttf")
        with open(ttf_path, "wb") as f:
            f.write(font_bytes)
        pdfmetrics.registerFont(TTFont("UserArabic", ttf_path))
        base_font = "UserArabic"

    def draw_text(line: str, y_pos: float, size=12, bold=False):
        txt = reshape_ar(line) if lang == "ar" else line
        c.setFont(base_font, size)
        c.drawString(margin, y_pos, txt)

    title = "Bank Reconciliation Summary" if lang == "en" else "ملخص تسوية الحساب البنكي"
    draw_text(title, y, 16)
    y -= 1.0*cm

    for k, v in summary_dict.items():
        line = f"{k}: {v}"
        if lang == "ar":
            # Simple label translation for key items
            k_map = {
                "Matched pairs": "عدد المطابقات",
                "GL unreconciled": "عناصر دفتر الأستاذ غير المسوّاة",
                "Bank unreconciled": "عناصر كشف البنك غير المسوّاة",
            }
            k_ar = k_map.get(k, k)
            line = f"{k_ar}: {v}"
        draw_text(line, y, 12)
        y -= 0.6*cm

    # Show a snippet of unreconciled (first 25)
    y -= 0.4*cm
    sub = "Top unreconciled items (GL)" if lang == "en" else "أعلى العناصر غير المسوّاة (دفتر الأستاذ)"
    draw_text(sub, y, 13)
    y -= 0.6*cm
    for _, r in gl_unrec.head(12).iterrows():
        line = f"{str(r.get('_date'))[:10]} | {r.get('_amount')} | {str(r.get('_desc'))[:60]}"
        draw_text(line, y, 10)
        y -= 0.45*cm
        if y < margin + 3*cm:
            c.showPage(); y = H - margin

    y -= 0.3*cm
    sub = "Top unreconciled items (Bank)" if lang == "en" else "أعلى العناصر غير المسوّاة (كشف البنك)"
    draw_text(sub, y, 13)
    y -= 0.6*cm
    for _, r in bank_unrec.head(12).iterrows():
        line = f"{str(r.get('_date'))[:10]} | {r.get('_amount')} | {str(r.get('_desc'))[:60]}"
        draw_text(line, y, 10)
        y -= 0.45*cm
        if y < margin + 2*cm:
            break

    c.showPage()
    c.save()
    return buf.getvalue()

# ----------------------------
# UI
# ----------------------------
with st.sidebar:
    lang = st.selectbox(T["en"]["ui_lang"], options=["en", "ar"], index=0)
    TT = T[lang]
    st.markdown(f"### {TT['title']}")
    st.caption(TT["intro"])

    try_pdf = st.checkbox(TT["parse_pdf"], value=True)
    try_ocr = st.checkbox(TT["use_ocr"], value=True)
    ocr_langs = st.text_input(TT["ocr_langs"], value="eng,ara")
    ocr_psm = st.text_input(TT["ocr_psm"], value="6")
    tess_path = st.text_input(TT["tess_path"], value="")
    smart_split = st.checkbox(TT["smart_split"], value=True)

    st.markdown("### " + TT["tol"])
    date_tol = st.number_input(TT["date_tol"], min_value=0, max_value=60, value=3, step=1)
    amt_tol = st.number_input(TT["amt_tol"], min_value=0.0, value=0.00, step=0.01, format="%.2f")

    use_fuzzy = st.checkbox(TT["fuzz"], value=False, help="Requires rapidfuzz")
    fuzz_thresh = st.slider(TT["fuzz_thresh"], 0, 100, 80, 1)

    font_file = st.file_uploader(TT["font_file"], type=["ttf"])

st.title(TT["title"])

col1, col2 = st.columns(2)
with col1:
    gl_file = st.file_uploader(TT["gl_file"], type=["xlsx", "xls", "csv", "pdf"], key="gl")
with col2:
    bank_file = st.file_uploader(TT["bank_file"], type=["xlsx", "xls", "csv", "pdf"], key="bank")

if gl_file and bank_file:
    # Load
    gl_df, gl_source = load_any(gl_file, try_pdf, try_ocr, ocr_langs, ocr_psm, tess_path or None, smart_split)
    bank_df, bank_source = load_any(bank_file, try_pdf, try_ocr, ocr_langs, ocr_psm, tess_path or None, smart_split)

    st.info(f"GL source: {gl_source}. Bank source: {bank_source}.")
    st.caption(TT["tbl_hint"])

    st.success(TT["parsed_msg"].format(rows=len(gl_df), cols=len(gl_df.columns)))
    st.dataframe(gl_df.head(10))

    st.success(TT["parsed_msg"].format(rows=len(bank_df), cols=len(bank_df.columns)))
    st.dataframe(bank_df.head(10))

    # Mapping controls
    st.header(TT["column_mapping"])
    st.caption(TT["map_hint"])

    def mapping_block(df: pd.DataFrame, title_key: str):
        st.subheader(TT[title_key])
        cols = [TT["choose_one"]] + list(df.columns)
        date_col = st.selectbox(TT["date_col"], cols, index=0, key=title_key+"_date")
        amount_col = st.selectbox(TT["amount_col"], cols, index=0, key=title_key+"_amount")
        debit_col = st.selectbox(TT["debit_col"], cols, index=0, key=title_key+"_debit")
        credit_col = st.selectbox(TT["credit_col"], cols, index=0, key=title_key+"_credit")
        desc_col = st.selectbox(TT["desc_col"], cols, index=0, key=title_key+"_desc")
        ref_col  = st.selectbox(TT["ref_col"], cols, index=0, key=title_key+"_ref")
        invert   = st.checkbox(TT["invert_sign"], value=False, key=title_key+"_inv")
        date_fmt = st.text_input(TT["date_fmt"], value="", key=title_key+"_fmt")
        return {
            "date_col": None if date_col == TT["choose_one"] else date_col,
            "amount_col": None if amount_col == TT["choose_one"] else amount_col,
            "debit_col": None if debit_col == TT["choose_one"] else debit_col,
            "credit_col": None if credit_col == TT["choose_one"] else credit_col,
            "desc_col": None if desc_col == TT["choose_one"] else desc_col,
            "ref_col":  None if ref_col == TT["choose_one"] else ref_col,
            "invert": invert,
            "fmt": date_fmt.strip() or None
        }

    gl_map = mapping_block(gl_df, "section_mapping_gl")
    bank_map = mapping_block(bank_df, "section_mapping_bank")

    if st.button(TT["run"], type="primary"):
        gl_norm = normalize_df(gl_df,
                               gl_map["date_col"], gl_map["amount_col"], gl_map["debit_col"], gl_map["credit_col"],
                               gl_map["desc_col"], gl_map["ref_col"], gl_map["fmt"], gl_map["invert"])
        bank_norm = normalize_df(bank_df,
                                 bank_map["date_col"], bank_map["amount_col"], bank_map["debit_col"], bank_map["credit_col"],
                                 bank_map["desc_col"], bank_map["ref_col"], bank_map["fmt"], bank_map["invert"])

        st.subheader(TT["results"])
        st.write(TT["preview_gl"])
        st.dataframe(gl_norm.head(10))
        st.write(TT["preview_bank"])
        st.dataframe(bank_norm.head(10))

        matches_df, gl_unrec, bank_unrec = reconcile(
            gl_norm, bank_norm,
            date_tol_days=int(date_tol),
            amt_tol=float(amt_tol),
            use_fuzzy=bool(use_fuzzy and RAPIDFUZZ_OK),
            fuzz_thresh=int(fuzz_thresh),
        )

        summary = {
            ("Matched pairs" if lang=="en" else "عدد المطابقات"): len(matches_df),
            ("GL unreconciled" if lang=="en" else "عناصر دفتر الأستاذ غير المسوّاة"): len(gl_unrec),
            ("Bank unreconciled" if lang=="en" else "عناصر كشف البنك غير المسوّاة"): len(bank_unrec),
        }

        st.header(TT["summary"])
        st.json(summary)

        st.header(TT["downloads"])

        # Excel
        excel_bytes = make_excel_report(matches_df, gl_unrec, bank_unrec, summary)
        st.download_button(TT["dl_excel"], data=excel_bytes, file_name=f"bank_recon_{datetime.now():%Y%m%d_%H%M}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        # CSVs
        st.download_button(TT["dl_csv_gl"], data=make_csv_bytes(gl_unrec), file_name="gl_unreconciled.csv", mime="text/csv")
        st.download_button(TT["dl_csv_bank"], data=make_csv_bytes(bank_unrec), file_name="bank_unreconciled.csv", mime="text/csv")

        # PDF
        font_bytes = font_file.getvalue() if font_file is not None else None
        if PDF_EXPORT_AVAILABLE:
            pdf_bytes = make_pdf_summary(lang, summary, gl_unrec, bank_unrec, font_bytes)
            st.download_button(TT["dl_pdf"], data=pdf_bytes, file_name=f"bank_recon_summary_{datetime.now():%Y%m%d_%H%M}.pdf", mime="application/pdf")
        else:
            st.warning("PDF export dependencies not installed (reportlab, arabic-reshaper, python-bidi).")

        st.success(TT["recon_ready"])

st.divider()
with st.expander(TT["notes"]):
    st.write(TT["notes_txt"])
    if not PDF_AVAILABLE:
        st.warning("pdfplumber not available; table parsing from PDFs disabled.")
    if not OCR_AVAILABLE:
        st.warning("OCR not available; install pdf2image, pytesseract, Pillow, and Poppler + Tesseract binaries.")
    if use_fuzzy and not RAPIDFUZZ_OK:
        st.warning("rapidfuzz not installed; fuzzy description matching disabled.")
