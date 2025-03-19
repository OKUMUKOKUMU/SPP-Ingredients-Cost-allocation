import pandas as pd
import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
import os
from datetime import datetime
import plotly.express as px

# Load environment variables
load_dotenv()

def connect_to_gsheet(spreadsheet_name, sheet_name):
    """
    Authenticate and connect to Google Sheets.
    """
    scope = ["https://spreadsheets.google.com/feeds", 
             "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file", 
             "https://www.googleapis.com/auth/drive"]
    
    try:
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
        spreadsheet = client.open(spreadsheet_name)  
        return spreadsheet.worksheet(sheet_name)  # Access specific sheet by name
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets: {e}")
        return None

def load_data_from_google_sheet():
    """
    Load data from Google Sheets.
    """
    with st.spinner("Loading data from Google Sheets..."):
        try:
            worksheet = connect_to_gsheet(SPREADSHEET_NAME, SHEET_NAME)
            if worksheet is None:
                return None
            
            # Get all records from the Google Sheet
            data = worksheet.get_all_records()
            
            if not data:
                st.error("No data found in the Google Sheet.")
                return None

            # Convert data to DataFrame
            df = pd.DataFrame(data)

            # Ensure columns match the updated Google Sheets structure
            df.columns = ["DATE", "ITEM_SERIAL", "ITEM NAME", "DEPARTMENT", "ISSUED_TO", "QUANTITY", 
                        "UNIT_OF_MEASURE", "ITEM_CATEGORY", "WEEK", "REFERENCE", 
                        "DEPARTMENT_CAT", "BATCH NO.", "STORE", "RECEIVED BY"]

            # Convert date and numeric columns
            df["DATE"] = pd.to_datetime(df["DATE"], errors="coerce")
            df["QUANTITY"] = pd.to_numeric(df["QUANTITY"], errors="coerce")
            df.dropna(subset=["QUANTITY"], inplace=True)
            
            # Extract quarter information
            df["QUARTER"] = df["DATE"].dt.to_period("Q")

            # Filter data for 2024 onwards
            current_year = datetime.now().year
            df = df[df["DATE"].dt.year >= current_year - 1]  # Data from last year onwards

            return df
        except Exception as e:
            st.error(f"Error loading data: {e}")
            return None

@st.cache_data(ttl=3600)  # Cache data for 1 hour
def get_cached_data():
    return load_data_from_google_sheet()

def calculate_proportion(df, identifier, department=None, min_proportion=1.0):
    """
    Calculate department-wise usage proportion without subdepartment details.
    Ensures all departments sum to 100%.
    Filters out departments with proportions less than min_proportion.
    """
    if df is None:
        return None
    
    try:
        if identifier.isnumeric():
            filtered_df = df[df["ITEM_SERIAL"].astype(str).str.lower() == identifier.lower()]
        else:
            filtered_df = df[df["ITEM NAME"].str.lower() == identifier.lower()]

        if filtered_df.empty:
            return None

        # If department is specified, filter by department
        if department and department != "All Departments":
            filtered_df = filtered_df[filtered_df["DEPARTMENT"] == department]
            if filtered_df.empty:
                return None

        # Calculate department-level proportions only
        dept_usage = filtered_df.groupby("DEPARTMENT")["QUANTITY"].sum().reset_index()
        
        # Calculate total across all departments
        total_usage = dept_usage["QUANTITY"].sum()
        
        if total_usage == 0:
            return None
            
        # Calculate each department's proportion of the total
        dept_usage["PROPORTION"] = (dept_usage["QUANTITY"] / total_usage) * 100
        
        # Filter out departments with proportions less than min_proportion
        significant_depts = dept_usage[dept_usage["PROPORTION"] >= min_proportion].copy()
        
        # If no departments meet the threshold, return the one with the highest proportion
        if significant_depts.empty and not dept_usage.empty:
            significant_depts = pd.DataFrame([dept_usage.iloc[dept_usage["PROPORTION"].idxmax()]])
        
        # Recalculate proportions to ensure they sum to 100%
        total_proportion = significant_depts["PROPORTION"].sum()
        significant_depts["PROPORTION"] = (significant_depts["PROPORTION"] / total_proportion) * 100
        
        # Calculate relative weights for sorting
        significant_depts["QUANTITY_ABS"] = significant_depts["QUANTITY"].abs()
        significant_depts["INTERNAL_WEIGHT"] = significant_depts["QUANTITY_ABS"] / significant_depts["QUANTITY_ABS"].sum()
        
        # Sort by proportion (descending)
        significant_depts.sort_values(by=["PROPORTION"], ascending=[False], inplace=True)
        
        return significant_depts
    except Exception as e:
        st.error(f"Error calculating proportions: {e}")
        return None

def allocate_quantity(df, identifier, available_quantity, department=None):
    """
    Allocate quantity based on historical proportions at department level only.
    Filters out departments with less than 1% proportion.
    Ensures total allocation exactly matches available quantity.
    """
    proportions = calculate_proportion(df, identifier, department, min_proportion=1.0)
    if proportions is None:
        return None
    
    # Calculate allocated quantity for each department based on their proportion
    proportions["ALLOCATED_QUANTITY"] = (proportions["PROPORTION"] / 100) * available_quantity
    
    # First calculate the sum of the non-rounded values
    total_unrounded = proportions["ALLOCATED_QUANTITY"].sum()
    
    # Round allocated quantities to integers
    proportions["ALLOCATED_QUANTITY"] = proportions["ALLOCATED_QUANTITY"].round(0).astype(int)
    
    # Get the total after rounding
    allocated_sum = proportions["ALLOCATED_QUANTITY"].sum()
    
    # Adjust to ensure we match exactly the available quantity
    if allocated_sum != available_quantity:
        difference = int(available_quantity - allocated_sum)
        
        if difference > 0:
            # Need to add some units - add to departments with largest fractional parts
            # Sort by fractional part (descending)
            fractional_parts = (proportions["PROPORTION"] / 100) * available_quantity - proportions["ALLOCATED_QUANTITY"]
            indices = fractional_parts.sort_values(ascending=False).index[:difference].tolist()
            for idx in indices:
                proportions.at[idx, "ALLOCATED_QUANTITY"] += 1
        elif difference < 0:
            # Need to subtract some units - remove from departments with smallest fractional parts
            # Sort by fractional part (ascending)
            fractional_parts = (proportions["PROPORTION"] / 100) * available_quantity - (proportions["ALLOCATED_QUANTITY"] - 1)
            indices = fractional_parts.sort_values(ascending=True).index[:-difference].tolist()
            for idx in indices:
                proportions.at[idx, "ALLOCATED_QUANTITY"] -= 1
    
    # Verify once more that the sum matches the available quantity exactly
    final_sum = proportions["ALLOCATED_QUANTITY"].sum()
    assert final_sum == available_quantity, f"Allocation error: {final_sum} != {available_quantity}"
    
    return proportions

def generate_allocation_chart(result_df, item_name):
    """
    Generate a bar chart for allocation results.
    """
    # Create a summarized version for charting (by DEPARTMENT only)
    chart_df = result_df.copy()
    
    # Create a bar chart
    fig = px.bar(
        chart_df, 
        x="DEPARTMENT", 
        y="ALLOCATED_QUANTITY",
        text="ALLOCATED_QUANTITY",
        title=f"Allocation for {item_name} by Department",
        labels={
            "DEPARTMENT": "Department",
            "ALLOCATED_QUANTITY": "Allocated Quantity"
        },
        height=400,
        color="DEPARTMENT",
        color_discrete_sequence=px.colors.qualitative.Bold
    )
    
    # Customize the layout
    fig.update_layout(
        title_font=dict(size=20, family="Arial", color="#333333"),
        title_x=0.5,
        legend_title_text='',
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            title=dict(font=dict(size=14, family="Arial", color="#555555")),
            tickfont=dict(size=12, family="Arial", color="#555555"),
            gridcolor="rgba(220,220,220,0.5)"
        ),
        yaxis=dict(
            title=dict(font=dict(size=14, family="Arial", color="#555555")),
            tickfont=dict(size=12, family="Arial", color="#555555"),
            gridcolor="rgba(220,220,220,0.5)"
        )
    )
    
    # Improve bar appearance
    fig.update_traces(
        textposition='outside',
        textfont=dict(size=12, family="Arial", color="#333333"),
        marker_line_width=1,
        marker_line_color="rgba(0,0,0,0.2)",
        opacity=0.85
    )
    
    return fig

# Streamlit UI
st.set_page_config(
    page_title="SPP Ingredients Allocation App", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Enhanced CSS with modern design elements
st.markdown("""
    <style>
    /* Global styles */
    * {
        font-family: 'Segoe UI', 'Roboto', 'Helvetica Neue', sans-serif;
    }
    
    /* App header */
    .title {
        text-align: center;
        font-size: 36px;
        font-weight: 600;
        color: #1E3A8A;
        margin-bottom: 10px;
        padding-top: 20px;
        background: linear-gradient(90deg, #1E3A8A 0%, #3B82F6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    .subtitle {
        text-align: center;
        font-size: 18px;
        color: #64748B;
        margin-bottom: 30px;
        font-weight: 400;
    }
    
    /* Cards */
    .card {
        background-color: #FFFFFF;
        border-radius: 12px;
        padding: 24px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
        margin-bottom: 24px;
        border: 1px solid #F1F5F9;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    
    .card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12);
    }
    
    /* Headers */
    .header {
        color: #1E3A8A;
        font-size: 24px;
        font-weight: 600;
        margin-bottom: 16px;
        border-bottom: 2px solid #F1F5F9;
        padding-bottom: 8px;
    }
    
    .subheader {
        color: #334155;
        font-size: 18px;
        font-weight: 500;
        margin: 16px 0 12px 0;
    }
    
    /* Result styles */
    .result-header {
        background-color: #F1F5F9;
        padding: 12px 16px;
        border-radius: 8px;
        margin-bottom: 16px;
        display: flex;
        align-items: center;
        border-left: 5px solid #3B82F6;
    }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(90deg, #3B82F6 0%, #2563EB 100%);
        color: white;
        font-weight: 500;
        border-radius: 8px;
        padding: 8px 16px;
        border: none;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        background: linear-gradient(90deg, #2563EB 0%, #1D4ED8 100%);
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
        transform: translateY(-2px);
    }
    
    /* Sidebar */
    .sidebar .sidebar-content {
        background: linear-gradient(180deg, #1E3A8A 0%, #0F172A 100%);
        color: white;
    }
    
    /* Metrics */
    .metric-card {
        background-color: #F8FAFC;
        border-radius: 8px;
        padding: 12px;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.05);
        border: 1px solid #E2E8F0;
        text-align: center;
    }
    
    .metric-value {
        font-size: 24px;
        font-weight: 600;
        color: #1E3A8A;
    }
    
    .metric-label {
        font-size: 14px;
        color: #64748B;
        margin-top: 4px;
    }
    
    /* Tables */
    .dataframe {
        border-radius: 8px !important;
        overflow: hidden !important;
    }
    
    /* Form elements */
    .stSelectbox > div > div {
        border-radius: 6px !important;
    }
    
    .stNumberInput > div > div > input {
        border-radius: 6px !important;
    }
    
    /* Footer */
    .footer {
        text-align: center;
        font-size: 14px;
        color: #94A3B8;
        margin-top: 40px;
        padding-top: 20px;
        border-top: 1px solid #E2E8F0;
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0px 0px;
        padding: 10px 16px;
        background-color: #F1F5F9;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #3B82F6 !important;
        color: white !important;
    }
    
    /* Alerts */
    .stAlert {
        border-radius: 8px !important;
    }
    
    /* Loading spinner */
    .stSpinner > div {
        border-color: #3B82F6 !important;
    }
    </style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("<h2 class='title'>SPP Ingredients</h2>", unsafe_allow_html=True)
    st.markdown("<p class='subtitle'>Smart Allocation System</p>", unsafe_allow_html=True)
    
    # Google Sheet credentials and details
    SPREADSHEET_NAME = 'BROWNS STOCK MANAGEMENT'
    SHEET_NAME = 'CHECK_OUT'
    
    # Load the data
    if "data" not in st.session_state:
        st.session_state.data = get_cached_data()
    
    data = st.session_state.data
    
    if data is None:
        st.error("Failed to load data from Google Sheets. Please check your connection and credentials.")
        st.stop()
    
    # Extract unique item names and departments for auto-suggestions
    unique_item_names = sorted(data["ITEM NAME"].unique().tolist())
    unique_departments = sorted(["All Departments"] + data["DEPARTMENT"].unique().tolist())
    
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='subheader'>Quick Stats</div>", unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            f"<div class='metric-card'>"
            f"<div class='metric-value'>{len(unique_item_names)}</div>"
            f"<div class='metric-label'>Total Items</div>"
            f"</div>",
            unsafe_allow_html=True
        )
    with col2:
        st.markdown(
            f"<div class='metric-card'>"
            f"<div class='metric-value'>{len(unique_departments) - 1}</div>"  # Exclude "All Departments"
            f"<div class='metric-label'>Departments</div>"
            f"</div>",
            unsafe_allow_html=True
        )
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Refresh data button
    if st.button("↻ Refresh Data"):
        st.session_state.data = load_data_from_google_sheet()
        st.success("✅ Data refreshed successfully!")
    
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='subheader'>Navigation</div>", unsafe_allow_html=True)
    view_mode = st.radio("", ["Allocation Calculator", "Data Overview"])
    st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("<p class='footer'>Developed by Brown's Data Team<br>©2025</p>", unsafe_allow_html=True)

# Main content
st.markdown("<h1 class='title'>SPP Ingredients Allocation App</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>Efficiently allocate ingredients across departments based on historical usage patterns</p>", unsafe_allow_html=True)

# Use tabs for a cleaner interface
if view_mode == "Allocation Calculator":
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='header'>Allocation Calculator</div>", unsafe_allow_html=True)
    
    # Use tabs for allocation form
    tab1, tab2 = st.tabs(["⚖️ Calculate Allocation", "📊 Recent Allocations"])
    
    with tab1:
        with st.form("allocation_form"):
            st.markdown("<div class='subheader'>Item Selection</div>", unsafe_allow_html=True)
            
            # Improved layout for department selection
            selected_department = st.selectbox(
                "Filter by Department (optional)",
                unique_departments,
                help="Select a department to filter allocation or use 'All Departments'"
            )
            
            # Item selection with better visual separation
            num_items = st.slider("Number of items to allocate", min_value=1, max_value=10, value=1)
            
            entries = []
            for i in range(num_items):
                st.markdown(f"<div class='subheader'>Item {i+1} Details</div>", unsafe_allow_html=True)
                col1, col2 = st.columns([2, 1])
                with col1:
                    identifier = st.selectbox(
                        "Select item", 
                        unique_item_names, 
                        key=f"item_{i}",
                        help="Choose an item from the inventory"
                    )
                with col2:
                    available_quantity = st.number_input(
                        "Quantity:", 
                        min_value=0.1, 
                        step=0.1, 
                        key=f"qty_{i}",
                        help="Enter the quantity available for allocation"
                    )

                if identifier and available_quantity > 0:
                    entries.append((identifier, available_quantity))

            # Make the submit button more noticeable
            submitted = st.form_submit_button("▶ Calculate Allocation")
    
    with tab2:
        st.info("Recent allocations will appear here")
        # This section could be enhanced to show recent allocations from a history
    
    st.markdown("</div>", unsafe_allow_html=True)

    # Processing Allocation with improved visualization
    if submitted:
        if not entries:
            st.warning("⚠️ Please enter at least one valid item and quantity!")
        else:
            for identifier, available_quantity in entries:
                result = allocate_quantity(data, identifier, available_quantity, selected_department)
                if result is not None:
                    st.markdown("<div class='card'>", unsafe_allow_html=True)
                    
                    # Enhanced header with icon and styling
                    st.markdown(
                        f"<div class='result-header'>"
                        f"<span style='font-size:24px;margin-right:10px;'>📊</span>"
                        f"<h3 style='margin:0;color:#1E3A8A;font-size:20px;'>Allocation Results: {identifier}</h3>"
                        f"</div>", 
                        unsafe_allow_html=True
                    )
                    
                    # Split the view with tabs for better organization
                    result_tab1, result_tab2 = st.tabs(["📋 Allocation Table", "📈 Visualization"])
                    
                    with result_tab1:
                        # Format the output for better readability
                        formatted_result = result[["DEPARTMENT", "PROPORTION", "ALLOCATED_QUANTITY"]].copy()
                        formatted_result = formatted_result.rename(columns={
                            "DEPARTMENT": "Department",
                            "PROPORTION": "Proportion (%)",
                            "ALLOCATED_QUANTITY": "Allocated Quantity"
                        })
                        
                        # Format numeric columns
                        formatted_result["Proportion (%)"] = formatted_result["Proportion (%)"].round(2)
                        formatted_result["Allocated Quantity"] = formatted_result["Allocated Quantity"].astype(int)
                        
                        # Display the result with enhanced styling
                        st.dataframe(
                            formatted_result,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Department": st.column_config.TextColumn("Department", help="Department receiving allocation"),
                                "Proportion (%)": st.column_config.NumberColumn("Proportion (%)", format="%.2f%%", help="Historical usage proportion"),
                                "Allocated Quantity": st.column_config.NumberColumn("Allocated Quantity", format="%d", help="Allocated quantity based on proportion")
                            }
                        )
                        
                        # Summary statistics with cleaner presentation
                        st.markdown("<div class='subheader'>Allocation Summary</div>", unsafe_allow_html=True)
                        summary_cols = st.columns(3)
                        with summary_cols[0]:
                            st.markdown(
                                f"<div class='metric-card'>"
                                f"<div class='metric-value'>{formatted_result['Allocated Quantity'].sum():,.0f}</div>"
                                f"<div class='metric-label'>Total Quantity</div>"
                                f"</div>",
                                unsafe_allow_html=True
                            )
                        with summary_cols[1]:
                            st.markdown(
                                f"<div class='metric-card'>"
                                f"<div class='metric-value'>{formatted_result['Department'].nunique()}</div>"
                                f"<div class='metric-label'>Departments</div>"
                                f"</div>",
                                unsafe_allow_html=True
                            )
                        with summary_cols[2]:
                            st.markdown(
                                f"<div class='metric-card'>"
                                f"<div class='metric-value'>{formatted_result['Proportion (%)'].max():.1f}%</div>"
                                f"<div class='metric-label'>Highest Proportion</div>"
                                f"</div>",
                                unsafe_allow_html=True
                            )
                        
                        # Add a download button with icon
                        csv = formatted_result.to_csv(index=False)
                        col1, col2 = st.columns([1, 3])
                        with col1:
                            st.download_button(
                                label="📥 Download CSV",
                                data=csv,
                                file_name=f"{identifier}_allocation.csv",
                                mime="text/csv",
                            )
                    
                    with result_tab2:
                        # Enhanced visualization
                        chart = generate_allocation_chart(result, identifier)
                        st.plotly_chart(chart, use_container_width=True)
                    
                    st.markdown("</div>", unsafe_allow_html=True)
                else:
                    st.error(f"❌ Item '{identifier}' not found in historical data or has no usage data for the selected department!")

elif view_mode == "Data Overview":
    # Data overview with improved visualization
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='header'>Data Overview</div>", unsafe_allow_html=True)
    
    # Better organized filter options
    st.markdown("<div class='subheader'>Filter Data</div>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        selected_items = st.multiselect(
            "Filter by Items",
            unique_item_names,
            default=[],
            help="Select specific items to view their data"
        )
    with col2:
        selected_overview_dept = st.multiselect(
            "Filter by Departments",
            unique_departments[1:],  # Exclude "All Departments"
            default=[],
            help="Select specific departments to view their data"
        )
    
    # Apply filters
    filtered_data = data.copy()
    if selected_items:
        filtered_data = filtered_data[filtered_data["ITEM NAME"].isin(selected_items)]
    if selected_overview_dept:
        filtered_data = filtered_data[filtered_data["DEPARTMENT"].isin(selected_overview_dept)]
    
    # Data preview with better styling
    st.markdown("<div class='subheader'>Data Preview</div>", unsafe_allow_html=True)
    display_columns = ["DATE", "ITEM NAME", "DEPARTMENT", "QUANTITY", "UNIT_OF_MEASURE"]
    
    # Format date column for better display
    filtered_display = filtered_data[display_columns].copy()
    filtered_display["DATE"] = filtered_display["DATE"].dt.strftime("%Y-%m-%d")
    
    st.dataframe(
        filtered_display.head(100),
        use_container_width=True,
        hide_index=True,
        column_config={
            "DATE": st.column_config.DateColumn("Date", help="Transaction date"),
            "ITEM NAME": st.column_config.TextColumn("Item Name", help="Name of the item"),
            "DEPARTMENT": st.column_config.TextColumn("Department", help="Department that used the item"),
            "QUANTITY": st.column_config.NumberColumn("Quantity", format="%.2f", help="Quantity used"),
            "UNIT_OF_MEASURE": st.column_config.TextColumn("Unit", help="Unit of measurement")
        }
    )
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Enhanced statistics visualization
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='header'>Usage Analytics</div>", unsafe_allow_html=True)
    
    if filtered_data.empty:
        st.info("Select items or departments to view usage analytics")
    else:
        total_usage = filtered_data["QUANTITY"].sum()
        unique_items_count = filtered_data["ITEM NAME"].nunique()
        date_range = f"{filtered_data['DATE'].min().strftime('%b %d, %Y')} to {filtered_data['DATE'].max().strftime('%b %d, %Y')}"
        
        # Metrics with better visual presentation
        stat_cols = st.columns(4)
        with stat_cols[0]:
            st.markdown(
                f"<div class='metric-card'>"
                f"<div class='metric-value'>{total_usage:,.2f}</div>"
                f"<div class='metric-label'>Total Quantity</div>"
                f"</div>",
                unsafe_allow_html=True
            )
        with stat_cols[1]:
            st.markdown(
                f"<div class='metric-card'>"
                f"<div class='metric-value'>{unique_items_count}</div>"
                f"<div class='metric-label'>Unique Items</div>"
                f"</div>",
                unsafe_allow_html=True
            )
        with stat_cols[2]:
            st.markdown(
                f"<div class='metric-card'>"
                f"<div class='metric-value'>{len(filtered_data):,}</div>"
                f"<div class='metric-label'>Transactions</div>"
                f"</div>",
                unsafe_allow_html=True
            )
        with stat_cols[3]:
            st.markdown(
                f"<div class='metric-card'>"
                f"<div class='metric-value'>{filtered_data['DEPARTMENT'].nunique()}</div>"
                f"<div class='metric-label'>Departments</div>"
                f"</div>",
                unsafe_allow_html=True
            )
        
        # Time range info
        st.info(f"Data shown for period: {date_range}")
        
        # Multiple visualizations using tabs
        chart_tab1, chart_tab2, chart_tab3 = st.tabs(["🥧 Department Distribution", "📈 Usage Trends", "🔝 Top Items"])
        
        with chart_tab1:
    # Department distribution pie chart
    dept_usage = filtered_data.groupby("DEPARTMENT")["QUANTITY"].sum().reset_index()
    fig1 = px.pie(
        dept_usage,
        values="QUANTITY",
        names="DEPARTMENT",
        title="Usage Distribution by Department",
        hole=0.4,
        color_discrete_sequence=px.colors.qualitative.Bold
    )
    fig1.update_layout(
        title_font=dict(size=18),
        title_x=0.5,
        legend_title_text="",
        legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
    )
    st.plotly_chart(fig1, use_container_width=True)

with chart_tab2:
    # Monthly usage trend line chart
    filtered_data["Month"] = filtered_data["DATE"].dt.strftime("%Y-%m")
    monthly_usage = filtered_data.groupby("Month")["QUANTITY"].sum().reset_index()
    monthly_usage = monthly_usage.sort_values("Month")
    
    fig2 = px.line(
        monthly_usage,
        x="Month",
        y="QUANTITY",
        title="Monthly Usage Trend",
        markers=True,
        line_shape="spline",
        color_discrete_sequence=["#3B82F6"]
    )
    fig2.update_layout(
        title_font=dict(size=18),
        title_x=0.5,
        xaxis_title="Month",
        yaxis_title="Total Quantity",
        xaxis=dict(tickangle=45)
    )
    st.plotly_chart(fig2, use_container_width=True)

with chart_tab3:
    # Top items by quantity
    item_usage = filtered_data.groupby("ITEM NAME")["QUANTITY"].sum().reset_index()
    top_items = item_usage.sort_values("QUANTITY", ascending=False).head(10)
    
    fig3 = px.bar(
        top_items,
        x="QUANTITY",
        y="ITEM NAME",
        orientation="h",
        title="Top 10 Items by Usage",
        color="QUANTITY",
        color_continuous_scale="Blues",
        text="QUANTITY"
    )
    fig3.update_layout(
        title_font=dict(size=18),
        title_x=0.5,
        yaxis=dict(title="", autorange="reversed"),
        xaxis_title="Total Quantity"
    )
    fig3.update_traces(
        texttemplate="%{x:.1f}",
        textposition="outside"
    )
    st.plotly_chart(fig3, use_container_width=True)

# End of chart tabs
st.markdown("</div>", unsafe_allow_html=True)

# Footer
st.markdown(
    """
    <div class='footer'>
        <p>SPP Ingredients Allocation App | Developed by Brown's Data Team</p>
        <p>Version 1.0 | Last Updated: March 2025</p>
    </div>
    """,
    unsafe_allow_html=True
)
