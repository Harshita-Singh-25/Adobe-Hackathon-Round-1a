# PDF Outline Extractor

A sophisticated Python solution that extracts document titles and hierarchical headings (H1-H4) from PDF files, outputting structured JSON for the hackathon challenge.

## 🚀 Solution Overview

This tool uses advanced PDF analysis to identify document structure through:
- **Multi-strategy title detection** (visual analysis + metadata + text patterns)
- **Intelligent heading recognition** (font analysis + positioning + formatting cues)
- **Robust text cleaning** (handles PDF artifacts, garbled text, hyphenation)
- **Smart hierarchy assignment** (logical H1-H4 level mapping)

## 🏗️ Architecture

### Core Components

**Text Processing Pipeline:**
- `clean_text()` - Removes PDF artifacts, fixes spacing/hyphenation
- `is_garbled_text()` - Filters corrupted text using character analysis
- `filter_title_candidate()` - Validates and cleans potential titles

**Extraction Engine:**
- **Title Detection**: Scans top 40% of first page for largest/boldest text, falls back to metadata
- **Font Analysis**: Calculates body text baseline, identifies heading font sizes
- **Heading Recognition**: Multi-factor analysis (size + weight + positioning + content)
- **Hierarchy Mapping**: Assigns H1-H4 levels based on relative font sizes

**Smart Filtering:**
- Excludes headers/footers, page numbers, bullets, URLs
- Prevents duplicate headings across pages
- Handles single vs multi-page document differences


## 🎯 Usage

1. **Place PDFs** in mounted `input/` directory
2. **Run container** - automatically processes all PDFs
3. **Collect results** from `output/` directory (filename.json for each filename.pdf)

The solution handles the entire pipeline automatically:
- Discovers all PDF files in input directory
- Processes each using the sophisticated extraction logic
- Generates corresponding JSON files with proper formatting
- Completes within performance constraints

## 🔧 Technical Approach

### Algorithm Highlights

1. **Font Size Analysis**: Determines body text baseline from most common font sizes (9-20pt range)
2. **Heading Detection**: Text qualifies as heading if:
   - Font size >5% larger than body text OR bold formatting
   - Proper positioning (left-aligned, reasonable width)
   - Content filtering (not page numbers, bullets, etc.)
3. **Level Assignment**: Maps font sizes to hierarchy (largest=H1, progressively smaller=H2-H4)
4. **Quality Control**: Combines consecutive short headings, prevents level skipping

### Key Features
- **Garbled Text Detection**: Multi-heuristic approach (character ratios, repetition patterns)
- **Layout Awareness**: Considers text positioning, width ratios, page margins  
- **Multilingual Support**: Handles Unicode, special characters, various font systems
- **Performance Optimized**: Processes 50-page PDFs in <10 seconds

## 📊 Output Format

```json
{
  "title": "Document Title Here", 
  "outline": [
    {"level": "H1", "text": "Chapter 1: Introduction", "page": 0},
    {"level": "H2", "text": "Background", "page": 1},
    {"level": "H3", "text": "Problem Statement", "page": 2}
  ]
}
```

## 🐳 Docker Setup

### Build & Run
```bash
# Build
docker build --platform linux/amd64 -t pdf-extractor:latest .

# Run  
docker run --rm \
  -v $(pwd)/input:/app/input \
  -v $(pwd)/output:/app/output \
  --network none \
  pdf-extractor:latest
```

### Container Specs
- **Platform**: linux/amd64 (AMD64 architecture)
- **Dependencies**: Python 3.9 + PyMuPDF + system graphics libraries
- **Performance**: <10s for 50-page PDFs, <200MB image size
- **Operation**: Completely offline, no network access

## 📁 Project Structure

```
├── Dockerfile          # AMD64-compatible container config
├── requirements.txt     # PyMuPDF>=1.18.14  
├── main.py             # Complete extraction pipeline
└── README.md           # This documentation
```




