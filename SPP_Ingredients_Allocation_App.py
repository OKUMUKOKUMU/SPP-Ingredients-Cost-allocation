import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# JSON key file contents as a dictionary

    
import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# Function to load data from Google Sheets
def load_data_from_google_sheet():
    # Define the scope
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    # Add credentials to the service account
    creds = Credentials.from_service_account_info(json_key, scopes=scope)

    # Authorize the client
    client = gspread.authorize(creds)

    # Get the instance of the Spreadsheet
    sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1dv3qKGiN3hemRiE0JFH4_ttVkeIKep3rJt4TA5R-tNU/edit?gid=1820651120#gid=1820651120")

    # Get the third sheet of the Spreadsheet
    worksheet = sheet.get_worksheet(2)  # 0-based index, so 2 represents the third sheet

    # Get all records of the data
    data = worksheet.get_all_records()
    
    # Convert data to DataFrame and rename columns correctly
    df = pd.DataFrame(data)
    df.columns = ["DATE", "ITEM_SERIAL", "ITEM NAME", "ISSUED_TO", "QUANTITY", "UNIT_OF_MEASURE",
                  "ITEM_CATEGORY", "WEEK", "REFERENCE", "DEPARTMENT_CAT", "BATCH NO.", "STORE", "RECEIVED BY"]
    df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")
    df["QUANTITY"] = pd.to_numeric(df["QUANTITY"], errors="coerce")
    df.dropna(subset=["QUANTITY"], inplace=True)
    df["QUARTER"] = df["DATE"].dt.to_period("Q")
    
    # Filter data to include from the year 2024 to the current date
    df = df[df["DATE"].dt.year >= 2024]

    return df

# Function to calculate department-wise usage proportion
def calculate_proportion(df, identifier):
    if identifier.isnumeric():
        filtered_df = df[df["ITEM_SERIAL"].astype(str).str.lower() == identifier.lower()]
    else:
        filtered_df = df[df["ITEM NAME"].str.lower() == identifier.lower()]

    if filtered_df.empty:
        return None

    usage_summary = filtered_df.groupby("DEPARTMENT_CAT")["QUANTITY"].sum()
    total_usage = usage_summary.sum()
    proportions = (usage_summary / total_usage) * 100
    proportions.sort_values(ascending=False, inplace=True)

    return proportions.reset_index()

# Function to allocate quantity based on historical proportions
def allocate_quantity(df, identifier, available_quantity):
    proportions = calculate_proportion(df, identifier)
    if proportions is None:
        return None
    
    proportions["Allocated Quantity"] = (proportions["QUANTITY"] / 100) * available_quantity
    
    # Adjust to make sure the sum matches the input quantity
    allocated_sum = proportions["Allocated Quantity"].sum()
    if allocated_sum != available_quantity:
        difference = available_quantity - allocated_sum
        index_max = proportions["Allocated Quantity"].idxmax()
        proportions.at[index_max, "Allocated Quantity"] += difference
    
    proportions["Allocated Quantity"] = proportions["Allocated Quantity"].round(0)

    return proportions

# Streamlit UI
st.markdown("""
    <style>
    .title {
        text-align: center;
        font-size: 46px;
        font-weight: bold;
        color: #FFC300; /* Cheese color */
        font-family: 'Amasis MT Pro', Arial, sans-serif;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown("<h1 class='title'> SPP Ingredients Allocation App </h1>", unsafe_allow_html=True)

data = load_data_from_google_sheet()

# Extract unique item names for auto-suggestions
unique_item_names = data["ITEM NAME"].unique().tolist()

# Auto-suggest input field for item name
identifier = st.selectbox("Enter Item Serial or Name:", unique_item_names)
available_quantity = st.number_input("Enter Available Quantity:", min_value=0.0, step=0.1)

if st.button("Calculate Allocation"):
    if identifier and available_quantity > 0:
        result = allocate_quantity(data, identifier, available_quantity)
        if result is not None:
            st.markdown("<div style='text-align: center;'><h3>Allocation Per Department</h3></div>", unsafe_allow_html=True)
            st.dataframe(result.rename(columns={"DEPARTMENT_CAT": "Department", "QUANTITY": "Proportion (%)"}), use_container_width=True)
        else:
            st.error("Item not found in historical data!")
    else:
        st.warning("Please enter a valid item serial/name and quantity.")

# Footnote
st.markdown("<p style='text-align: center; font-size: 14px;'> Developed by Brown's Data Team,©2025 </p>", unsafe_allow_html=True)

