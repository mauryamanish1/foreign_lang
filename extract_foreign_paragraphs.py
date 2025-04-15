import streamlit as st
import fitz  # PyMuPDF
from langdetect import detect
from collections import Counter
import pandas as pd
import re
import io
from langdetect import detect
import pycountry

# ---------------------- Helper Functions ----------------------

def is_valid_paragraph(text):
    text = text.strip()
    if not text or len(text.split()) < 3:
        return False

    # Filter obvious noise
    if re.match(r'^.*\.{4,}.*$', text):
        return False

    words = text.split()
    word_count = len(words)
    part_number_like = 0

    for word in words:
        cleaned = word.strip(".,;:()[]{}")
        has_digits = any(char.isdigit() for char in cleaned)
        long_enough = len(cleaned) > 3
        if has_digits and long_enough:
            part_number_like += 1

    part_ratio = part_number_like / word_count if word_count else 0
    if part_ratio > 0.3:
        return False

    has_punctuation = any(p in text for p in ['.', ':', ';', '!', '?'])
    return has_punctuation



def extract_text_by_columns(page, column_split=300):
    blocks = page.get_text("blocks")
    left_col, right_col = [], []
    for b in blocks:
        x0, y0, x1, y1, text, *_ = b
        if x0 < column_split:
            left_col.append((y0, text))
        else:
            right_col.append((y0, text))
    left_col.sort()
    right_col.sort()
    combined_text = '\n'.join([t for _, t in left_col + right_col])
    return combined_text

def clean_line(line):
    line = line.strip()
    if not line or line.count('.') > 10:
        return ''
    if re.fullmatch(r'[-–—_\s\d.]+', line):
        return ''
    return line

def extract_paragraphs_from_pdf(pdf_bytes, use_columns=True, column_split=300):
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        st.error("❌ Unable to read the PDF. Please check if it's a valid file.")
        return []

    paragraphs = []
    for page_num, page in enumerate(doc, start=1):
        text = extract_text_by_columns(page, column_split) if use_columns else page.get_text("text")
        lines = [clean_line(line) for line in text.split('\n')]
        lines = [line for line in lines if line]
        para_buffer = ""
        para_num = 0
        for line in lines:
            if para_buffer:
                para_buffer += ' ' + line.strip()
            else:
                para_buffer = line.strip()
            if re.search(r'[.?!:;]$', line.strip()) or len(line.strip()) < 40:
                if is_valid_paragraph(para_buffer):
                    para_num += 1
                    paragraphs.append({
                        'page': page_num,
                        'paragraph_number': para_num,
                        'text': para_buffer.strip(),
                        'word_count': len(para_buffer.strip().split())
                    })
                para_buffer = ""
        if is_valid_paragraph(para_buffer):
            para_num += 1
            paragraphs.append({
                'page': page_num,
                'paragraph_number': para_num,
                'text': para_buffer.strip(),
                'word_count': len(para_buffer.strip().split())
            })
    return paragraphs

# def detect_languages(paragraphs):
#     lang_results = []
#     for p in paragraphs:
#         try:
#             lang = detect(p['text'])
#         except Exception:
#             lang = "unknown"
#         p['language'] = lang
#         lang_results.append(lang)
#     return paragraphs, lang_results





def get_language_name(code):
    try:
        return pycountry.languages.get(alpha_2=code).name
    except:
        return "Unknown"

def detect_languages(paragraphs):
    lang_results = []
    for p in paragraphs:
        try:
            lang_code = detect(p['text'])
            lang_name = get_language_name(lang_code)
        except Exception:
            lang_code = "unknown"
            lang_name = "Unknown"
        p['language'] = lang_name
        lang_results.append(lang_name)
    return paragraphs, lang_results




def find_foreign_paragraphs(paragraphs, lang_results):
    lang_count = Counter(lang_results)
    if not lang_count:
        return "unknown", []

    major_language = lang_count.most_common(1)[0][0]
    foreign_paragraphs = [
        p for p in paragraphs if p['language'] != major_language and p['language'] != "unknown"
    ]
    return major_language, foreign_paragraphs

def analyze_pdf_language_and_save_bytesio(pdf_bytes, file_name, use_columns=True, column_split=300):
    paragraphs = extract_paragraphs_from_pdf(pdf_bytes, use_columns, column_split)
    if not paragraphs:
        return "unknown", pd.DataFrame(), b"", ""

    paragraphs, lang_results = detect_languages(paragraphs)
    major_language, foreign_paragraphs = find_foreign_paragraphs(paragraphs, lang_results)

    if not foreign_paragraphs:
        return major_language, pd.DataFrame(), b"", ""

    df_foreign = pd.DataFrame(foreign_paragraphs)
    clean_df_foreign = df_foreign.loc[df_foreign['word_count']>9]
    output_csv = f"{file_name.replace('.pdf', '')}_foreign.csv"
    csv_bytes = clean_df_foreign.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
    return major_language, clean_df_foreign, csv_bytes, output_csv

# ---------------------- Streamlit App ----------------------
st.set_page_config(page_title="Foreign Language Detector", layout="centered")
st.title("📄 Foreign Language Detector")

uploaded_file = st.file_uploader("Upload a PDF file (<10 MB)", type=["pdf"])

if uploaded_file is not None:
    with st.spinner("Analyzing PDF..."):
        try:
            pdf_bytes = uploaded_file.read()
            major_lang, df, csv_bytes, output_csv = analyze_pdf_language_and_save_bytesio(
                pdf_bytes, uploaded_file.name
            )

            if df.empty:
                st.warning("No foreign language paragraphs were detected.")
            else:
                st.success(f"✅ Major language: {major_lang}")
                st.info(f"Found {len(df)} foreign paragraphs.")
                st.dataframe(df[['page', 'language', 'text']].head(10))
                st.download_button(
                    label="⬇️ Download Foreign Paragraphs CSV",
                    data=csv_bytes,
                    file_name=output_csv,
                    mime="text/csv"
                )
        except Exception as e:
            st.error(f"❌ An unexpected error occurred during analysis.")
            st.exception(e)