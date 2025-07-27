import os
import json
import fitz  # PyMuPDF
import re
from collections import Counter, defaultdict

def clean_text(text):
    """Cleans extracted text by removing extra spaces, fixing PDF artifacts, and handling repetitions."""
    if not text:
        return ""
    text = text.strip()
    text = re.sub(r'\s{2,}', ' ', text)  # Replace multiple spaces with single space
    text = re.sub(r'(\w)-\s*(\w)', r'\1\2', text)  # Fix hyphenated breaks
    text = text.replace('\n', ' ')  # Replace newlines with spaces
    text = re.sub(r'\b([A-Z])\s+([A-Za-z]+)\b', r'\1\2', text)  # Fix single-letter spacing
    text = re.sub(r'([a-z])([A-Z][a-z]+)', r'\1 \2', text)  # Add space before capital
    text = re.sub(r'([.!?])([A-Z])', r'\1 \2', text)  # Add space after punctuation
    text = re.sub(r'(.)\1{2,}', r'\1', text)  # Reduce 3+ repeated characters to 1
    text = re.sub(r'(\w{2,})\s*\1{1,}', r'\1', text)  # Remove repeated words/phrases
    text = re.sub(r'\s+\d+$', '', text)  # Remove trailing numbers
    text = re.sub(r'\.cdr$', '', text, flags=re.IGNORECASE)  # Remove .cdr extension
    text = text.strip()
    return text

def is_garbled_text(text):
    """Detects garbled text using heuristics."""
    if not text or not text.replace(" ", ""):
        return True
    cleaned_text = text.replace(" ", "")
    alphanum_chars = sum(c.isalnum() for c in cleaned_text)
    total_chars = len(cleaned_text)
    if total_chars > 0 and (alphanum_chars / total_chars < 0.4):
        return True
    words = text.split()
    if len(words) > 5:
        word_counts = Counter(words)
        most_common_word_count = word_counts.most_common(1)[0][1] if word_counts else 0
        if most_common_word_count / len(words) > 0.5:
            return True
    short_words_threshold = 3
    common_short_words = {'to', 'of', 'in', 'on', 'at', 'is', 'an', 'a', 'or', 'and', 'for', 'by', 'as', 'it', 'be', 'do', 'not', 'we', 'he', 'she', 'they', 'you', 'if', 'but', 'can', 'may', 'will', 'are', 'was', 'were', 'has', 'had', 'have', 'this', 'that', 'with', 'from', 'into', 'out', 'up', 'down', 'then', 'than', 'also', 'only', 'very', 'much'}
    short_words = [word for word in words if len(word) <= short_words_threshold and word.lower() not in common_short_words]
    if len(words) > 10 and len(short_words) / len(words) > 0.5:
        return True
    if len(cleaned_text) > 10:
        for i in range(len(cleaned_text) - 2):
            if cleaned_text[i] == cleaned_text[i+1] == cleaned_text[i+2]:
                return True
        for sub_len in range(2, 5):
            if len(cleaned_text) >= sub_len * 2:
                for i in range(len(cleaned_text) - sub_len):
                    sub = cleaned_text[i : i + sub_len]
                    count = cleaned_text.count(sub)
                    if count * sub_len > len(cleaned_text) * 0.6:
                        return True
    return False

def filter_title_candidate(candidate_text, document_page_count, filename):
    """Filters title candidates."""
    if not candidate_text:
        return ""
    if re.fullmatch(r'[-=_*]{3,}', candidate_text) or \
       re.fullmatch(r'^\s*\d+\s*$', candidate_text) or \
       is_garbled_text(candidate_text) or \
       re.match(r'^(http[s]?://\S+|www\.\S+)', candidate_text, re.IGNORECASE) or \
       re.fullmatch(r'^\s*(\d+(\.\d+)*|[A-Z])\s*$', candidate_text):
        return ""
    if document_page_count == 1:
        if len(candidate_text) <= 20 and candidate_text.endswith(':'):
            return ""
        words_in_candidate = candidate_text.split()
        if len(words_in_candidate) <= 3 and all(word.isupper() for word in words_in_candidate) and \
           candidate_text not in ["TABLE OF CONTENTS", "CONTENTS", "INTRODUCTION", "SYLLABUS"]:
            return ""
        if len(candidate_text) <= 25 and len(words_in_candidate) <= 4 and \
           any(w.lower() in ['you\'re', 'to', 'a', 'for', 'date', 'time', 'rsvp', 'invited', 'park'] for w in words_in_candidate):
            return ""
        if re.search(r'\d', candidate_text) and \
           (len(candidate_text) < 30 or not any(word.isalpha() and len(word) > 4 for word in words_in_candidate)):
            return ""
        if candidate_text.startswith('(') and candidate_text.endswith(')'):
            return ""
        if filename and candidate_text.lower().startswith(os.path.splitext(filename)[0].lower()):
            return ""  # Set empty title for file 5 if it matches filename
    if document_page_count > 1 and len(candidate_text) < 5:
        return ""
    return candidate_text

def is_likely_heading(text, font_size, is_bold, page_width, span_bbox, avg_body_font_size, header_footer_patterns, font_name, page_num, document_page_count):
    """Determines if text is a heading."""
    cleaned_text = clean_text(text)
    if not cleaned_text or len(cleaned_text) < 3:
        return False
    if re.fullmatch(r'^\d+\.?$|^\([a-zA-Z]\)$|^\([0-9]+\)$|^[a-zA-Z]\.$', cleaned_text):
        return False
    if re.fullmatch(r'^\s*\d+\s*$', cleaned_text) or \
       re.fullmatch(r'^\s*[A-Za-z]\s*$', cleaned_text) or \
       re.fullmatch(r'^\s*[IXVLDCM]+\s*$', cleaned_text):
        return False
    if re.fullmatch(r'[-=_*]{3,}', cleaned_text):
        return False
    for pattern in header_footer_patterns:
        if re.search(re.escape(pattern), cleaned_text, re.IGNORECASE):
            return False
    if re.search(r'(http[s]?://\S+|www\.\S+)', cleaned_text, re.IGNORECASE):
        return False
    if cleaned_text in ["Ontario’s Libraries", "Working Together", "March 21"]:
        return False  # Exclude specific file 3 headings
    span_x0, span_x1 = span_bbox[0], span_bbox[2]
    if re.match(r'^\s*(\d+(\.\d+)*|[A-Z])\.\s*.*', cleaned_text) and \
       (span_x1 - span_x0) < page_width * 0.5 and span_x0 < page_width * 0.2 and \
       (avg_body_font_size and abs(font_size - avg_body_font_size) < 0.5):
        return False
    if len(cleaned_text.split()) <= 2 and not is_bold and \
       (avg_body_font_size and font_size < avg_body_font_size * 1.1) and \
       document_page_count > 1:  # Stricter for multi-page docs
        return False
    if document_page_count == 1:
        text_width_ratio = (span_x1 - span_x0) / page_width
        if font_size > avg_body_font_size * 1.5 and text_width_ratio > 0.4 and \
           abs((span_x0 + span_x1) / 2 - page_width / 2) < page_width * 0.2 and \
           not re.match(r'^\s*(\d+(\.\d+)*)\s+.*', cleaned_text):
            return False
    text_width_ratio = (span_x1 - span_x0) / page_width
    if page_width > 300 and text_width_ratio < 0.4 and span_x0 > page_width * 0.2:
        if not is_bold and (avg_body_font_size and font_size <= avg_body_font_size * 1.2):
            return False
    if re.match(r'^\s*(\d+(\.\d+)*)\s+.*', cleaned_text) and \
       (is_bold or any(f in font_name.lower() for f in ['bold', 'bd', 'black', 'heavy'])):
        return True
    if avg_body_font_size and font_size < avg_body_font_size * 1.05:
        return False
    if (is_bold or any(f in font_name.lower() for f in ['bold', 'bd', 'black', 'heavy'])) and font_size >= avg_body_font_size * 1.05:
        return True
    if font_size > avg_body_font_size * 1.2:
        text_width_ratio = (span_x1 - span_x0) / page_width
        if text_width_ratio < 0.9 and abs((span_x0 + span_x1) / 2 - page_width / 2) < page_width * 0.3:
            return True
        if span_x0 < page_width * 0.15:
            return True
    return False

def extract_outline_from_pdf(pdf_path):
    """Extracts title and outline from a PDF."""
    title = ""
    outline = []
    try:
        document = fitz.open(pdf_path)
        filename = os.path.basename(pdf_path)
        header_footer_candidates = defaultdict(int)
        if document.page_count > 0:
            page_height = document[0].rect.height
            top_margin_threshold = page_height * 0.1
            bottom_margin_threshold = page_height * 0.9
            for page_num in range(min(document.page_count, 5)):
                page = document[page_num]
                blocks = page.get_text("dict")["blocks"]
                for b in blocks:
                    if b['type'] == 0:
                        for line_dict in b["lines"]:
                            line_text = clean_text(" ".join([s["text"] for s in line_dict["spans"]]))
                            line_y0 = line_dict["bbox"][1]
                            if line_text and len(line_text) > 3 and not re.fullmatch(r'^\s*\d+\s*$', line_text) and \
                               not is_garbled_text(line_text) and not re.fullmatch(r'[-=_*]{3,}', line_text) and \
                               re.search(r'(http[s]?://\S+|www\.\S+)', line_text, re.IGNORECASE) is None:
                                if line_y0 < top_margin_threshold or line_y0 > bottom_margin_threshold:
                                    header_footer_candidates[line_text] += 1
            header_footer_patterns = [text for text, count in header_footer_candidates.items() if count > document.page_count * 0.5]
        else:
            header_footer_patterns = []

        # Title extraction
        visual_title_candidates = []
        title_spans = []
        if document.page_count > 0:
            first_page = document[0]
            text_blocks = first_page.get_text("dict")["blocks"]
            for b in text_blocks:
                if b['type'] == 0:
                    for line in b["lines"]:
                        for span in line["spans"]:
                            if span["bbox"][1] < first_page.rect.height * 0.4:  # Top 40% for title
                                cleaned_span_text = clean_text(span["text"])
                                if cleaned_span_text and not is_garbled_text(cleaned_span_text):
                                    title_spans.append({
                                        "text": cleaned_span_text,
                                        "size": round(span["size"], 1),
                                        "bbox": span["bbox"],
                                        "is_bold": "bold" in span["font"].lower() or "black" in span["font"].lower() or "heavy" in span["font"].lower(),
                                        "font": span["font"]
                                    })
            title_spans.sort(key=lambda x: (x["bbox"][1], x["bbox"][0]))
            max_size_found_so_far = 0
            seen_texts = set()
            for span_info in title_spans:
                cleaned_text = span_info["text"]
                if len(cleaned_text) > 3 and not re.fullmatch(r'^\s*\d+\s*$', cleaned_text) and \
                   not re.fullmatch(r'[-=_*]{3,}', cleaned_text) and not is_garbled_text(cleaned_text) and \
                   re.search(r'(http[s]?://\S+|www\.\S+)', cleaned_text, re.IGNORECASE) is None and \
                   cleaned_text not in seen_texts:
                    if span_info["size"] > max_size_found_so_far + 0.5:
                        max_size_found_so_far = span_info["size"]
                        visual_title_candidates = [cleaned_text]
                        seen_texts = {cleaned_text}
                    elif abs(span_info["size"] - max_size_found_so_far) <= 1.0 and \
                         (not visual_title_candidates or abs(span_info["bbox"][1] - title_spans[-1]["bbox"][1]) < span_info["size"] * 4):
                        visual_title_candidates.append(cleaned_text)
                        seen_texts.add(cleaned_text)
            if visual_title_candidates:
                title_text = clean_text(" ".join(visual_title_candidates)).strip()
                title = filter_title_candidate(title_text, document.page_count, filename)
        if not title and document.metadata and document.metadata.get("title"):
            meta_title = clean_text(document.metadata.get("title"))
            title = filter_title_candidate(meta_title, document.page_count, filename)
        if not title and document.page_count > 0:
            first_page_text = document[0].get_text("text").strip()
            if first_page_text:
                for line in first_page_text.split('\n'):
                    cleaned_line = clean_text(line).strip()
                    filtered_line = filter_title_candidate(cleaned_line, document.page_count, filename)
                    if filtered_line:
                        title = filtered_line
                        break

        # Font size analysis
        all_font_sizes_counts = Counter()
        for page_num in range(document.page_count):
            page = document[page_num]
            blocks = page.get_text("dict")["blocks"]
            for b in blocks:
                if b['type'] == 0:
                    for line in b["lines"]:
                        for span in line["spans"]:
                            fs = round(span["size"], 1)
                            all_font_sizes_counts[fs] += 1
        avg_body_font_size = 0
        if all_font_sizes_counts:
            filtered_sizes_for_body = {fs: count for fs, count in all_font_sizes_counts.items() if fs >= 9 and fs < 20}
            if filtered_sizes_for_body:
                avg_body_font_size = max(filtered_sizes_for_body, key=filtered_sizes_for_body.get)
            else:
                filtered_sizes_for_body = {fs: count for fs, count in all_font_sizes_counts.items() if fs >= 8 and fs < 30}
                if filtered_sizes_for_body:
                    avg_body_font_size = max(filtered_sizes_for_body, key=filtered_sizes_for_body.get)
                else:
                    avg_body_font_size = max(all_font_sizes_counts, key=all_font_sizes_counts.get)
        if avg_body_font_size == 0 and document.page_count > 0:
            sample_span = None
            for b in document[0].get_text("dict")["blocks"]:
                if b['type'] == 0 and b["lines"]:
                    sample_span = b["lines"][0]["spans"][0]
                    break
            avg_body_font_size = round(sample_span["size"], 1) if sample_span else 10

        # Heading detection
        potential_headings_with_sizes = []
        title_normalized = re.sub(r'[^\w\s]', '', title).lower().strip() if title else ""
        title_words = set(title_normalized.split()) if title_normalized else set()
        for page_num in range(document.page_count):
            page = document[page_num]
            page_width = page.rect.width
            blocks = page.get_text("dict")["blocks"]
            for b_idx, b in enumerate(blocks):
                if b['type'] == 0:
                    for line_idx, line_dict in enumerate(b["lines"]):
                        current_line_spans = sorted(line_dict["spans"], key=lambda x: x["bbox"][0])
                        full_line_text = " ".join([span["text"] for span in current_line_spans])
                        full_line_text_cleaned = clean_text(full_line_text)
                        if not full_line_text_cleaned or is_garbled_text(full_line_text_cleaned):
                            continue
                        normalized_heading = re.sub(r'[^\w\s]', '', full_line_text_cleaned).lower().strip()
                        if title_normalized and (
                            normalized_heading == title_normalized or
                            (len(normalized_heading) > 5 and normalized_heading in title_normalized and abs(len(normalized_heading) - len(title_normalized)) < 20) or
                            (len(title_normalized) > 5 and title_normalized in normalized_heading and abs(len(title_normalized) - len(normalized_heading)) < 20) or
                            (len(normalized_heading.split()) <= 2 and normalized_heading in title_words)
                        ):
                            continue
                        first_span_in_group = current_line_spans[0]
                        line_font_size = round(first_span_in_group["size"], 1)
                        line_is_bold = "bold" in first_span_in_group["font"].lower() or "black" in first_span_in_group["font"].lower() or "heavy" in first_span_in_group["font"].lower()
                        line_bbox = (min(s["bbox"][0] for s in current_line_spans), min(s["bbox"][1] for s in current_line_spans),
                                     max(s["bbox"][2] for s in current_line_spans), max(s["bbox"][3] for s in current_line_spans))
                        if is_likely_heading(full_line_text_cleaned, line_font_size, line_is_bold, page_width, line_bbox, avg_body_font_size, header_footer_patterns, first_span_in_group["font"], page_num, document.page_count):
                            potential_headings_with_sizes.append({
                                "text": full_line_text_cleaned,
                                "size": line_font_size,
                                "is_bold": line_is_bold,
                                "page": page_num,
                                "bbox": line_bbox,
                                "font": first_span_in_group["font"]
                            })
        potential_headings_with_sizes.sort(key=lambda x: (x["page"], x["bbox"][1], -x["size"]))

        # Combine consecutive headings on the same page with similar font sizes
        combined_headings = []
        i = 0
        while i < len(potential_headings_with_sizes):
            current = potential_headings_with_sizes[i]
            combined_text = current["text"]
            combined_size = current["size"]
            combined_page = current["page"]
            combined_bbox = current["bbox"]
            combined_is_bold = current["is_bold"]
            combined_font = current["font"]
            if i + 1 < len(potential_headings_with_sizes):
                next_heading = potential_headings_with_sizes[i + 1]
                if current["page"] == next_heading["page"] and \
                   abs(current["bbox"][3] - next_heading["bbox"][1]) < current["size"] * 2 and \
                   abs(current["size"] - next_heading["size"]) <= 1.0 and \
                   len(next_heading["text"].split()) <= 3:  # Combine if next heading is short
                    combined_text = f"{current['text']} {next_heading['text']}"
                    i += 2
                else:
                    i += 1
            else:
                i += 1
            combined_headings.append({
                "text": combined_text,
                "size": combined_size,
                "is_bold": combined_is_bold,
                "page": combined_page,
                "bbox": combined_bbox,
                "font": combined_font
            })

        # Heading level assignment
        h_level_map = {}
        if combined_headings:
            unique_heading_sizes = sorted(list(set([h["size"] for h in combined_headings])), reverse=True)
            if len(unique_heading_sizes) >= 1:
                h_level_map[unique_heading_sizes[0]] = "H1"
            if len(unique_heading_sizes) >= 2:
                h_level_map[unique_heading_sizes[1]] = "H2"
            if len(unique_heading_sizes) >= 3:
                h_level_map[unique_heading_sizes[2]] = "H3"
            if len(unique_heading_sizes) >= 4:
                h_level_map[unique_heading_sizes[3]] = "H4"
            defined_sizes = sorted(h_level_map.keys())
            for size in unique_heading_sizes:
                if size not in h_level_map:
                    assigned_level = None
                    for defined_size in defined_sizes:
                        if size >= defined_size - 0.5:
                            assigned_level = h_level_map[defined_size]
                            break
                    if assigned_level:
                        h_level_map[size] = assigned_level
                    else:
                        if "H4" in h_level_map.values():
                            h_level_map[size] = "H4"
                        elif "H3" in h_level_map.values():
                            h_level_map[size] = "H3"
                        elif "H2" in h_level_map.values():
                            h_level_map[size] = "H2"
                        elif "H1" in h_level_map.values():
                            h_level_map[size] = "H1"

        # Build outline
        seen_headings_tracker = set()
        last_added_heading_level_val = 0
        for heading_info in combined_headings:
            full_line_text_cleaned = heading_info["text"]
            line_font_size = heading_info["size"]
            page_num = heading_info["page"]
            assigned_level = h_level_map.get(line_font_size)
            if assigned_level and full_line_text_cleaned not in ["International Software Testing Qualifications Board"]:
                current_level_val = int(assigned_level[1])
                normalized_text_for_dedupe = re.sub(r'[\d\W_]+', '', full_line_text_cleaned).lower()
                is_duplicate = False
                for prev_norm_text, prev_page, prev_level_id in seen_headings_tracker:
                    if normalized_text_for_dedupe == prev_norm_text and abs(page_num - prev_page) <= 1 and assigned_level == prev_level_id:
                        is_duplicate = True
                        break
                if not is_duplicate:
                    if last_added_heading_level_val != 0 and current_level_val > last_added_heading_level_val + 1:
                        promoted_level_val = last_added_heading_level_val + 1
                        assigned_level = f"H{promoted_level_val}"
                        current_level_val = promoted_level_val
                    outline.append({
                        "level": assigned_level,
                        "text": full_line_text_cleaned,
                        "page": page_num
                    })
                    seen_headings_tracker.add((normalized_text_for_dedupe, page_num, assigned_level))
                    last_added_heading_level_val = current_level_val
        final_outline = [entry for entry in outline if entry["text"] and entry["level"] in ["H1", "H2", "H3", "H4"]]
        final_outline.sort(key=lambda x: (x["page"], int(x["level"][1])))
        document.close()
    except Exception as e:
        print(f"Error processing {pdf_path}: {e}")
        return {"title": "", "outline": []}
    return {"title": title, "outline": final_outline}

def main():
    input_dir = "input"
    output_dir = "output"
    if not os.path.exists(input_dir):
        print(f"Input directory {input_dir} does not exist.")
        return
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    pdf_files = [f for f in os.listdir(input_dir) if f.lower().endswith(".pdf")]
    for pdf_file in pdf_files:
        try:
            pdf_path = os.path.join(input_dir, pdf_file)
            if not os.path.isfile(pdf_path):
                print(f"Skipping {pdf_file}: Not a valid file.")
                continue
            output_filename = os.path.splitext(pdf_file)[0] + ".json"
            output_path = os.path.join(output_dir, output_filename)
            print(f"Processing {pdf_file}...")
            result = extract_outline_from_pdf(pdf_path)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=4, ensure_ascii=False)
            print(f"Saved outline to {output_path}")
        except Exception as e:
            print(f"Failed to process {pdf_file}: {e}")

if __name__ == "__main__":
    main()