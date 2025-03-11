import pandas as pd
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
import os
import time
import plotly.express as px
import numpy as np
from datetime import datetime

# Load environment variables
load_dotenv()

# Configure page
st.set_page_config(page_title="SPP Ingredients Allocation App", layout="wide")

# Add custom CSS
st.markdown("""
<style>
    .main-header {text-align: center; color: #FFC300; margin-bottom: 20px;}
    .sub-header {margin-top: 15px; margin-bottom: 10px;}
    .highlight {background-color: #f0f2f6; padding: 10px; border-radius: 5px;}
    .footer {text-align: center; color: #888; font-size: 0.8em;}
    .stAlert {margin-top: 20px;}
</style>
""", unsafe_allow_html=True)

# Function to validate Google credentials
def validate_google_credentials():
    required_env_vars = [
        "GOOGLE_PROJECT_ID", "GOOGLE_PRIVATE_KEY_ID", "GOOGLE_PRIVATE_KEY",
        "GOOGLE_CLIENT_EMAIL", "GOOGLE_CLIENT_ID", "GOOGLE_AUTH_URI", 
        "GOOGLE_TOKEN_URI", "GOOGLE_AUTH_PROVIDER_X509_CERT_URL", "GOOGLE_CLIENT_X509_CERT_URL"
    ]
    
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        st.error(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        st.info("Please set all required environment variables for Google Sheets access.")
        return False
    return True

# Cache function for Google Sheets connection with error handling
@st.cache_data(ttl=3600)
def load_data_from_google_sheet():
    if not validate_google_credentials():
        return pd.DataFrame()
        
    try:
        scope = ["https://spreadsheets.google.com/feeds", 
                'https://www.googleapis.com/auth/spreadsheets',
                "https://www.googleapis.com/auth/drive.file", 
                "https://www.googleapis.com/auth/drive"]
        
        credentials = {
            "type": "service_account",
            "project_id": os.getenv("GOOGLE_PROJECT_ID"),
            "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
            "private_key": os.getenv("GOOGLE_PRIVATE_KEY").replace("\\n", "\n"),
            "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
            "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
            "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_X509_CERT_URL"),
            "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_X509_CERT_URL")
        }

        client_credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials, scope)
        client = gspread.authorize(client_credentials)
        
        try:
            worksheet = client.open("BROWNS STOCK MANAGEMENT").worksheet("CHECK_OUT")
        except gspread.exceptions.SpreadsheetNotFound:
            st.error("❌ Spreadsheet 'BROWNS STOCK MANAGEMENT' not found!")
            return pd.DataFrame()
        except gspread.exceptions.WorksheetNotFound:
            st.error("❌ Worksheet 'CHECK_OUT' not found!")
            return pd.DataFrame()
        
        data = worksheet.get_all_records()
        if not data:
            st.warning("⚠️ No data found in the spreadsheet!")
            return pd.DataFrame()
            
        df = pd.DataFrame(data)

        # Standardize column names and handle potential missing columns
        expected_columns = ["DATE", "ITEM_SERIAL", "ITEM NAME", "ISSUED_TO", "QUANTITY", 
                          "UNIT_OF_MEASURE", "ITEM_CATEGORY", "WEEK", "REFERENCE", 
                          "DEPARTMENT_CAT", "BATCH NO.", "STORE", "RECEIVED BY"]
        
        # Check if all expected columns are present
        missing_columns = [col for col in expected_columns if col not in df.columns]
        if missing_columns:
            st.warning(f"⚠️ Missing columns in spreadsheet: {', '.join(missing_columns)}")
            # Add missing columns with NaN values
            for col in missing_columns:
                df[col] = np.nan
        
        # Ensure column order matches expected order
        df = df[expected_columns]
        
        # Data cleaning and transformation
        df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")
        df["QUANTITY"] = pd.to_numeric(df["QUANTITY"], errors="coerce")
        
        # Drop rows with missing quantities
        df.dropna(subset=["QUANTITY"], inplace=True)
        
        # Fill missing department categories
        if df["DEPARTMENT_CAT"].isna().any():
            df["DEPARTMENT_CAT"].fillna("Unspecified", inplace=True)
            
        # Add quarter and year columns for potential filtering
        df["QUARTER"] = df["DATE"].dt.to_period("Q")
        df["YEAR"] = df["DATE"].dt.year
        
        # Filter for recent data (current year)
        current_year = datetime.now().year
        recent_data = df[df["YEAR"] >= current_year - 1]
        
        if recent_data.empty:
            st.warning(f"⚠️ No data found for {current_year} or {current_year-1}. Showing all available data instead.")
            return df
        
        return recent_data
        
    except Exception as e:
        st.error(f"❌ Error loading data: {str(e)}")
        return pd.DataFrame()

@st.cache_data
def calculate_proportion(df, identifier):
    """Calculate proportional usage by department for a specific item"""
    if df.empty:
        return None
        
    identifier = str(identifier).lower()
    # Improved search logic to handle partial matches
    filtered_df = df[(df["ITEM_SERIAL"].astype(str).str.lower() == identifier) |
                     (df["ITEM NAME"].str.lower() == identifier) |
                     (df["ITEM NAME"].str.lower().str.contains(identifier))]

    if filtered_df.empty:
        return None

    # Group by department and calculate total quantity
    usage_summary = filtered_df.groupby("DEPARTMENT_CAT")["QUANTITY"].sum()
    
    # Calculate proportions
    total_usage = usage_summary.sum()
    if total_usage == 0:
        return None
        
    proportions = (usage_summary / total_usage) * 100
    proportions.sort_values(ascending=False, inplace=True)

    result = proportions.reset_index()
    # Ensure no null values
    result = result.fillna(0)
    
    return result

def allocate_quantity(df, item_quantities, min_threshold=5):
    """Allocate quantities to departments based on historical usage patterns"""
    if df.empty:
        st.error("❌ No data available for allocation!")
        return {}
        
    allocations = {}
    
    for item, quantity in item_quantities.items():
        if quantity <= 0:
            continue
            
        proportions = calculate_proportion(df, item)
        if proportions is None:
            st.warning(f"⚠️ No usage data found for '{item}'.")
            continue

        # Create a copy to avoid modifying the original dataframe
        allocation_df = proportions.copy()
        allocation_df["Allocated Quantity"] = np.round((allocation_df["QUANTITY"] / 100) * quantity, 1)
        
        # Handle minimum threshold allocation
        total_allocated = allocation_df["Allocated Quantity"].sum()
        if total_allocated > 0:
            # Identify departments that would receive less than the minimum threshold
            min_quantity = (quantity * min_threshold / 100)
            underallocated = allocation_df[allocation_df["Allocated Quantity"] < min_quantity].copy()
            
            if not underallocated.empty and len(allocation_df) > len(underallocated):
                # Calculate how much quantity needs to be reallocated
                needed_reallocation = sum(min_quantity - row["Allocated Quantity"] 
                                         for _, row in underallocated.iterrows())
                
                # Set underallocated departments to minimum threshold
                for idx in underallocated.index:
                    allocation_df.loc[idx, "Allocated Quantity"] = min_quantity
                
                # Calculate how much to reduce from other departments
                overallocated = allocation_df[~allocation_df.index.isin(underallocated.index)]
                if not overallocated.empty:
                    total_over = overallocated["Allocated Quantity"].sum()
                    reduction_factor = needed_reallocation / total_over
                    
                    # Reduce allocation proportionally from other departments
                    for idx in overallocated.index:
                        current = allocation_df.loc[idx, "Allocated Quantity"]
                        allocation_df.loc[idx, "Allocated Quantity"] = max(0, current - (current * reduction_factor))
                        
            # Special case: if all departments would be under minimum threshold
            elif len(underallocated) == len(allocation_df) and len(allocation_df) > 1:
                # Distribute equally
                equal_share = quantity / len(allocation_df)
                allocation_df["Allocated Quantity"] = equal_share
        
        # Round allocated quantities to 1 decimal place for readability
        allocation_df["Allocated Quantity"] = np.round(allocation_df["Allocated Quantity"], 1)
        
        # Check if allocation sum matches original quantity (adjust for rounding errors)
        total_after_allocation = allocation_df["Allocated Quantity"].sum()
        if abs(total_after_allocation - quantity) > 0.5:
            # Adjust the largest allocation to compensate for rounding differences
            idx_max = allocation_df["Allocated Quantity"].idxmax()
            adjustment = quantity - total_after_allocation
            allocation_df.loc[idx_max, "Allocated Quantity"] += adjustment
            allocation_df.loc[idx_max, "Allocated Quantity"] = np.round(allocation_df.loc[idx_max, "Allocated Quantity"], 1)
        
        # Rename columns for better UI display
        allocation_df.rename(columns={"DEPARTMENT_CAT": "Department", "QUANTITY": "Proportion (%)"}, inplace=True)
        allocation_df["Proportion (%)"] = np.round(allocation_df["Proportion (%)"], 1)
        
        # Add to allocations dictionary
        allocations[item] = allocation_df

    return allocations

# Sidebar UI
st.sidebar.markdown("""
    <h1 class='main-header'>SPP Ingredients Allocation App</h1>
""", unsafe_allow_html=True)

# Loading data indicator in the main area instead of sidebar
with st.spinner("Loading data..."):
    data = load_data_from_google_sheet()

if data.empty:
    st.error("❌ Unable to load data. Please check your connection and credentials.")
else:
    # Show data statistics in the sidebar
    st.sidebar.success(f"✅ Loaded {len(data):,} records")
    unique_items_count = data["ITEM NAME"].nunique()
    st.sidebar.info(f"📊 {unique_items_count} unique items available")
    
    # Date range information
    if not data["DATE"].empty:
        min_date = data["DATE"].min().strftime("%b %Y")
        max_date = data["DATE"].max().strftime("%b %Y")
        st.sidebar.info(f"📅 Data range: {min_date} to {max_date}")

    # Filtering options
    st.sidebar.header("🔍 Item Selection")
    
    # Option to filter by category first
    categories = sorted(data["ITEM_CATEGORY"].dropna().unique().tolist())
    if categories:
        selected_category = st.sidebar.selectbox("Filter by Category (Optional):", 
                                               ["All Categories"] + categories)
        
        if selected_category != "All Categories":
            filtered_data = data[data["ITEM_CATEGORY"] == selected_category]
        else:
            filtered_data = data
    else:
        filtered_data = data
    
    # Get unique item names with sorting for better UX
    unique_item_names = sorted(filtered_data["ITEM NAME"].dropna().unique().tolist())
    
    # Search functionality for better user experience
    search_term = st.sidebar.text_input("Search for items:", "")
    if search_term:
        matching_items = [item for item in unique_item_names 
                         if search_term.lower() in item.lower()]
        if not matching_items:
            st.sidebar.warning(f"No items found matching '{search_term}'")
    else:
        matching_items = unique_item_names
    
    # Select items with limited selections for performance
    max_selections = 10
    selected_identifiers = st.sidebar.multiselect(
        f"Select Items (max {max_selections}):", 
        matching_items, 
        max_selections=max_selections
    )

    # Enter quantities with validation
    if selected_identifiers:
        st.sidebar.subheader("📌 Enter Available Quantities")
        
        # Add option to set same quantity for all
        use_same_qty = st.sidebar.checkbox("Use same quantity for all items")
        
        item_quantities = {}
        if use_same_qty:
            default_qty = st.sidebar.number_input(
                "Quantity for all items:", 
                min_value=0.0, 
                max_value=10000.0,
                step=0.1
            )
            for item in selected_identifiers:
                item_quantities[item] = default_qty
        else:
            for item in selected_identifiers:
                item_quantities[item] = st.sidebar.number_input(
                    f"{item}:", 
                    min_value=0.0, 
                    max_value=10000.0,
                    step=0.1, 
                    key=item
                )
        
        # Option to adjust minimum allocation threshold
        st.sidebar.subheader("⚙️ Advanced Settings")
        min_threshold = st.sidebar.slider(
            "Minimum allocation threshold (%):", 
            min_value=0, 
            max_value=20, 
            value=5,
            help="Departments allocated less than this percentage will be adjusted"
        )
        
        # Calculate button with loading indicator
        if st.sidebar.button("🚀 Calculate Allocation", type="primary"):
            if all(qty == 0 for qty in item_quantities.values()):
                st.sidebar.error("Please enter at least one non-zero quantity")
            else:
                # Use the spinner in the main area instead of sidebar
                with st.spinner("Calculating allocation..."):
                    time.sleep(0.5)  # Brief pause for UX
                    result = allocate_quantity(filtered_data, item_quantities, min_threshold)
                    
                    if result:
                        # Main area results display
                        st.markdown("<h2 class='main-header'>📊 Allocation Results</h2>", unsafe_allow_html=True)
                        
                        # Summary card
                        summary_cols = st.columns([1, 1])
                        with summary_cols[0]:
                            st.info(f"📋 Items processed: {len(result)}")
                        with summary_cols[1]:
                            total_qty = sum(sum(table["Allocated Quantity"]) for table in result.values())
                            st.info(f"📦 Total quantity allocated: {total_qty:,.1f}")
                        
                        # Use tabs for better organization when multiple items
                        if len(result) > 1:
                            tabs = st.tabs([f"{item}" for item in result.keys()])
                            for i, (item, table) in enumerate(result.items()):
                                with tabs[i]:
                                    # Display allocation table
                                    st.markdown(f"#### Allocation Table for {item}")
                                    st.dataframe(
                                        table,
                                        use_container_width=True
                                    )
                                    
                                    # Show visualization
                                    display_cols = st.columns([2, 1])
                                    with display_cols[0]:
                                        fig_pie = px.pie(
                                            table, 
                                            names="Department", 
                                            values="Allocated Quantity",
                                            title=f"Quantity Allocation for {item}",
                                            color_discrete_sequence=px.colors.qualitative.Set3
                                        )
                                        fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                                        st.plotly_chart(fig_pie, use_container_width=True)
                                    
                                    with display_cols[1]:
                                        # Show bar chart of proportions
                                        fig_bar = px.bar(
                                            table, 
                                            x="Department", 
                                            y="Proportion (%)",
                                            title="Historical Usage Pattern",
                                            color="Proportion (%)",
                                            color_continuous_scale="Blues",
                                        )
                                        fig_bar.update_layout(xaxis_tickangle=-45)
                                        st.plotly_chart(fig_bar, use_container_width=True)
                        else:
                            # Simpler layout for single item
                            for item, table in result.items():
                                st.markdown(f"#### 🔹 Allocation for {item}")
                                st.dataframe(
                                    table,
                                    use_container_width=True
                                )
                                
                                # Create columns for charts
                                col1, col2 = st.columns([1, 1])
                                with col1:
                                    fig = px.pie(
                                        table, 
                                        names="Department", 
                                        values="Allocated Quantity",
                                        title=f"Quantity Allocation",
                                        color_discrete_sequence=px.colors.qualitative.Set3
                                    )
                                    fig.update_traces(textposition='inside', textinfo='percent+label')
                                    st.plotly_chart(fig, use_container_width=True)
                                
                                with col2:
                                    fig_bar = px.bar(
                                        table, 
                                        x="Department", 
                                        y="Proportion (%)",
                                        title="Historical Usage Pattern",
                                        color="Proportion (%)",
                                        color_continuous_scale="Blues"
                                    )
                                    fig_bar.update_layout(xaxis_tickangle=-45)
                                    st.plotly_chart(fig_bar, use_container_width=True)
                                
                        # Option to download results
                        st.markdown("### 📥 Download Results")
                        for item, table in result.items():
                            csv = table.to_csv(index=False)
                            filename = f"{item.replace(' ', '_')}_allocation.csv"
                            st.download_button(
                                f"Download {item} allocation",
                                csv,
                                filename,
                                "text/csv",
                                key=f"download_{item}"
                            )
                    else:
                        st.error("❌ No matching data found for the selected items!")

    # Footer
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "<p class='footer'>Developed by Brown's Data Team<br>©2025 | v2.0</p>", 
        unsafe_allow_html=True
    )
    
    # Help section
    with st.sidebar.expander("ℹ️ Help & Information"):
        st.markdown("""
        **How to use this app:**
        1. Select items from the dropdown menu
        2. Enter the available quantities for each item
        3. Click 'Calculate Allocation' to see results
        
        **Understanding Results:**
        - The app analyzes historical usage patterns to suggest optimal allocations
        - Departments that would receive very small amounts are handled based on the minimum threshold setting
        - Visualizations help you understand both historical patterns and proposed allocations
        
        **Need more help?** Contact data-team@browns.com
        """)
