import streamlit as st
import fitz  # PyMuPDF
from langdetect import detect
from collections import Counter
import pandas as pd
import re
import os
import io

# ---------------------- Helper Functions ----------------------
def is_valid_paragraph(text):
    word_count = len(text.split())
    has_punctuation = any(p in text for p in ['.', ':', ';', '!', '?'])
    not_code_like = not re.match(r'^\w{2,10}[-\d]*$', text.strip())
    not_part_number = not re.search(r'\b(part\s*no|ref|code|item)\b', text.lower())
    not_dotted_line = not re.match(r'^.*\.{4,}.*$', text)
    return word_count >= 8 and has_punctuation and not_code_like and not_part_number and not_dotted_line

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
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
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

def detect_languages(paragraphs):
    lang_results = []
    for p in paragraphs:
        try:
            lang = detect(p['text'])
        except:
            lang = "unknown"
        p['language'] = lang
        lang_results.append(lang)
    return paragraphs, lang_results

def find_foreign_paragraphs(paragraphs, lang_results):
    lang_count = Counter(lang_results)
    major_language = lang_count.most_common(1)[0][0]
    foreign_paragraphs = [
        p for p in paragraphs if p['language'] != major_language and p['language'] != "unknown"
    ]
    return major_language, foreign_paragraphs

def analyze_pdf_language_and_save_bytesio(pdf_bytes, file_name, use_columns=True, column_split=300):
    paragraphs = extract_paragraphs_from_pdf(pdf_bytes, use_columns, column_split)
    paragraphs, lang_results = detect_languages(paragraphs)
    major_language, foreign_paragraphs = find_foreign_paragraphs(paragraphs, lang_results)
    df_foreign = pd.DataFrame(foreign_paragraphs)
    output_csv = f"{file_name.replace('.pdf', '')}_foreign.csv"
    csv_bytes = df_foreign.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
    return major_language, df_foreign, csv_bytes, output_csv


# ---------------------- Streamlit App ----------------------
st.set_page_config(page_title="Foreign Language Detector", layout="centered")
st.title("📄 Foreign Language Detector")

uploaded_file = st.file_uploader("Upload a PDF file(<10 MB)", type=["pdf"])

if uploaded_file is not None:
    with st.spinner("Analyzing PDF..."):
        pdf_bytes = uploaded_file.read()
        major_lang, df, csv_bytes, output_csv = analyze_pdf_language_and_save_bytesio(
            pdf_bytes, uploaded_file.name
        )
    st.success(f"✅ Major language: {major_lang}")
    st.info(f"Found {len(df)} foreign paragraphs.")
    st.dataframe(df[['page', 'language', 'text']].head(10))
    st.download_button(
        label="⬇️ Download Foreign Paragraphs CSV",
        data=csv_bytes,
        file_name=output_csv,
        mime="text/csv"
    )