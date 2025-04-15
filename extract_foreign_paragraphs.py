# %%
import fitz  # PyMuPDF
from langdetect import detect
from collections import Counter
import pandas as pd
import re

def is_valid_paragraph(text):
    """Heuristic to validate a meaningful paragraph."""
    word_count = len(text.split())
    has_punctuation = any(p in text for p in ['.', ':', ';', '!', '?'])
    not_code_like = not re.match(r'^\w{2,10}[-\d]*$', text.strip())  # avoid codes
    not_part_number = not re.search(r'\b(part\s*no|ref|code|item)\b', text.lower())
    not_dotted_line = not re.match(r'^.*\.{4,}.*$', text)  # remove lines with many dots (TOC-style)
    return word_count >= 8 and has_punctuation and not_code_like and not_part_number and not_dotted_line

def extract_text_by_columns(page, column_split=300):
    """Extracts text block-wise preserving column layout."""
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
    """Basic line hygiene."""
    line = line.strip()
    if not line or line.count('.') > 10:  # eliminate TOC-style lines
        return ''
    if re.fullmatch(r'[-–—_\s\d.]+', line):  # dashes, dots, whitespace only
        return ''
    return line

def extract_paragraphs_from_pdf(pdf_path, use_columns=True, column_split=300):
    doc = fitz.open(pdf_path)
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

import os

def analyze_pdf_language_and_save(pdf_path, use_columns=True, column_split=300):
    # Extract paragraphs from the PDF
    paragraphs = extract_paragraphs_from_pdf(pdf_path, use_columns, column_split)
    
    # Detect languages of the paragraphs
    paragraphs, lang_results = detect_languages(paragraphs)
    
    # Identify the major language and foreign paragraphs
    major_language, foreign_paragraphs = find_foreign_paragraphs(paragraphs, lang_results)

    print(f"\n✅ Major language detected: {major_language}")
    print(f"🚨 Foreign paragraphs found: {len(foreign_paragraphs)}")

    # Create the DataFrame of foreign paragraphs
    df_foreign = pd.DataFrame(foreign_paragraphs)
    
    # Get the input PDF file name (without extension)
    file_name = os.path.splitext(os.path.basename(pdf_path))[0]
    
    # Generate the output CSV file name by appending the input file name as a suffix
    output_file = f"{file_name}_df_foreign.csv"
    
    # Save the DataFrame to a CSV file with the generated name
    df_foreign.to_csv(output_file, index=False)

    return major_language, df_foreign





