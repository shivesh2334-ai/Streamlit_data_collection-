import streamlit as st
import gspread
from google.oauth2 import service_account
import pandas as pd
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="ICU Antibiotic Tracking",
    page_icon="💊",
    layout="wide"
)

# Initialize session state
if 'patients_data' not in st.session_state:
    st.session_state.patients_data = []

# Google Sheets connection with better error handling
@st.cache_resource
def get_google_sheet_client():
    """Initialize and return Google Sheets client"""
    try:
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

        # Check if secrets exist
        if "gcp_service_account" not in st.secrets:
            st.error("❌ Google Cloud credentials not found in secrets!")
            return None, "Missing gcp_service_account in secrets"

        credentials = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=scope
        )

        client = gspread.authorize(credentials)
        return client, None

    except KeyError as e:
        error_msg = f"Missing key in secrets: {e}"
        st.error(f"❌ Configuration Error: {error_msg}")
        return None, error_msg
    except Exception as e:
        error_msg = f"Authentication error: {str(e)}"
        st.error(f"❌ {error_msg}")
        return None, error_msg

def get_sheet_id():
    """Extract Sheet ID from secrets"""
    try:
        if "sheets" not in st.secrets or "url" not in st.secrets["sheets"]:
            return None, "Sheet URL not configured in secrets"

        sheet_url = st.secrets["sheets"]["url"]

        # Extract ID from URL if it's a full URL
        if "docs.google.com/spreadsheets" in sheet_url:
            if "/d/" in sheet_url:
                sheet_id = sheet_url.split("/d/")[1].split("/")[0]
            else:
                return None, "Invalid Sheet URL format"
        else:
            # Assume it's already just the ID
            sheet_id = sheet_url

        return sheet_id, None

    except Exception as e:
        return None, f"Error extracting Sheet ID: {str(e)}"

def read_sheet(sheet_id, worksheet_name="Sheet1"):
    """Read data from Google Sheet"""
    try:
        client, error = get_google_sheet_client()
        if error:
            return None, error

        if not sheet_id:
            return None, "Sheet ID is empty"

        # Try to open the spreadsheet
        try:
            sheet = client.open_by_key(sheet_id)
        except gspread.exceptions.SpreadsheetNotFound:
            return None, f"Spreadsheet not found. Please verify:\n1. Sheet ID is correct: {sheet_id}\n2. Sheet is shared with service account"
        except gspread.exceptions.APIError as e:
            return None, f"Google API Error: {str(e)}"

        # Try to get the worksheet
        try:
            worksheet = sheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            return None, f"Worksheet '{worksheet_name}' not found. Available worksheets: {[ws.title for ws in sheet.worksheets()]}"

        # Get all records
        data = worksheet.get_all_records()

        if not data:
            return pd.DataFrame(), None

        return pd.DataFrame(data), None

    except Exception as e:
        return None, f"Unexpected error: {str(e)}"

def append_to_sheet(sheet_id, row_data, worksheet_name="Sheet1"):
    """Append a row to Google Sheet"""
    try:
        client, error = get_google_sheet_client()
        if error:
            return False, error

        sheet = client.open_by_key(sheet_id)
        worksheet = sheet.worksheet(worksheet_name)
        worksheet.append_row(row_data)

        return True, None

    except gspread.exceptions.SpreadsheetNotFound:
        return False, "Spreadsheet not found"
    except gspread.exceptions.WorksheetNotFound:
        return False, f"Worksheet '{worksheet_name}' not found"
    except Exception as e:
        return False, f"Error appending data: {str(e)}"

def initialize_sheet_if_empty(sheet_id, worksheet_name="Sheet1"):
    """Initialize sheet with headers if empty"""
    try:
        client, error = get_google_sheet_client()
        if error:
            return False, error

        sheet = client.open_by_key(sheet_id)
        worksheet = sheet.worksheet(worksheet_name)

        # Check if sheet is empty
        if not worksheet.get_all_values():
            headers = ["Patient ID", "Antibiotic", "Dosage", "Date", "Time", "Added By"]
            worksheet.append_row(headers)
            return True, "Headers added successfully"

        return True, None

    except Exception as e:
        return False, f"Error initializing sheet: {str(e)}"

# Sidebar for adding new patients
with st.sidebar:
    st.header("Patient Management")
    
    if st.button("➕ Add New Patient"):
        st.session_state.patients_data.append({
            'Age': 65,
            'Gender': "",
            'Species': "",
            'Rectal_CPE_Pos': "",
            'Setting': "",
            'Acquisition': "",
            'BSI_Source': "",
            'CHF': "",
            'CKD': "",
            'Tumor': "",
            'Diabetes': "",
            'Immunosuppressed': "",
            'CR': "",
            'BLBLI_R': "",
            'FQR': "",
            '3GC_R': "",
            'timestamp': datetime.now().isoformat()
        })
        st.success("New patient added!")
    
    if st.button("🗑️ Clear All Patients"):
        st.session_state.patients_data = []
        st.success("All patients cleared!")
    
    st.markdown("---")
    st.markdown(f"**Total Patients:** {len(st.session_state.patients_data)}")

# Main content
st.title("💊 ICU Antibiotic Tracking System")

# Main data entry form
if len(st.session_state.patients_data) == 0:
    st.info("👆 Click 'Add New Patient' in the sidebar to start data collection")
else:
    # Patient selector
    patient_idx = st.selectbox(
        "Select Patient to Edit:",
        range(len(st.session_state.patients_data)),
        format_func=lambda x: f"Patient {x+1}"
    )

    st.markdown(f"### Editing Patient {patient_idx + 1}")

    # Create form
    with st.form(f"patient_form_{patient_idx}"):
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("👤 Demographics")
            age = st.number_input("Age", min_value=18, max_value=90,
                                value=st.session_state.patients_data[patient_idx].get('Age', 65))
            gender = st.selectbox("Gender", ["", "Male", "Female"],
                                index=["", "Male", "Female"].index(st.session_state.patients_data[patient_idx].get('Gender', "")))

            st.subheader("🔬 Microbiological Data")
            species = st.selectbox("Species",
                                 ["", "E. coli", "Klebsiella spp.", "Proteus spp.", "Pseudomonas spp.", "Acinetobacter spp."],
                                 index=["", "E. coli", "Klebsiella spp.", "Proteus spp.", "Pseudomonas spp.", "Acinetobacter spp."].index(
                                     st.session_state.patients_data[patient_idx].get('Species', "")))
            rectal_cpe = st.selectbox("Rectal CPE Positive", ["", "0", "1"],
                                    index=["", "0", "1"].index(str(st.session_state.patients_data[patient_idx].get('Rectal_CPE_Pos', ""))))

            st.subheader("🏥 Clinical Context")
            setting = st.selectbox("Setting", ["", "ICU", "Internal Medicine"],
                                 index=["", "ICU", "Internal Medicine"].index(st.session_state.patients_data[patient_idx].get('Setting', "")))
            acquisition = st.selectbox("Acquisition", ["", "Community", "Hospital"],
                                     index=["", "Community", "Hospital"].index(st.session_state.patients_data[patient_idx].get('Acquisition', "")))
            bsi_source = st.selectbox("BSI Source", ["", "Primary", "Lung", "Abdomen", "UTI"],
                                    index=["", "Primary", "Lung", "Abdomen", "UTI"].index(st.session_state.patients_data[patient_idx].get('BSI_Source', "")))

        with col2:
            st.subheader("🫀 Comorbidities")
            chf = st.selectbox("CHF", ["", "0", "1"],
                             index=["", "0", "1"].index(str(st.session_state.patients_data[patient_idx].get('CHF', ""))))
            ckd = st.selectbox("CKD", ["", "0", "1"],
                             index=["", "0", "1"].index(str(st.session_state.patients_data[patient_idx].get('CKD', ""))))
            tumor = st.selectbox("Tumor", ["", "0", "1"],
                               index=["", "0", "1"].index(str(st.session_state.patients_data[patient_idx].get('Tumor', ""))))
            diabetes = st.selectbox("Diabetes", ["", "0", "1"],
                                  index=["", "0", "1"].index(str(st.session_state.patients_data[patient_idx].get('Diabetes', ""))))
            immunosuppressed = st.selectbox("Immunosuppressed", ["", "0", "1"],
                                          index=["", "0", "1"].index(str(st.session_state.patients_data[patient_idx].get('Immunosuppressed', ""))))

            st.subheader("🧪 Resistance Outcomes")
            cr = st.selectbox("CR (Carbapenem Resistance)", ["", "0", "1"],
                            index=["", "0", "1"].index(str(st.session_state.patients_data[patient_idx].get('CR', ""))))
            blbli_r = st.selectbox("BLBLI_R", ["", "0", "1"],
                                 index=["", "0", "1"].index(str(st.session_state.patients_data[patient_idx].get('BLBLI_R', ""))))
            fqr = st.selectbox("FQR (Fluoroquinolone Resistance)", ["", "0", "1"],
                             index=["", "0", "1"].index(str(st.session_state.patients_data[patient_idx].get('FQR', ""))))
            gc3_r = st.selectbox("3GC_R", ["", "0", "1"],
                               index=["", "0", "1"].index(str(st.session_state.patients_data[patient_idx].get('3GC_R', ""))))

        # Save button
        if st.form_submit_button("💾 Save Patient Data"):
            st.session_state.patients_data[patient_idx] = {
                'Age': age,
                'Gender': gender,
                'Species': species,
                'Rectal_CPE_Pos': rectal_cpe,
                'Setting': setting,
                'Acquisition': acquisition,
                'BSI_Source': bsi_source,
                'CHF': chf,
                'CKD': ckd,
                'Tumor': tumor,
                'Diabetes': diabetes,
                'Immunosuppressed': immunosuppressed,
                'CR': cr,
                'BLBLI_R': blbli_r,
                'FQR': fqr,
                '3GC_R': gc3_r,
                'timestamp': datetime.now().isoformat()
            }
            st.success(f"✅ Patient {patient_idx + 1} data saved!")

    # Display current data
    if st.session_state.patients_data:
        st.markdown("### 📋 Current Data Summary")
        df = pd.DataFrame(st.session_state.patients_data)
        st.dataframe(df, use_container_width=True)

# Google Sheets integration section
st.markdown("---")
st.header("📊 Google Sheets Integration")

sheet_id, sheet_error = get_sheet_id()
if sheet_error:
    st.error(f"Sheet ID Error: {sheet_error}")
else:
    st.success(f"Sheet ID: {sheet_id}")

if st.button("🔄 Sync with Google Sheets"):
    if sheet_id:
        success, message = initialize_sheet_if_empty(sheet_id)
        if success:
            st.success("Google Sheets connection established!")
            
            # Here you would add code to sync your patient data with Google Sheets
            # For example:
            for i, patient in enumerate(st.session_state.patients_data):
                row_data = [
                    f"Patient_{i+1}",
                    "Antibiotic_Data",  # You would replace this with actual antibiotic data
                    "Dosage_Data",     # You would replace this with actual dosage data
                    datetime.now().strftime("%Y-%m-%d"),
                    datetime.now().strftime("%H:%M:%S"),
                    "Streamlit App"
                ]
                success, error = append_to_sheet(sheet_id, row_data)
                if error:
                    st.error(f"Error syncing patient {i+1}: {error}")
            
            st.success("Data synced with Google Sheets!")
        else:
            st.error(f"Failed to initialize sheet: {message}")
    else:
        st.error("No valid Sheet ID found")

# ------------------------------------------------------------
# DEPLOYMENT INSTRUCTIONS
# ------------------------------------------------------------
with st.expander("📖 Deployment Instructions"):
    st.markdown(
        """
        **To deploy this app:**

        1. Save this code as `app.py`
        2. Create a file named `requirements.txt` with the following:
           ```
           streamlit
           pandas
           gspread
           google-auth
           ```
        3. Deploy via:
           - **Streamlit Cloud:** Push to GitHub → [streamlit.io](https://streamlit.io) → Deploy
           - **Local (for testing):**
             ```bash
             streamlit run app.py
             ```
        """
            )
