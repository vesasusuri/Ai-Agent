import streamlit as st
import pandas as pd
from ocr_processor import ReceiptProcessor
from database import ReceiptDatabase
import json
import os
from datetime import datetime
import re
import io
import calendar

st.set_page_config(page_title="Receipt Processor", layout="wide")

# Initialize database
db = ReceiptDatabase()

QUESTIONS_FILE = "chat_questions.jsonl"

def save_question_to_file(question):
    with open(QUESTIONS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"question": question, "timestamp": datetime.now().isoformat()}) + "\n")

OPTIONAL_ANSWERS = {
    "no_receipts": "No receipts found for that date.",
    "no_items": "No items found for that date.",
    "default": "Sorry, I can answer questions like 'How much did I spend on food in May 2025?' or 'What did I buy on 2025-03-05?'."
}

def answer_question(question, db):
    q = question.lower()

    # Handle "last may" or "this may"
    this_year = datetime.now().year
    last_year = this_year - 1
    month_match = re.search(r'(last|this)?\s*(january|february|march|april|may|june|july|august|september|october|november|december)', q)
    year = None
    month = None
    if month_match:
        which = month_match.group(1)
        month_str = month_match.group(2)
        month = list(calendar.month_name).index(month_str.capitalize())
        if which == "last":
            year = last_year
        else:
            year = this_year

    # Category and month/year queries
    cat_match = re.search(r'spend on (\w+)(?: in| for)? (\w+)? ?(\d{4})?', q)
    if cat_match:
        category = cat_match.group(1)
        # Use parsed month/year if available
        month_str = cat_match.group(2) or (month and calendar.month_name[month])
        year_str = cat_match.group(3) or (str(year) if year else None)
        month = None
        year = None
        if month_str:
            try:
                month = list(calendar.month_name).index(month_str.capitalize())
            except ValueError:
                month = None
        if year_str:
            year = int(year_str)
        receipts = db.get_all_receipts()
        total = 0
        for r in receipts:
            r_date = r.get('date')
            if not r_date:
                continue
            try:
                dt = datetime.strptime(r_date, "%Y-%m-%d")
            except:
                continue
            if (not month or dt.month == month) and (not year or dt.year == year):
                for item in r.get('items', []):
                    if item.get('category') == category:
                        try:
                            total += float(item.get('price').replace('L','').replace('$','').replace('€','').replace('£',''))
                        except:
                            continue
        if total > 0:
            return f"You spent a total of {total} on {category} in {month_str or ''} {year_str or ''}."
        else:
            return f"No {category} purchases found for {month_str or ''} {year_str or ''}."

    # --- Existing logic for specific date ---
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', question)
    if date_match:
        date = date_match.group(1)
        receipts = db.get_all_receipts()
        items = []
        total = 0
        unwanted = {"delivery", "service fee", "tira"}
        seen = set()
        for r in receipts:
            if r.get('date') == date and r.get('items'):
                for item in r['items']:
                    name = item['item'].strip()
                    # Filter unwanted and deduplicate
                    if not name or any(u in name.lower() for u in unwanted):
                        continue
                    if name not in seen:
                        items.append(item)
                        seen.add(name)
        # Calculate total only for shown items
        for item in items:
            price_str = item.get('price', '0')
            # Extract the first number (integer or decimal) from the price string
            match = re.search(r'(\d+(?:[.,]\d+)?)', str(price_str).replace(',', '.'))
            if match:
                try:
                    total += float(match.group(1))
                except:
                    continue
        if items:
            items_md = "\n".join([f"- {i['item']}" for i in items])
            return f"On {date}, you spent a total of **{total}**.\n\nItems purchased:\n{items_md}"
        else:
            return f"No items found for {date}."
    receipts = db.get_all_receipts()
    if not receipts:
        return OPTIONAL_ANSWERS["no_receipts"]
    return OPTIONAL_ANSWERS["default"]

# Create tabs for different views
tab1, tab2, tab3 = st.tabs(["Upload Receipt", "View History", "Chatbot"])

with tab1:
    st.title("Receipt Data Extractor")
    st.write("Upload your receipt (image or PDF) to extract structured data")

    # Currency selector
    currency = st.selectbox(
        "Select Currency",
        options=['USD', 'EUR', 'ALL', 'GBP'],
        format_func=lambda x: {
            'USD': '$ (US Dollar)',
            'EUR': '€ (Euro)',
            'ALL': 'L (Albanian Lek)',
            'GBP': '£ (British Pound)'
        }[x]
    )

    # Initialize the receipt processor with selected currency
    processor = ReceiptProcessor(currency=currency)

    # File uploader
    uploaded_file = st.file_uploader("Choose a receipt file", type=['png', 'jpg', 'jpeg', 'pdf'])

    if uploaded_file is not None:
        try:
            # Create a spinner while processing
            with st.spinner('Processing receipt...'):
                # Get file type
                file_type = 'pdf' if uploaded_file.type == 'application/pdf' else 'image'
                
                # Process the receipt
                result = processor.process_receipt(uploaded_file.read(), file_type)
                
                # Add currency information to the result
                result['currency'] = currency
                
                # Save to database
                db.save_receipt(result, uploaded_file.name, file_type)
                
                # Display results in columns
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("Receipt Details")
                    st.write(f"Date: {result.get('date', 'Not found')}")
                    if result.get('total') is not None:
                        st.write(f"Total Amount: {processor.format_price(result['total'])}")
                    else:
                        st.write("Total Amount: Not found")
                    
                    st.subheader("Items")
                    if result.get('items'):
                        items_df = pd.DataFrame(result['items'])
                        st.dataframe(items_df)
                    else:
                        st.warning("No items detected")
                
                with col2:
                    st.subheader("Raw Extracted Text")
                    if result.get('raw_text'):
                        st.text_area("", result['raw_text'], height=300, key="raw_text_upload")
                    else:
                        st.warning("No text was extracted")
                
                # Export current receipt to JSON
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"receipt_data_{timestamp}.json"
                
                with open(filename, 'w') as f:
                    json.dump(result, f, indent=4)
                
                st.download_button(
                    label="Download Receipt JSON",
                    data=open(filename, 'r').read(),
                    file_name=filename,
                    mime="application/json"
                )
                
                # Clean up the temporary file
                os.remove(filename)
                
        except Exception as e:
            st.error(f"Error processing receipt: {str(e)}")

with tab2:
    st.title("Receipt History")
    
    # Add export buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Export All to JSON"):
            json_file = db.export_to_json()
            with open(json_file, 'r') as f:
                st.download_button(
                    label="Download All Receipts (JSON)",
                    data=f.read(),
                    file_name="all_receipts.json",
                    mime="application/json"
                )
            os.remove(json_file)
    
    # Display all receipts
    receipts = db.get_all_receipts()
    if receipts:
        for receipt in receipts:
            with st.expander(f"Receipt: {receipt['file_name']} ({receipt['upload_timestamp']})"):
                st.write(f"Date: {receipt.get('date', 'Not found')}")
                st.write(f"Total: {receipt.get('total', 'Not found')} {receipt.get('currency', '')}")
                
                if receipt.get('items'):
                    st.subheader("Items")
                    items_df = pd.DataFrame(receipt['items'])
                    st.dataframe(items_df)
                
                st.subheader("Raw Text")
                st.text_area("", receipt.get('raw_text', ''), height=100, key=f"raw_text_{receipt['id']}")
    else:
        st.info("No receipts in database yet. Upload some receipts to see them here!")

with tab3:
    st.header("Receipts Chatbot")

    # --- Show all food items from uploaded receipts ---
    receipts = db.get_all_receipts()
    food_items = []
    for r in receipts:
        date = r.get('date', '')
        for item in r.get('items', []):
            # If you use the category field as in previous answers:
            if item.get('category') == 'food':
                food_items.append({
                    'date': date,
                    'item': item.get('item', ''),
                    'price': item.get('price', '')
                })
            # If you don't have a category field, use keywords:
            # if any(word in item.get('item', '').lower() for word in ["bread", "milk", "egg", "cheese", "meat", "apple", "banana", "food", "pizza", "burger", "salad", "rice", "chicken", "beef", "fish", "vegetable", "fruit"]):
            #     food_items.append({...})



    # Use session state to store chat history
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Custom CSS for Messenger-style chat
    st.markdown("""
    <style>
    .chat-container {
        max-width: 600px;
        margin: 0 auto;
        padding-bottom: 16px;
    }
    .chat-row {
        display: flex;
        align-items: flex-end;
        margin-bottom: 12px;
    }
    .chat-row.user {
        flex-direction: row-reverse;
    }
    .chat-avatar {
        width: 38px;
        height: 38px;
        border-radius: 50%;
        margin: 0 8px;
        object-fit: cover;
        border: 2px solid #fff;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    }
    .chat-bubble {
        padding: 12px 18px;
        border-radius: 20px;
        max-width: 70%;
        font-size: 1.1em;
        line-height: 1.4;
        margin: 0 4px;
        word-break: break-word;
    }
    .chat-bubble.user {
        background: #2563eb;
        color: #fff;
        border-bottom-right-radius: 5px;
        border-bottom-left-radius: 20px;
        border-top-left-radius: 20px;
        border-top-right-radius: 20px;
    }
    .chat-bubble.assistant {
        background: #f0f0f0;
        color: #222;
        border-bottom-left-radius: 5px;
        border-bottom-right-radius: 20px;
        border-top-left-radius: 20px;
        border-top-right-radius: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

    # Avatars (replace with your own images if you want)
    user_avatar = "https://randomuser.me/api/portraits/men/32.jpg"
    assistant_avatar = "https://randomuser.me/api/portraits/women/44.jpg"

    # User input at the bottom
    user_question = st.chat_input("Ask a question about your receipts:")

    # If user sends a message, process and append to chat history
    if user_question:
        st.session_state.chat_history.append({"role": "user", "content": user_question})
        answer = answer_question(user_question, db)
        st.session_state.chat_history.append({"role": "assistant", "content": answer})
        save_question_to_file(user_question)  # Save question to file

    # Display chat history above the input
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            st.markdown(
                f'''
                <div class="chat-row user">
                    <img src="{user_avatar}" class="chat-avatar">
                    <div class="chat-bubble user">{msg["content"]}</div>
                </div>
                ''',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f'''
                <div class="chat-row assistant">
                    <img src="{assistant_avatar}" class="chat-avatar">
                    <div class="chat-bubble assistant">{msg["content"]}</div>
                </div>
                ''',
                unsafe_allow_html=True
            )
    st.markdown('</div>', unsafe_allow_html=True)

# Add a button to download chat history as JSON
if st.session_state.chat_history:
    chat_json = json.dumps(st.session_state.chat_history, indent=2, ensure_ascii=False)
    st.download_button(
        label="Download Chat History (JSON)",
        data=chat_json,
        file_name="chat_history.json",
        mime="application/json"
    )

# Add usage instructions
with st.expander("Usage Instructions"):
    st.write("""
    1. Select the currency of your receipt
    2. Click the 'Browse files' button to upload your receipt
    3. Wait for the processing to complete
    4. Review the extracted data
    5. Download the JSON file with all extracted information
    
    Supported file types:
    - Images (PNG, JPG, JPEG)
    - PDF documents
    
    Supported currencies:
    - USD (US Dollar)
    - EUR (Euro)
    - ALL (Albanian Lek)
    - GBP (British Pound)
    """)

# Add a footer with some information
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center'>
        <p>This application uses Tesseract OCR to extract text from receipts.</p>
        <p>For best results, ensure your receipt images are clear and well-lit.</p>
    </div>
    """,
    unsafe_allow_html=True
)