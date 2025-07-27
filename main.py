import os
import json
import fitz  # PyMuPDF
import re
from collections import Counter, defaultdict


def clean_text(text):
    """Cleans extracted text by removing extra spaces, fixing common PDF artifacts,
    and handling some specific garbling patterns."""
    text = text.strip()
    text = re.sub(r'\s{2,}', ' ', text) # Replace multiple spaces with single
    text = re.sub(r'(\w)-\s*(\w)', r'\1\2', text) # Fix hyphenated words broken by line breaks
    text = text.replace('\n', ' ') # Remove newlines

    # Specific garbling fix: Re-join single capital letters to the next word (e.g., "Y ou" -> "You", "T HERE" -> "THERE").
    # This targets cases where single capital characters are separated from the rest of the word.
    text = re.sub(r'\b([A-Z])\s+([A-Za-z]+)\b', r'\1\2', text)

    # Heuristic for missing spaces between concatenated words (e.g., "aProposal")
    # Only if the first part is lowercase and the second starts with an uppercase letter.
    # This should run after the above rule to prevent conflicts.
    text = re.sub(r'([a-z])([A-Z][a-z]+)', r'\1 \2', text)
    
    # Add space after period, exclamation mark, or question mark if followed by an uppercase letter without space
    text = re.sub(r'([.!?])([A-Z])', r'\1 \2', text)

    # New: Remove excessive character repetition (e.g., "Reeeequest" -> "Request")
    # This pattern looks for 3 or more identical characters and replaces them with 2.
    # This is a common PDF OCR artifact.
    text = re.sub(r'(.)\1{2,}', r'\1\1', text) # e.g., "aaaa" -> "aa", "eee" -> "ee"

    # Remove trailing page numbers from headings (e.g., "Section 12")
    text = re.sub(r'\s+\d+$', '', text).strip()
    
    return text


def is_garbled_text(text):
    """
    Heuristic to detect if text is likely garbled due to PDF rendering issues.
    Checks for high non-alphanumeric ratio, excessive repetition, and very short fragmented words.
    """
    if not text:
        return True
    
    cleaned_text_for_check = text.replace(" ", "") # For repetition check, ignore spaces
    if not cleaned_text_for_check:
        return True

    # High non-alphanumeric ratio (excluding common punctuation within words)
    alphanum_chars = sum(c.isalnum() for c in cleaned_text_for_check)
    total_chars = len(cleaned_text_for_check)
    if total_chars > 0 and (alphanum_chars / total_chars < 0.5): # Stricter threshold (was 0.6)
        return True

    words = text.split()
    if len(words) > 5:
        word_counts = Counter(words)
        most_common_word_count = word_counts.most_common(1)[0][1] if word_counts else 0
        if len(words) > 0 and most_common_word_count / len(words) > 0.5: # More than 50% of words are the same (was 0.6)
            return True
    
    # Check for excessive short, non-common words
    short_words_threshold = 3 # Words 3 chars or less
    common_short_words = {'to', 'of', 'in', 'on', 'at', 'is', 'an', 'a', 'or', 'and', 'for', 'by', 'as', 'it', 'be', 'do', 'not', 'we', 'he', 'she', 'they', 'you', 'if', 'but', 'can', 'may', 'will', 'are', 'was', 'were', 'has', 'had', 'have', 'this', 'that', 'with', 'from', 'into', 'out', 'up', 'down', 'then', 'than', 'also', 'only', 'very', 'much'}
    short_words = [word for word in words if len(word) <= short_words_threshold and word.lower() not in common_short_words]
    if len(words) > 10 and len(short_words) / len(words) > 0.5: # More than 50% of words are short and uncommon (was 0.6)
        return True

    # Detect excessive character repetition (e.g., "aaaaa" or "opopop")
    if len(cleaned_text_for_check) > 10:
        # Check for 4 consecutive identical characters (was 5)
        for i in range(len(cleaned_text_for_check) - 3):
            if cleaned_text_for_check[i] == cleaned_text_for_check[i+1] == cleaned_text_for_check[i+2] == cleaned_text_for_check[i+3]:
                return True
        
        # Check for repeating substrings of length 2-4 (was 2-5) that cover a significant portion of the text
        for sub_len in range(2, 5): # Check for repeating patterns of length 2, 3, 4
            if len(cleaned_text_for_check) >= sub_len * 2:
                for i in range(len(cleaned_text_for_check) - sub_len):
                    sub = cleaned_text_for_check[i : i + sub_len]
                    count = cleaned_text_for_check.count(sub)
                    if count * sub_len > len(cleaned_text_for_check) * 0.6: # 60% coverage (was 0.7)
                        return True
    return False


def filter_title_candidate(candidate_text, document_page_count):
    """
    Applies a series of filters to a text candidate to determine if it's a valid document title.
    Returns the filtered text or an empty string if it's not a valid title.
    """
    if not candidate_text:
        return ""

    # Basic noise filters
    if re.fullmatch(r'[-=_]{3,}', candidate_text) or \
       re.fullmatch(r'^\s*\d+\s*$', candidate_text) or \
       is_garbled_text(candidate_text) or \
       re.match(r'^(http[s]?://\S+|www\.\S+)', candidate_text, re.IGNORECASE) or \
       re.fullmatch(r'^\s*(\d+(\.\d+)*|[A-Z])\s*$', candidate_text):
        return ""

    # Filters specific to single-page documents (like flyers/invitations)
    if document_page_count == 1:
        # Case 1: Short text ending with a colon (e.g., "ADDRESS:")
        if len(candidate_text) <= 20 and candidate_text.endswith(':'):
            return ""
        # Case 2: Short, all-uppercase phrases that are common in flyers/invitations
        words_in_candidate = candidate_text.split()
        if len(words_in_candidate) > 0 and len(words_in_candidate) <= 3 and \
           all(word.isupper() for word in words_in_candidate) and \
           not is_garbled_text(candidate_text):
            # Exclude common actual titles that might be all caps
            if candidate_text not in ["TABLE OF CONTENTS", "CONTENTS", "INTRODUCTION", "SYLLABUS"]:
                return ""
        
        # Case 3: Very short and looks like a non-descriptive phrase (e.g., "YOU'RE INVITED", "TO A")
        if len(candidate_text) <= 25 and len(candidate_text.split()) <= 4 and \
           any(w.lower() in ['you\'re', 'to', 'a', 'for', 'date', 'time', 'rsvp', 'invited', 'park'] for w in words_in_candidate):
            return ""
        
        # Case 4: Looks like an address (contains digits and is short/non-descriptive)
        if re.search(r'\d', candidate_text) and \
           (len(candidate_text) < 30 or not any(word.isalpha() and len(word) > 4 for word in words_in_candidate)):
            return ""

        # Case 5: Starts and ends with parentheses (e.g., "(NEAR DIXIE STAMPEDE ON THE PARKWAY)")
        if candidate_text.startswith('(') and candidate_text.endswith(')'):
            return ""
    
    # General filter for multi-page documents: if title is too short, it's likely not a real title
    if document_page_count > 1 and len(candidate_text) < 7:
        return ""

    return candidate_text


def is_likely_heading(text, font_size, is_bold, page_width, span_bbox, avg_body_font_size, header_footer_patterns, font_name, page_num, document_page_count):
    """
    Determines if a text span is likely a heading based on structural and visual heuristics.
    Includes more robust noise filtering and positional awareness.
    """
    cleaned_text = clean_text(text)

    # 1. Basic length and content filters
    if not cleaned_text or len(cleaned_text) < 3: # Headings are usually longer than 2 chars
        return False
    
    # Filter out single numbers or common list/table indicators that are not descriptive
    if re.fullmatch(r'^\d+\.?$|^\([a-zA-Z]\)$|^\([0-9]+\)$|^[a-zA-Z]\.$', cleaned_text):
        return False
    
    # Filter out common page numbers/short noise that might appear in headers/footers
    if re.fullmatch(r'^\s*\d+\s*$', cleaned_text) or \
       re.fullmatch(r'^\s*[A-Za-z]\s*$', cleaned_text) or \
       re.fullmatch(r'^\s*[IXVLDCM]+\s*$', cleaned_text): # Roman numerals
        return False

    # Filter out common separator lines (e.g., "---", "===")
    if re.fullmatch(r'[-=_]{3,}', cleaned_text):
        return False

    # Filter based on identified header/footer patterns (text consistently appearing in margins)
    for pattern in header_footer_patterns:
        if re.search(re.escape(pattern), cleaned_text, re.IGNORECASE):
            return False

    # Filter out lines that look like URLs, preventing them from being identified as headings.
    if re.search(r'(http[s]?://\S+|www\.\S+)', cleaned_text, re.IGNORECASE):
        return False

    # Heuristic for form-like numbered items or short table headers (e.g., from file01.pdf)
    span_x0 = span_bbox[0]
    span_x1 = span_bbox[2]
    # If it starts with a number/letter and a period, is relatively narrow, and left-aligned,
    # AND its font size is very close to body text, it's likely a form label/list item.
    if re.match(r'^\s*(\d+(\.\d+)*|[A-Z])\.\s*.*', cleaned_text) and \
       (span_x1 - span_x0) < page_width * 0.5 and \
       span_x0 < page_width * 0.2 and \
       (avg_body_font_size and abs(font_size - avg_body_font_size) < 0.5): # Very close to body font size
        return False
    
    # Additional filter for short, non-bold text that is not significantly larger than body text.
    # This helps filter out things like "S. No", "Name", "Age" if they are not truly prominent headings.
    if len(cleaned_text.split()) <= 3 and not is_bold and \
       (avg_body_font_size and font_size < avg_body_font_size * 1.2): # Not much larger than body text
        return False

    # New: Filter for single-page documents where large, centered text might be decorative/flyer content, not a heading.
    # This specifically targets "HOPE To SEE You THERE !" in file05.pdf.
    if document_page_count == 1:
        text_width_ratio = (span_x1 - span_x0) / page_width
        # If it's very large, relatively wide (not a narrow column), and roughly centered
        if font_size > avg_body_font_size * 1.5 and text_width_ratio > 0.4 and \
           abs((span_x0 + span_x1) / 2 - page_width / 2) < page_width * 0.2:
            # And it's not a numbered heading (which are usually structural even in flyers)
            if not re.match(r'^\s*(\d+(\.\d+)*)\s+.*', cleaned_text):
                return False

    # New: Positional filter for columnar text (e.g., file04.pdf's "REGULAR PATHWAY", "DISTINCTION PATHWAY")
    # This targets text blocks that are narrower than the page width and are notably indented
    # from the main left margin, suggesting they are part of a multi-column layout or a sidebar/box.
    # Crucially, this filter should *not* apply if the text is clearly a strong heading (very large or bold numbered).
    text_width_ratio = (span_x1 - span_x0) / page_width
    if page_width > 500 and text_width_ratio < 0.45 and span_x0 > page_width * 0.2: # Wider margin for columnar
        # Only filter if it's NOT explicitly bold AND NOT significantly larger than average body text.
        if not is_bold and (avg_body_font_size and font_size <= avg_body_font_size * 1.3):
            return False


    # Strong priority for numbered and bold headings (or bold by font name, e.g., "Arial-Bold")
    if re.match(r'^\s*(\d+(\.\d+)*)\s+.*', cleaned_text) and \
       (is_bold or any(f in font_name.lower() for f in ['bold', 'bd', 'black', 'heavy'])):
        return True

    # Font size comparison to average body text - only consider as heading if significantly larger.
    # A multiplier of 1.15 means the font size must be at least 15% larger than the body text.
    if avg_body_font_size and font_size < avg_body_font_size * 1.1: # Reduced threshold slightly
        return False

    # If it's bold and reasonably sized, it's a strong candidate
    if (is_bold or any(f in font_name.lower() for f in ['bold', 'bd', 'black', 'heavy'])) and font_size >= avg_body_font_size * 1.1:
        # Filter for long, bold sentences that are not significantly larger than body text AND are very left-aligned,
        # often indicative of a paragraph start rather than a true heading.
        if len(cleaned_text.split()) > 8 and font_size <= avg_body_font_size * 1.3 and span_x0 < page_width * 0.1:
            return False
        return True

    # If it's significantly larger than body text (e.g., >30% larger) and reasonably positioned
    if font_size > avg_body_font_size * 1.3:
        # Heuristic for centering: if text is not too wide and roughly centered on the page.
        text_width_ratio = (span_x1 - span_x0) / page_width
        if text_width_ratio < 0.9 and abs((span_x0 + span_x1) / 2 - page_width / 2) < page_width * 0.3:
            return True
        # Or if it's clearly left-aligned but still significantly larger than body text.
        if span_x0 < page_width * 0.15:
            return True

    return False


def extract_outline_from_pdf(pdf_path):
    """
    Extracts the title and a structured outline (H1, H2, H3) from a PDF.
    """
    title = ""
    outline = []
    
    try:
        document = fitz.open(pdf_path)
        
        # --- Pre-pass for Header/Footer Detection ---
        # Collect candidates based on consistent position across many pages to filter them out later.
        header_footer_candidates = defaultdict(int)
        if document.page_count > 0:
            page_height = document[0].rect.height
            top_margin_threshold = page_height * 0.1
            bottom_margin_threshold = page_height * 0.9

            for page_num in range(document.page_count):
                page = document[page_num]
                blocks = page.get_text("dict")["blocks"]
                for b in blocks:
                    if b['type'] == 0:
                        for line_dict in b["lines"]:
                            line_text = clean_text(" ".join([s["text"] for s in line_dict["spans"]]))
                            line_y0 = line_dict["bbox"][1]
                            
                            if line_text and len(line_text) > 3 and not re.fullmatch(r'^\s*\d+\s*$', line_text) and \
                               not is_garbled_text(line_text) and not re.fullmatch(r'[-=_]{3,}', line_text) and \
                               re.search(r'(http[s]?://\S+|www\.\S+)', line_text, re.IGNORECASE) is None: # Exclude URLs
                                if line_y0 < top_margin_threshold or line_y0 > bottom_margin_threshold:
                                    header_footer_candidates[line_text] += 1
            
            header_footer_patterns = []
            for text, count in header_footer_candidates.items():
                if count > document.page_count * 0.5: # Text appearing on more than half the pages is likely a header/footer.
                    header_footer_patterns.append(text)
        else:
            header_footer_patterns = []


        # --- 1. Title Extraction (Prioritize Visual, Fallback to Metadata) ---
        visual_title_candidate = ""
        if document.page_count > 0:
            first_page = document[0]
            text_blocks = first_page.get_text("dict")["blocks"]
            
            first_page_spans = []
            for b in text_blocks:
                if b['type'] == 0:
                    for line in b["lines"]:
                        for span in line["spans"]:
                            first_page_spans.append({
                                "text": clean_text(span["text"]),
                                "size": round(span["size"], 1),
                                "bbox": span["bbox"],
                                "is_bold": "bold" in span["font"].lower() or "black" in span["font"].lower() or "heavy" in span["font"].lower(),
                                "font": span["font"]
                            })
            
            # Sort by top-most position, then by largest font size to find potential title elements.
            first_page_spans.sort(key=lambda x: (x["bbox"][1], -x["size"]))

            max_size_found_so_far = 0
            potential_title_spans = []
            
            # Find the largest font size that is likely part of a title.
            # Collect all large-font, vertically proximate spans on the first page, combine them.
            for span_info in first_page_spans:
                # Apply comprehensive filters for title candidates, including the improved is_garbled_text and URL check.
                if len(span_info["text"]) > 3 and not re.fullmatch(r'^\s*\d+\s*$', span_info["text"]) and \
                   not re.fullmatch(r'[-=_]{3,}', span_info["text"]) and not is_garbled_text(span_info["text"]) and \
                   re.search(r'(http[s]?://\S+|www\.\S+)', span_info["text"], re.IGNORECASE) is None and \
                   span_info["bbox"][1] < first_page.rect.height * 0.35: # Title usually in the top 35% of the page.
                    
                    # If this span is significantly larger than what we've seen, start a new title group.
                    if span_info["size"] > max_size_found_so_far + 0.5:
                        max_size_found_so_far = span_info["size"]
                        potential_title_spans = [span_info]
                    # If this span is relatively large (e.g., at least 70% of the max size found)
                    # AND is vertically close to the last collected title span, include it.
                    elif potential_title_spans and span_info["size"] >= max_size_found_so_far * 0.7 and \
                         abs(span_info["bbox"][1] - potential_title_spans[-1]["bbox"][1]) < span_info["size"] * 2.5: # Increased vertical tolerance
                        potential_title_spans.append(span_info)
                    elif not potential_title_spans and span_info["size"] > 0: # Handle first span if no max_size_found_so_far
                        max_size_found_so_far = span_info["size"]
                        potential_title_spans = [span_info]


            # Reconstruct title from collected spans, handling multi-line titles and horizontal spacing.
            if potential_title_spans:
                potential_title_spans.sort(key=lambda x: (x["bbox"][1], x["bbox"][0]))
                
                current_line_text_parts = []
                last_y_pos = -1
                last_x1_pos = -1
                
                for span_info in potential_title_spans:
                    # Check for new line based on significant vertical jump
                    # Or if it's the very first part
                    if not current_line_text_parts or (abs(span_info["bbox"][1] - last_y_pos) > span_info["size"] * 1.5): # Increased vertical tolerance for multi-line titles
                        if current_line_text_parts:
                            visual_title_candidate += " ".join(current_line_text_parts) + "\n" # Add newline for new visual line
                        current_line_text_parts = [span_info["text"]]
                    else:
                        # Check for horizontal spacing to decide if space is needed
                        # If the gap between current span's x0 and last span's x1 is small, concatenate without space
                        if span_info["bbox"][0] - last_x1_pos < span_info["size"] * 0.5: # Small horizontal gap
                            current_line_text_parts[-1] += span_info["text"]
                        else:
                            current_line_text_parts.append(span_info["text"])
                    
                    last_y_pos = span_info["bbox"][1]
                    last_x1_pos = span_info["bbox"][2]

                if current_line_text_parts:
                    visual_title_candidate += " ".join(current_line_text_parts)
                
                visual_title_candidate = clean_text(visual_title_candidate).strip()
                
                # Apply comprehensive filters to the final visual title candidate
                visual_title_candidate = filter_title_candidate(visual_title_candidate, document.page_count)

        # Assign title: prioritize the visually extracted title, then fallback to PDF metadata.
        if visual_title_candidate:
            title = visual_title_candidate
        elif document.metadata and document.metadata.get("title"):
            meta_title = clean_text(document.metadata.get("title"))
            # Filter metadata title using the same robust filters
            title = filter_title_candidate(meta_title, document.page_count)
        
        # Final fallback: use the first non-noise line from the first page if no suitable title is found.
        if not title and document.page_count > 0:
            first_page_text = document[0].get_text("text").strip()
            if first_page_text:
                for line in first_page_text.split('\n'):
                    cleaned_line = clean_text(line).strip()
                    # Apply the same robust filters to the fallback line
                    filtered_line = filter_title_candidate(cleaned_line, document.page_count)
                    if filtered_line: # If the line passes the filters
                        title = filtered_line
                        break
        
        # --- 2. Dynamic Font Size Grouping for Heading Levels ---
        # Analyze all font sizes to determine the most common body text font size, crucial for heading detection.
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
            # Find the most common font size among those likely to be body text (e.g., size >= 9 and below 20 points).
            filtered_sizes_for_body = {fs: count for fs, count in all_font_sizes_counts.items() if fs >= 9 and fs < 20}
            if filtered_sizes_for_body:
                avg_body_font_size = max(filtered_sizes_for_body, key=filtered_sizes_for_body.get)
            else: # Fallback if no sizes in typical body text range, pick most common overall (excluding very large/small sizes).
                    filtered_sizes_for_body = {fs: count for fs, count in all_font_sizes_counts.items() if fs >= 8 and fs < 30}
                    if filtered_sizes_for_body:
                        avg_body_font_size = max(filtered_sizes_for_body, key=filtered_sizes_for_body.get)
                    else:
                        avg_body_font_size = max(all_font_sizes_counts, key=all_font_sizes_counts.get) # Last resort if no suitable range is found.
        
        # Ensure a fallback average body font size if no suitable one is identified.
        if avg_body_font_size == 0 and document.page_count > 0:
            sample_span = None
            for b in document[0].get_text("dict")["blocks"]:
                if b['type'] == 0 and b["lines"]:
                    sample_span = b["lines"][0]["spans"][0]
                    break
            avg_body_font_size = round(sample_span["size"], 1) if sample_span else 10 # Default to 10 points.


        # Collect all potential headings with their font sizes and positions across all pages.
        potential_headings_with_sizes = []
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
                        if not full_line_text_cleaned: continue

                        # Skip lines identified as garbled text before further processing.
                        if is_garbled_text(full_line_text_cleaned):
                            continue

                        first_span_in_group = current_line_spans[0]
                        line_font_size = round(first_span_in_group["size"], 1)
                        line_is_bold = "bold" in first_span_in_group["font"].lower() or "black" in first_span_in_group["font"].lower() or "heavy" in first_span_in_group["font"].lower()
                        line_bbox = (min(s["bbox"][0] for s in current_line_spans), min(s["bbox"][1] for s in current_line_spans),
                                      max(s["bbox"][2] for s in current_line_spans), max(s["bbox"][3] for s in current_line_spans))
                        
                        # Use the refined is_likely_heading function to determine if the line is a heading.
                        if is_likely_heading(full_line_text_cleaned, line_font_size, line_is_bold, page_width, line_bbox, avg_body_font_size, header_footer_patterns, first_span_in_group["font"], page_num, document.page_count):
                            potential_headings_with_sizes.append({
                                "text": full_line_text_cleaned,
                                "size": line_font_size,
                                "is_bold": line_is_bold,
                                "page": page_num, # 0-indexed page for internal consistency.
                                "bbox": line_bbox,
                                "font": first_span_in_group["font"]
                            })
        
        # Sort potential headings by page number, then y-position, then font size (descending) to establish a logical order.
        potential_headings_with_sizes.sort(key=lambda x: (x["page"], x["bbox"][1], -x["size"]))


        # Assign H1, H2, H3 based on relative font sizes among detected headings.
        h_level_map = {}
        if potential_headings_with_sizes:
            # Get all distinct font sizes from potential headings
            unique_heading_sizes = sorted(list(set([h["size"] for h in potential_headings_with_sizes])), reverse=True)
            
            # Skip the largest font size (likely title), shift heading levels up by one
            if len(unique_heading_sizes) >= 2:
                h_level_map[unique_heading_sizes[1]] = "H1"
            if len(unique_heading_sizes) >= 3:
                h_level_map[unique_heading_sizes[2]] = "H2"
            if len(unique_heading_sizes) >= 4:
                h_level_map[unique_heading_sizes[3]] = "H3"


            # For any other unique heading sizes, assign them to the closest higher or equal defined level.
            # This ensures that smaller font sizes don't get assigned higher levels than larger ones.
            defined_sizes = sorted(h_level_map.keys()) # Sort ascending for easier mapping
            for size in unique_heading_sizes:
                if size not in h_level_map:
                    assigned_level = None
                    for i, defined_size in enumerate(defined_sizes):
                        if size >= defined_size - 0.5: # If current size is very close to or larger than a defined size
                            assigned_level = h_level_map[defined_size]
                            break
                    
                    if assigned_level:
                        h_level_map[size] = assigned_level
                    else: # If smaller than all defined sizes, assign to the lowest level (H3 if exists, else H2, else H1)
                        if "H3" in h_level_map.values():
                            h_level_map[size] = "H3"
                        elif "H2" in h_level_map.values():
                            h_level_map[size] = "H2"
                        elif "H1" in h_level_map.values():
                            h_level_map[size] = "H1"


        # --- 3. Iterate through collected headings and build the final outline ---
        seen_headings_tracker = set() # Used to prevent immediate visual and semantic duplicates.
        
        last_added_heading_level_val = 0 # Tracks the level of the last added heading to enforce hierarchy.
        last_added_heading_page = -1

        for heading_info in potential_headings_with_sizes:
            full_line_text_cleaned = heading_info["text"] # Use the cleaned text for consistency
            line_font_size = heading_info["size"]
            page_num = heading_info["page"] # Already 0-indexed.

            assigned_level = h_level_map.get(line_font_size)
            
            if assigned_level:
                current_level_val = int(assigned_level[1]) # Convert "H1" to 1, "H2" to 2, etc.

                # --- Prevent Title Repetition in Outline ---
                # Compare the heading to the extracted document title to avoid adding the title as a heading.
                if title:
                    normalized_title = re.sub(r'[^\w\s]', '', title).lower().strip()
                    normalized_heading = re.sub(r'[^\w\s]', '', full_line_text_cleaned).lower().strip() # Use cleaned text for comparison

                    # Check if heading is identical or a significant part of the title, especially on early pages.
                    if normalized_title == normalized_heading or \
                       (len(normalized_title) > 5 and normalized_heading in normalized_title and \
                        abs(len(normalized_title) - len(normalized_heading)) < 15 and page_num < 3) or \
                       (len(normalized_heading) > 5 and normalized_title in normalized_heading and \
                        abs(len(normalized_heading) - len(normalized_title)) < 15 and page_num < 3):
                        continue

                # --- Prevent Adding Duplicate Headings (same text on same or adjacent pages) ---
                # Normalize text for robust deduplication.
                normalized_text_for_dedupe = re.sub(r'[\d\W_]+', '', full_line_text_cleaned).lower() # Use cleaned text for dedupe
                
                is_duplicate = False
                for prev_norm_text, prev_page, prev_level_id in seen_headings_tracker:
                    if normalized_text_for_dedupe == prev_norm_text and abs(page_num - prev_page) <= 1 and assigned_level == prev_level_id:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    # --- Enforce Hierarchy (H1 -> H2 -> H3) ---
                    # Promote a heading's level if it's much deeper than the previous heading,
                    # ensuring a logical hierarchical flow.
                    if last_added_heading_level_val != 0 and current_level_val > last_added_heading_level_val + 1:
                        promoted_level_val = last_added_heading_level_val + 1
                        assigned_level = f"H{promoted_level_val}"
                        current_level_val = promoted_level_val
                    
                    outline.append({
                        "level": assigned_level,
                        "text": full_line_text_cleaned, # Use cleaned text for the output
                        "page": page_num # Keep 0-indexed for internal processing.
                    })
                    seen_headings_tracker.add((normalized_text_for_dedupe, page_num, assigned_level))
                    last_added_heading_level_val = current_level_val
                    last_added_heading_page = page_num
        
        # Final pass: page numbers are already 0-indexed, so no change needed here.
        final_outline = outline # No need to create a new list or modify page numbers

        # Sort by page, then by numerical level (H1 before H2 before H3 for same page) for consistent output.
        final_outline.sort(key=lambda x: (x["page"], int(x["level"][1])))

        document.close()

    except Exception as e:
        print(f"Error processing {pdf_path}: {e}")
        return {"title": "", "outline": []}

    return {"title": title, "outline": final_outline}


def main():
    input_dir = "input" # Assuming your PDFs are in an 'input' folder
    output_dir = "output" # Output JSONs will be saved in an 'output' folder

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Get all PDF files from the input directory
    pdf_files = [f for f in os.listdir(input_dir) if f.lower().endswith(".pdf")]

    for pdf_file in pdf_files:
        pdf_path = os.path.join(input_dir, pdf_file)
        output_filename = os.path.splitext(pdf_file)[0] + ".json"
        output_path = os.path.join(output_dir, output_filename)

        print(f"Processing {pdf_file}...")
        result = extract_outline_from_pdf(pdf_path)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=4, ensure_ascii=False)
        print(f"Saved outline to {output_path}")


if __name__ == "__main__":
    main()
