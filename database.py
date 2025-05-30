import sqlite3
import json
from datetime import datetime

class ReceiptDatabase:
    def __init__(self, db_path='receipts.db'):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize the database with required tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create receipts table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            total REAL,
            currency TEXT,
            raw_text TEXT,
            file_name TEXT,
            upload_timestamp TEXT,
            file_type TEXT
        )
        ''')

        # Create items table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS receipt_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            receipt_id INTEGER,
            item_name TEXT,
            price REAL,
            FOREIGN KEY (receipt_id) REFERENCES receipts (id)
        )
        ''')

        conn.commit()
        conn.close()

    def save_receipt(self, receipt_data, file_name, file_type):
        """Save receipt data to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Insert receipt data
            cursor.execute('''
            INSERT INTO receipts (date, total, currency, raw_text, file_name, upload_timestamp, file_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                receipt_data.get('date'),
                receipt_data.get('total'),
                receipt_data.get('currency'),
                receipt_data.get('raw_text'),
                file_name,
                datetime.now().isoformat(),
                file_type
            ))
            
            receipt_id = cursor.lastrowid

            # Insert items
            items = receipt_data.get('items', [])
            for item in items:
                # Handle Albanian Lek prices (format: L1234 or L1,234)
                price_str = str(item['price'])
                # Remove 'L' prefix and any commas
                price_str = price_str.strip('L').replace(',', '')
                try:
                    price = float(price_str)
                except ValueError:
                    price = 0.0

                cursor.execute('''
                INSERT INTO receipt_items (receipt_id, item_name, price)
                VALUES (?, ?, ?)
                ''', (receipt_id, item['item'], price))

            conn.commit()
            return receipt_id

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def get_all_receipts(self):
        """Get all receipts with their items."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        receipts = []
        cursor.execute('''
        SELECT * FROM receipts ORDER BY upload_timestamp DESC
        ''')
        
        for receipt in cursor.fetchall():
            receipt_dict = dict(receipt)
            
            # Get items for this receipt
            cursor.execute('''
            SELECT item_name, price FROM receipt_items WHERE receipt_id = ?
            ''', (receipt_dict['id'],))
            
            items = [{'item': row[0], 'price': row[1]} for row in cursor.fetchall()]
            receipt_dict['items'] = items
            receipts.append(receipt_dict)

        conn.close()
        return receipts

    def export_to_json(self, file_path='all_receipts.json'):
        """Export all receipts to a JSON file."""
        receipts = self.get_all_receipts()
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(receipts, f, indent=2, ensure_ascii=False)
        return file_path

    def get_receipt_by_id(self, receipt_id):
        """Get a specific receipt by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM receipts WHERE id = ?', (receipt_id,))
        receipt = dict(cursor.fetchone())

        cursor.execute('SELECT item_name, price FROM receipt_items WHERE receipt_id = ?', (receipt_id,))
        items = [{'item': row[0], 'price': row[1]} for row in cursor.fetchall()]
        receipt['items'] = items

        conn.close()
        return receipt

    def clear_database(self):
        """Delete all receipts from the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM receipts")
        conn.commit()
        conn.close()