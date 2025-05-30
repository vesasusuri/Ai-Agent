# Receipt Processor

A web application that processes receipts using OCR to extract items and prices, specifically optimized for Albanian Lek (L) currency format.

## Prerequisites

1. Python 3.7 or higher
2. Tesseract OCR - Install from:
   - Windows: https://github.com/UB-Mannheim/tesseract/wiki
   - Linux: `sudo apt-get install tesseract-ocr`
   - macOS: `brew install tesseract`

3. Poppler (for PDF processing) - Install from:
   - Windows: Download from http://blog.alivate.com.au/poppler-windows/
   - Linux: `sudo apt-get install poppler-utils`
   - macOS: `brew install poppler`

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd receipt-processor
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Start the Flask application:
   ```bash
   python app.py
   ```

2. Open your web browser and navigate to:
   ```
   http://localhost:5000
   ```

3. Upload a receipt by either:
   - Dragging and dropping an image/PDF onto the upload area
   - Clicking the upload area to select a file

4. The application will process the receipt and display:
   - Extracted items and their prices
   - Receipt date
   - Total amount
   - History of previously processed receipts

## Supported Formats

- Images: PNG, JPG, JPEG
- Documents: PDF

## Features

- OCR-based text extraction
- Automatic item and price detection
- Albanian Lek (L) currency support
- Receipt history tracking
- Drag-and-drop file upload
- Responsive web interface

## Troubleshooting

1. If Tesseract is not found, ensure it's installed and the path is correct in the code
2. For PDF processing issues, verify Poppler is installed and accessible
3. Check the console for any error messages
4. Ensure the receipt images are clear and well-lit for best results 