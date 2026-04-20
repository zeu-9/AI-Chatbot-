import streamlit as st
import pandas as pd
import re
import os
from google import genai

client = genai.Client(api_key="AIzaSyA9r5dJJTz874RXXH-SymA3kbR-LwA23fI")
# Load data
df = pd.read_csv("cleaned_washingmachine.csv")

# --- FUNCTIONS ---
import time

def generate_ai_response(user_input, recommendations):

    prompt = f"""
    You are an AI assistant helping users choose washing machines.
    
    User request: {user_input}
    
    Here are some recommended products:
    {recommendations}
    
    Explain the recommendations in a friendly and helpful way.
    Highlight why these are good choices.
    """

    # Try primary model with retries
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            return response.text

        except Exception as e:
            print(f"Attempt {attempt+1} failed: {e}")
            time.sleep(5)  # wait before retry

    # Fallback model (safer)
    try:
        print("Switching to fallback model...")
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        return response.text

    except Exception as e:
        print("Fallback also failed:", e)

    # Final fallback (never crash your app)
    return "⚠️ AI is currently busy. Please try again in a few seconds."

def extract_details(text):
    text = text.lower()
    
    budget = None
    family = None
    machine_type = None
    
    # 💰 Budget
    min_price = None
    max_price = None

    # "between 10000 and 20000"
    match = re.search(r'between (\d+) and (\d+)', text)
    if match:
        min_price = int(match.group(1))
        max_price = int(match.group(2))

    # "under 10000"
    match = re.search(r'under\s*(\d+)', text)
    if match:
        budget = int(match.group(1))

    # "10k", "15k"
    match = re.search(r'(\d+)k', text)
    if match:
        budget = int(match.group(1)) * 1000

    # "cheap"
    if "cheap" in text or "budget" in text:
        budget = 15000
    
    # 👨‍👩‍👧‍👦 Family
    if "small family" in text:
        family = 2
    elif "medium family" in text:
        family = 4
    elif "large family" in text:
        family = 6
    else:
        # Case 1: "2 people", "3 persons"
        match = re.search(r'(\d+)\s*(people|persons|person|members)', text)
        if match:
            family = int(match.group(1))
        
        # Case 2: "family of 4"
        match = re.search(r'family of (\d+)', text)
        if match:
            family = int(match.group(1))
        
        # Case 3: "for 2"
        match = re.search(r'for\s*(\d+)',text)
        if match:
            family = int(match.group(1))
    
    # ⚙️ Type
    if "fully automatic" in text:
        machine_type = "Fully Automatic"
    elif "semi automatic" in text:
        machine_type = "Semi Automatic"
    
    best = False
    if "best" in text or "top" in text:
        best = True
    
    return budget, family, machine_type, min_price, max_price, best


def family_to_capacity(family):
    if family <= 2:
        return 6
    elif family <= 4:
        return 7
    else:
        return 8


def recommend(df, budget, capacity, machine_type=None, min_price=None, max_price=None, best=False):
    
    filtered = df.copy()
    
    # Price filter
    if min_price and max_price:
        filtered = filtered[
            (filtered['Price'] >= min_price) &
            (filtered['Price'] <= max_price)
        ]
    elif budget is not None:
        filtered = filtered[
            filtered['Price'] <= budget
        ]
    
    # Capacity filter
    filtered = filtered[
        filtered['Washing Capacity'] >= capacity
    ]
    
    # Type filter
    if machine_type:
        filtered = filtered[
            filtered['Function Type'].str.contains(machine_type, case=False)
        ]
    
    filtered = filtered.drop_duplicates(subset=['Model Name'])
    
    if filtered.empty:
        return pd.DataFrame()

    filtered['Capacity Score'] = 1 / (abs(filtered['Washing Capacity'] - capacity) + 1)
    
    filtered['Score'] = (
        filtered['Ratings'] * 0.6 +
        (1 / filtered['Price']) * 20000 +
        filtered['Capacity Score'] * 0.4
    )
    
    # 🔥 Step 4
    if best:
        filtered = filtered.sort_values(by='Ratings', ascending=False)
    else:
        filtered = filtered.sort_values(by='Score', ascending=False)
    
    top = filtered.head(4)
    remaining = filtered.iloc[4:]
    
    extra = remaining.sample(min(len(remaining), 4)) if len(remaining) > 0 else remaining
    
    result = pd.concat([top, extra])
    result = result.sample(frac=1)
    
    return result[['Product Name', 'Price', 'Ratings', 'Product_Url', 'Score']]


def chatbot_recommendation(df, text):
    budget, family, machine_type, min_price, max_price, best = extract_details(text)
    
    if family is None:
        return None, None
    
    capacity = family_to_capacity(family)
    
    recs = recommend(df, budget, capacity, machine_type, min_price, max_price, best)
    
    ai_response = generate_ai_response(text, recs.to_string())
    
    return recs, ai_response


# --- UI ---

st.title("🧺 AI Washing Machine Recommender")
st.markdown("### Tell me what you need 👇")


with st.form(key="input_form"):
    user_input = st.text_input("Describe what you want:")
    submit = st.form_submit_button("🔍 Get Recommendations")

if submit:
    recs, ai_text = chatbot_recommendation(df, user_input)
    
    if recs is None or recs.empty:
        st.warning("No matching products found 😔 Try changing your input")
    else:
        st.success("Here are some great options for you 👇")
        
        # 🤖 AI explanation
        st.markdown("### 🤖 AI Recommendation Summary")
        st.write(ai_text)
        
        st.markdown("---")
        
        # 📦 Product list
        for _, row in recs.iterrows():
            st.subheader(row['Product Name'])
            st.write(f"💰 Price: ₹{int(row['Price'])}")
            st.write(f"⭐ Rating: {row['Ratings']}")
            st.markdown(f"🔗 [View Product]({row['Product_Url']})")
            st.write("---")