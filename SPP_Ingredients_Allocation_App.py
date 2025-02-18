import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# JSON key file contents as a dictionary
json_key = {
  "type": "service_account",
  "project_id": "tracker-419810",
  "private_key_id": "1db0cd4dcda19da909eb0c1045284abb4b5c06b4",
  "private_key": """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDH21Yt6KRhdCBT
mV1b9IHlspRJ7CySyIAnDfrd4tCRIadsZpV96LwPLc0Z4pSkmtcAm9+a3JC5tqnC
b97oIADFZ4oJtWuemWf1TYHoqI6RqzwERc66viD0HB//9nvviiCDxXFB39W1v4FL
kjsVciqmglmyNYy+xmvkY4n5gwBNGyIps//yGSxFmczblxhCwc8Pfrh8qJhH/p6W
6rko4gWJblIhjOYiz5DS2d2XSNFiodPNPsgtzU3hmg3Lvi3w+WzeVJeiU7A/Xk/1
pB4hXJwHPi23p8hMpZWIBgZMKfe++Cg2rIiSNYt0PKcO7KkcuOdCAkDyGgEPBmzy
5nRnPj27AgMBAAECggEAQHTQdAj6bwXFYUDut7gBZuPz6G13qLVqg24CUSqUKqKI
fTEOmKeFc33JjsYhO39GxUcAVFE7ifHMCU4MPaAIr6Hnhp8QwPtn6Fjhg3hNVtS7
jAM5m8ezGBe0CFjl+sj5GJaGowC+S5oiaI2WaaHC+KXEqPGVXXfgFy41MxgZckQy
QyOvc9ikBkSWMOMo00XwCpzureOCrh2Dqeox84Lj8mpj2mQWu2YSPC4y39M3dMBf
nS0QYlRyTE80CK3gn9XjOwBhp2PUklva9i8EPQzSOkf22M1a/+lSQ/VJh5K0U7ni
76LKiG9UHIMC0K2tmBJ9Mz0huXhkYlscRC2bd1UzVQKBgQDx2+eUQe4t3aPqhlwH
cgW8M4+UwfJr9vWP9KaebJ9WxaV+DJK7DeuVgTsHn7Q57Qqj/ZJdrcI+DCAvcNvo
fftFlOOfM3jQ4pJQx4qdcSfeG6f206evisIDkNxlbv1yR5/YZ69Oc/JmAdXtxL9R
klCsBOQTMgqin+fslABb6IpQ/QKBgQDTisBkf9vuCcWpY82Pj0FfLLUs3R/2XPzB
GfGmNji+2HFrtirKF0LCtiYWSUkCy0b3Wgk1nx4yZdFcFRvxml++OxyaqqgsVh/J
vhiyvUMDICS1JXZBWkygFye4jmVxFTy5q8ibAN/zUwfFD2F2KYSpEkZMoL5iq5Aa
JN95kLYDFwKBgQC4tJpc7ST6viOqvcWWogujOTVUA/IhZc8Pi2Wb45Skbfj/FJcS
Z4Uc/j6YiezXuCHCL6sSA9suC5Cg6m3nVh8JerWDJYoE7KOVMW644mvyAej6ZZXQ
SAX3NzA5/tNr7Ssz16tYHNBn+srn9LOvljApzupnhnX80GYMlNLZXfQT+QKBgC0S
x2Oiiq3xjxhEl6wbDgbFc+UXSJQpxAExEfgkXXrsi14z9nIQ+ryaKwtcmh3qSjiy
CnxOZxS99Rn1tXqJNhVGaxXZfvPTdfp6crDC+uBTnP6r+MJ8Bw+lX2VHkf3CVKoL
HDdKvG0QJ/upB08yEX4k0q3JIkfL3mxzpto0J1QJAoGAOJJhiONVmx5oYYVA/I02
6KaJ95WvcdN9eUNoizHl1wGoJhd+FLEoDnU6ZSxxJ0z2ag2HBWjGfi07Y8xO2gMR
WLW42xnowTqey/aNml760mE7rCgQz1RJ7hCrUeV693EkDplxOcvU36YdObGfO7in
4Rx1mTv7WKclb+7boAfx1Z4=
-----END PRIVATE KEY-----""",
  "client_email": "spp-ing@tracker-419810.iam.gserviceaccount.com",
  "client_id": "101889874987074189201",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/spp-ing%40tracker-419810.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
    }
    
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

