import pytesseract
import cv2
import numpy as np
from PIL import Image
from pdf2image import convert_from_bytes
import re
from datetime import datetime
from dateutil.parser import parse
import json
import os
from pathlib import Path
import logging
import shutil

class ReceiptProcessor:
    CURRENCY_PATTERNS = {
        'USD': r'(?:\$\s*)?(\d+(?:\.\d{2})?)',  # $12.34 or 12.34
        'EUR': r'(?:€\s*)?(\d+(?:[,.]\d{2})?)',  # €12,34 or 12.34
        'ALL': r'(?:L(?:ek)?\s*)?(\d+(?:[,.]\d{2})?)',  # <-- Updated for decimals
        'GBP': r'(?:£\s*)?(\d+(?:\.\d{2})?)',  # £12.34 or 12.34
    }

    CURRENCY_SYMBOLS = {
        'USD': '$',
        'EUR': '€',
        'ALL': 'L',
        'GBP': '£',
    }

    def __init__(self, currency='USD'):
        self.date_pattern = r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{2,4}[-/]\d{1,2}[-/]\d{1,2}'
        self.set_currency(currency)

        # Cross-platform Tesseract check
        tesseract_cmd = shutil.which("tesseract")
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            print(f"Found Tesseract at: {tesseract_cmd}")
        else:
            raise Exception(
                "Tesseract not found. Please install it:\n"
                "- On Mac: brew install tesseract\n"
                "- On Windows: https://github.com/UB-Mannheim/tesseract/wiki"
            )

        # Try to find poppler in common installation locations
        self.poppler_path = None
        possible_paths = [
            str(Path.home() / "poppler" / "bin"),
            str(Path.home() / "poppler" / "Library" / "bin"),
            r"C:\Program Files\poppler\Library\bin",
            r"C:\Program Files\poppler\bin",
            r"C:\poppler\Library\bin",
            r"C:\poppler\bin"
        ]
        for path in possible_paths:
            if os.path.exists(path):
                self.poppler_path = path
                print(f"Found Poppler at: {path}")
                break

    def set_currency(self, currency):
        """Set the currency and update patterns accordingly."""
        if currency not in self.CURRENCY_PATTERNS:
            raise ValueError(f"Unsupported currency: {currency}")
        
        self.currency = currency
        self.currency_symbol = self.CURRENCY_SYMBOLS[currency]
        self.price_pattern = self.CURRENCY_PATTERNS[currency]
        self.item_pattern = f'^[A-Za-z0-9\s\-&]+\s+{self.price_pattern}'

    def normalize_price(self, price_str):
        """Normalize price string to float based on currency."""
        price_str = price_str.replace(self.currency_symbol, '').replace('Lek', '').strip()
        price_str = price_str.replace(',', '.')  # Convert European format if needed
        try:
            return float(price_str) if price_str else 0.0
        except ValueError:
            return 0.0

    def format_price(self, price):
        """Format price with appropriate currency symbol."""
        if self.currency == 'ALL':
            return f"L{int(price)}"  # Albanian Lek doesn't use decimals
        else:
            return f"{self.currency_symbol}{price:.2f}"

    def process_image(self, image_bytes):
        """Process image bytes and return extracted text."""
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # Preprocess the image
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Apply adaptive thresholding
            thresh = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY, 11, 2
            )
            
            # Additional preprocessing
            # 1. Increase image size to improve OCR
            scaled = cv2.resize(thresh, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            
            # 2. Apply denoising
            denoised = cv2.fastNlMeansDenoising(scaled)
            
            # Convert to PIL Image
            pil_image = Image.fromarray(denoised)
            
            # Extract text using Tesseract with specific configuration
            text = pytesseract.image_to_string(
                pil_image,
                config='--psm 6 --oem 3 -l eng'  # Use English language and assume uniform text block
            )
            
            if not text.strip():
                raise Exception("No text was extracted from the image. The image might be too blurry or the text might be unclear.")
            
            return text
            
        except Exception as e:
            print(f"Error in process_image: {str(e)}")
            raise

    def process_pdf(self, pdf_bytes):
        """Convert PDF to images and process each page."""
        # Remove the poppler_path check for Mac/Homebrew
        pages = convert_from_bytes(pdf_bytes)  # No poppler_path needed on Mac with Homebrew
        text = ""
        for page in pages:
            text += pytesseract.image_to_string(page)
        return text

    def extract_date(self, text):
        """Extract date from text."""
        # Look for date patterns in various formats
        date_patterns = [
            r'\d{2}\.\d{2}\.\d{4}',  # DD.MM.YYYY
            r'\d{2}/\d{2}/\d{4}',    # DD/MM/YYYY
            r'\d{2}-\d{2}-\d{4}',    # DD-MM-YYYY
            r'\d{4}-\d{2}-\d{2}',    # YYYY-MM-DD
            r'\d{2}\.\d{2}\.\d{2}',  # DD.MM.YY
        ]
        
        for line in text.split('\n'):
            for pattern in date_patterns:
                match = re.search(pattern, line)
                if match:
                    try:
                        date_str = match.group(0)
                        # Parse the date
                        parsed_date = parse(date_str)
                        return parsed_date.strftime('%Y-%m-%d')
                    except:
                        continue
        return None

    def extract_total(self, text):
        """Extract total amount from text."""
        # Look for total amount patterns
        total_patterns = [
            (r'total.*?(\d+(?:[,.]\d{2,3})?)', 10),  # General total with high priority
            (r'amount.*?(\d+(?:[,.]\d{2,3})?)', 9),
            (r'sum.*?(\d+(?:[,.]\d{2,3})?)', 8),
            (r'total\s+in\s+all.*?(\d+(?:[,.]\d{2,3})?)', 7),
            (r'grand\s+total.*?(\d+(?:[,.]\d{2,3})?)', 6),
        ]
        
        candidates = []
        lines = text.split('\n')
        
        # First pass: look for explicit total markers
        for line in lines:
            line = line.lower()
            for pattern, priority in total_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    try:
                        amount_str = match.group(1)
                        # Remove any currency symbols and normalize
                        amount_str = ''.join(c for c in amount_str if c.isdigit() or c in '.,')
                        amount = float(amount_str.replace(',', '.'))
                        candidates.append((amount, priority))
                    except:
                        continue
        
        # If we found candidates with total markers, use the highest priority one
        if candidates:
            candidates.sort(key=lambda x: (-x[1], -x[0]))  # Sort by priority then amount
            return candidates[0][0]
        
        # Second pass: find the largest number that looks like a total
        all_numbers = []
        for line in lines:
            matches = re.findall(r'(\d+(?:[,.]\d{2,3})?)', line)
            for match in matches:
                try:
                    amount_str = ''.join(c for c in match if c.isdigit() or c in '.,')
                    amount = float(amount_str.replace(',', '.'))
                    if amount > 0:
                        all_numbers.append(amount)
                except:
                    continue
        
        if all_numbers:
            return max(all_numbers)
        
        return None

    def extract_items(self, text):
        """Extract items and their prices for any currency."""
        items = []
        lines = text.split('\n')
        # Use the price pattern for the selected currency
        price_pattern = self.price_pattern

        # This regex matches: [item name] [price] (price at end of line)
        item_line_pattern = re.compile(rf"(.+?)\s+{price_pattern}$")

        # Words that indicate this is not an item
        non_item_words = {
            'total', 'subtotal', 'cash', 'change', 'vat', 'tax', 'receipt',
            'business', 'operator', 'address', 'terminal', 'reference', 'invoice',
            'merchant', 'date', 'time', 'order', 'id:', 'nr:', 'no:', 'code'
        }

        for line in lines:
            line = line.strip()
            if not line:
                continue
            line_lower = line.lower()
            if any(word in line_lower for word in non_item_words):
                continue

            match = item_line_pattern.match(line)
            if match:
                item_name = match.group(1).strip()
                price_str = match.group(2).replace(',', '.')
                try:
                    price = float(price_str)
                    if len(item_name) > 2 and not item_name.isdigit() and price > 0:
                        items.append({
                            'item': item_name,
                            'price': self.format_price(price),
                            'category': self.categorize_item(item_name)
                        })
                except ValueError:
                    continue

        return items

    def process_receipt(self, file_bytes, file_type):
        """Main processing function."""
        try:
            if file_type == 'pdf':
                print("Processing PDF file...")
                text = self.process_pdf(file_bytes)
            else:
                print("Processing image file...")
                text = self.process_image(file_bytes)
            
            print("\n=== EXTRACTED RAW TEXT ===")
            print(text)
            print("=== END OF RAW TEXT ===\n")
            
            # Split text into lines and show each line for debugging
            print("\n=== LINE BY LINE ANALYSIS ===")
            for i, line in enumerate(text.split('\n'), 1):
                if line.strip():
                    print(f"Line {i}: '{line.strip()}'")
            print("=== END OF LINE ANALYSIS ===\n")
            
            result = {
                'date': self.extract_date(text),
                'total': self.extract_total(text),
                'items': self.extract_items(text),
                'raw_text': text
            }
            
            print("\n=== EXTRACTION RESULTS ===")
            print(f"Date found: {result['date']}")
            print(f"Total found: {result['total']}")
            print(f"Number of items found: {len(result['items'])}")
            if result['items']:
                print("Items found:")
                for item in result['items']:
                    print(f"- {item['item']}: {item['price']}")
            else:
                print("No items were detected!")
            print("=== END OF RESULTS ===\n")
            
            return result
            
        except Exception as e:
            print(f"Error in process_receipt: {str(e)}")
            raise

    def save_to_json(self, data, filename):
        """Save extracted data to JSON file."""
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)

    def categorize_item(self, item_name):
        item_lower = item_name.lower()
        if any(word in item_lower for word in ["shirt", "pants", "jeans", "dress", "shoes", "jacket", "coat", "clothes", "t-shirt"]):
            return "clothes"
        if any(word in item_lower for word in ["bread", "milk", "egg", "cheese", "meat", "apple", "banana", "food", "pizza", "burger", "salad", "rice", "chicken", "beef", "fish", "vegetable", "fruit"]):
            return "food"
        # Add more categories as needed
        return "other"