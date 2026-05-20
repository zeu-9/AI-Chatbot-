import streamlit as st
import pandas as pd
import re
import requests
import os

# 🔑 ADD YOUR GROQ KEY
GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
# GROQ_API_KEY = None  # Set to None if you don't have a key or want to test Ollama only

df = pd.read_csv("cleaned_washingmachine.csv")

# -------------------------------
# 🤖 AI RESPONSE
# -------------------------------
def generate_ai_response(user_input, recs):

    recs_text = ""
    for i, (_, row) in enumerate(recs.iterrows(), 1):
        recs_text += f"{i}. {row['Product Name']} (₹{int(row['Price'])}, Rating: {row['Ratings']}/5, Type: {row['Function Type']})\n"

    prompt = f"""
    You are an expert home appliance consultant with deep knowledge of washing machines.
    A customer has come to you for personalized advice.

    Customer's Request: {user_input}

    Products shortlisted for this customer:
    {recs_text}

    Your job is to write a detailed, helpful buying guide for THIS customer based on THEIR specific request.
    Structure your response EXACTLY as follows, with a blank line between every section:

    🏆 BEST PICK FOR YOU:
    [One sentence recommending the best product and why it suits this customer.]

    ---

    📦 PRODUCT-BY-PRODUCT BREAKDOWN:

    For EACH product write it in this EXACT format with each point on a NEW LINE:

    🔹 [Product Name]
    ✅ Advantages:
    • [Advantage 1]
    • [Advantage 2]
    • [Advantage 3]
    ❌ Disadvantages:
    • [Disadvantage 1]
    • [Disadvantage 2]
    🎯 Best suited for: [Describe ideal customer in one line]

    [Repeat above block for every product with a blank line between each]

    ---

    💡 SITUATION GUIDE — WHEN TO CHOOSE WHAT:
    • If you have a large family with heavy daily laundry → [recommendation]
    • If you live in an apartment with low water pressure → [recommendation]
    • If energy bill is a concern → [recommendation]
    • If you hand wash delicates often → [recommendation]

    ---

    ⚠️ THINGS TO WATCH OUT FOR:
    • [Mistake 1]
    • [Mistake 2]
    • [Mistake 3]

    Rules:
    - Be specific to the products listed above, do not invent or suggest products not in the list
    - Use the customer's budget and family context from their request throughout your response
    - Speak directly to the customer using "you" and "your"
    - Keep the tone friendly, expert, and honest — like a trusted advisor, not a salesman
    - Every bullet point MUST be on its own new line
    - Every section MUST be separated by a blank line
    - Do not put multiple points on the same line
    - Total response should be 250-320 words
    """

    # 🟢 GROQ
    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            max_tokens=1024,        # ← fixed from 600
            temperature=0.7,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert home appliance consultant. You give honest, detailed, structured buying advice. You always consider the customer's specific situation — their family size, budget, and usage needs — before recommending anything."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        return response.choices[0].message.content

    except Exception as e:
        print("Groq failed:", e)

    # 🔵 OLLAMA
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.1",
                "prompt": prompt[:5000],
                "stream": False,
               "options": {
               "temperature": 0.5,
               "num_predict": 1024,
               "num_ctx": 8192       # ← ADD THIS — increases context window
               }
            },
            timeout=60
        )

        result = response.json()

        if 'response' in result:
            return result['response']
        else:
            print("Ollama returned unexpected format:", result)

    except Exception as e:
        print("Ollama failed:", e)

    return "⚠️ AI unavailable. Please check your Groq API key or ensure Ollama is running locally."

# -------------------------------
# 🧠 INPUT PROCESSING
# -------------------------------
def extract_details(text):
    text = text.lower()

    budget = None
    family = None
    machine_type = None
    load_type = None
    min_price = None
    max_price = None

    # 💰 Price
    match = re.search(r'between (\d+) and (\d+)', text)
    if match:
        min_price = int(match.group(1))
        max_price = int(match.group(2))

    match = re.search(r'under\s*(\d+)', text)
    if match:
        budget = int(match.group(1))

    match = re.search(r'(\d+)k', text)
    if match:
        budget = int(match.group(1)) * 1000

    if "cheap" in text or "budget" in text:
        budget = 15000

    # 👨‍👩‍👧‍👦 Family
    match = re.search(r'(\d+)\s*(people|members|persons)', text)
    if match:
        family = int(match.group(1))

    match = re.search(r'family of (\d+)', text)
    if match:
        family = int(match.group(1))

    if "small family" in text:
        family = 2
    elif "medium family" in text:
        family = 4
    elif "large family" in text:
        family = 6

    # ⚙️ Machine Type
    if "fully automatic" in text:
        machine_type = "Fully Automatic"
    elif "semi automatic" in text:
        machine_type = "Semi Automatic"

    # 🔄 Load Type Detection (improved - catches more variations)
    top_load_keywords = [
        "top load", "top-load", "topload",
        "top loading", "top-loading",
        "tl ", " tl", "top loader"
    ]
    front_load_keywords = [
        "front load", "front-load", "frontload",
        "front loading", "front-loading",
        "fl ", " fl", "front loader"
    ]

    for keyword in top_load_keywords:
        if keyword in text:
            load_type = "Top Load"
            break

    if load_type is None:
        for keyword in front_load_keywords:
            if keyword in text:
                load_type = "Front Load"
                break

    best = "best" in text or "top rated" in text or "top-rated" in text

    return budget, family, machine_type, min_price, max_price, best, load_type


def family_to_capacity(family):
    if family <= 2:
        return 6
    elif family <= 4:
        return 7
    else:
        return 8


# -------------------------------
# 🎯 RECOMMENDATION ENGINE
# -------------------------------
def recommend(df, budget, capacity, machine_type=None, min_price=None, max_price=None, best=False, load_type=None):

    filtered = df.copy()

    # Price
    if min_price and max_price:
        filtered = filtered[
            (filtered['Price'] >= min_price) &
            (filtered['Price'] <= max_price)
        ]
    elif budget:
        filtered = filtered[filtered['Price'] <= budget]

    # Capacity
    filtered = filtered[filtered['Washing Capacity'] >= capacity]

    # Machine Type
    if machine_type:
        filtered = filtered[
            filtered['Function Type'].str.contains(machine_type, case=False, na=False)
        ]

    # 🔄 Load Type Filter
    if load_type:
        filtered = filtered[
            filtered['Function Type'].str.contains(load_type, case=False, na=False)
        ]

        if filtered.empty:
            return pd.DataFrame()

    filtered = filtered.drop_duplicates(subset=['Model Name'])

    if filtered.empty:
        return pd.DataFrame()

    # Scoring
    filtered['Capacity Score'] = 1 / (abs(filtered['Washing Capacity'] - capacity) + 1)

    filtered['Score'] = (
        filtered['Ratings'] * 0.6 +
        (1 / filtered['Price']) * 20000 +
        filtered['Capacity Score'] * 0.4
    )

    if best:
        filtered = filtered.sort_values(by='Ratings', ascending=False)
    else:
        filtered = filtered.sort_values(by='Score', ascending=False)

    return filtered.head(6)[['Product Name', 'Price', 'Ratings', 'Product_Url', 'Function Type']]


def chatbot_recommendation(df, text):
    budget, family, machine_type, min_price, max_price, best, load_type = extract_details(text)

    if family is None:
        return None, None, None

    capacity = family_to_capacity(family)

    recs = recommend(df, budget, capacity, machine_type, min_price, max_price, best, load_type)

    ai_response = generate_ai_response(text, recs)

    # Build a summary of what filters were detected
    detected = []
    if load_type:
        detected.append(f"🔄 Load Type: **{load_type}**")
    if machine_type:
        detected.append(f"⚙️ Type: **{machine_type}**")
    if min_price and max_price:
        detected.append(f"💰 Budget: **₹{min_price:,} – ₹{max_price:,}**")
    elif budget:
        detected.append(f"💰 Budget: **under ₹{budget:,}**")
    if family:
        detected.append(f"👨‍👩‍👧‍👦 Family Size: **{family} people → {family_to_capacity(family)} kg+**")

    return recs, ai_response, detected


# -------------------------------
# 🎨 UI
# -------------------------------
st.set_page_config(page_title="AI Washing Machine Recommender", page_icon="🧺")

st.title("🧺 AI Washing Machine Recommender")
st.markdown("### Tell me what you need 👇")

st.info(
    "💡 **Try queries like:**\n"
    "- *Top load washing machine under 15000 for 3 people*\n"
    "- *Front load fully automatic for family of 4*\n"
    "- *Best semi automatic under 20k for large family*"
)

with st.form("form"):
    user_input = st.text_input("Describe what you want:")
    submit = st.form_submit_button("🔍 Get Recommendations")

if submit:

    if user_input.strip() == "":
        st.warning("Please enter something")

    else:
        with st.spinner("🤖 Finding best options..."):
            recs, ai_text, detected = chatbot_recommendation(df, user_input)

        # ✅ Show what the chatbot understood
        if detected:
            st.markdown("---")
            st.markdown("### 🔍 What I Understood From Your Query")
            cols = st.columns(len(detected))
            for i, item in enumerate(detected):
                cols[i].markdown(item)

        if recs is None or recs.empty:
            st.warning("No exact matching products found 😔 Try relaxing filters (e.g. remove load type or increase budget)")
        else:
            st.success(f"Found **{len(recs)}** matching products 👇")

    st.markdown("### 🤖 AI Recommendation Summary")
    with st.container():
        st.markdown(
            f"""
            <div style="
                background-color: #1a1a2e;
                border-left: 4px solid #e94560;
                border-radius: 10px;
                padding: 20px 25px;
                color: #e8eaf6;
                font-size: 15px;
                line-height: 1.8;
                white-space: pre-wrap;
            ">
    {ai_text}
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("---")
    st.markdown("### 📦 Recommended Products")

    for _, row in recs.iterrows():
        with st.container():
            st.subheader(row['Product Name'])

            # Show the machine type badge from dataset
            func_type = str(row.get('Function Type', ''))
            if func_type and func_type != 'nan':
                if "Top Load" in func_type:
                    st.markdown("🔼 `Top Load`", unsafe_allow_html=False)
                elif "Front Load" in func_type:
                    st.markdown("⬅️ `Front Load`", unsafe_allow_html=False)

                if "Fully Automatic" in func_type:
                    st.markdown("✅ `Fully Automatic`", unsafe_allow_html=False)
                elif "Semi Automatic" in func_type:
                    st.markdown("🔧 `Semi Automatic`", unsafe_allow_html=False)

            st.write(f"💰 Price: ₹{int(row['Price'])}")
            st.write(f"⭐ Rating: {row['Ratings']}")
            st.markdown(f"🔗 [View Product]({row['Product_Url']})")
            st.write("---")