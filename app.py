"""
Streamlit app for collecting Antimicrobial Resistance patient data in a single Google Sheet
and exporting the data as CSV.

Features / improvements:
- Robust service-account credentials handling (fixes escaped newlines in private_key)
- Canonical field order mapping so the sheet and app remain consistent
- Safe selectbox index resolution to avoid ValueError when stored values change
- Batch row update (single-range update) to avoid slow cell-by-cell updates
- Ensures headers exist before appending or replacing rows
- CSV export via a dedicated Download CSV button
- Optional delete patient action
- Better session_state initialization and smaller, focused helper functions
"""

import io
import datetime
from typing import List, Dict

import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials
import gspread
from gspread_dataframe import set_with_dataframe

# Page config
st.set_page_config(page_title="AMR Data Collector", page_icon="🦠", layout="wide")

# Google Sheets required scopes
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Canonical fields order used for sheet and exports
FIELDS = [
    "Age", "Gender", "Species", "Rectal_CPE_Pos", "Setting", "Acquisition", "BSI_Source",
    "CHF", "CKD", "Tumor", "Diabetes", "Immunosuppressed",
    "CR", "BLBLI_R", "FQR", "GC3_R",
    "Timestamp", "Entry_By"
]


# -------------------------
# Helpers for Google Sheets
# -------------------------
@st.cache_resource(ttl=3600)
def get_google_sheets_client():
    """
    Initialize gspread client from st.secrets["gcp_service_account"].
    Corrects the private_key if newlines are escaped in TOML.
    Returns gspread client or None.
    """
    if "gcp_service_account" not in st.secrets:
        st.error("gcp_service_account not found in Streamlit secrets.")
        return None
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        # Fix escaped newlines if present
        if "private_key" in creds_dict and isinstance(creds_dict["private_key"], str):
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Failed to create Google Sheets client: {e}")
        return None


def ensure_sheet_headers(worksheet, fields: List[str]):
    """
    Ensure the sheet has a header row matching `fields`.
    If empty, write the canonical headers.
    If existing headers are different, leave them but the app will read/write using canonical mapping.
    """
    values = worksheet.get_all_values()
    if not values:
        worksheet.append_row(fields, value_input_option="USER_ENTERED")


def load_data_from_sheets(client: gspread.Client, spreadsheet_id: str) -> pd.DataFrame:
    """
    Load all records from the first worksheet of the spreadsheet.
    Returns a DataFrame reindexed to canonical FIELDS (missing columns filled with empty string).
    """
    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.get_worksheet(0)
        ensure_sheet_headers(worksheet, FIELDS)
        records = worksheet.get_all_records()
        if not records:
            return pd.DataFrame(columns=FIELDS)
        df = pd.DataFrame(records)
        # Reindex to canonical fields so UI and export are consistent
        df = df.reindex(columns=FIELDS, fill_value="")
        return df
    except Exception as e:
        st.error(f"Error loading data from Google Sheets: {e}")
        return pd.DataFrame(columns=FIELDS)


def append_patient_to_sheet(client: gspread.Client, spreadsheet_id: str, patient: Dict) -> bool:
    """
    Append a single patient record to the first worksheet.
    Values are ordered according to FIELDS.
    """
    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.get_worksheet(0)
        ensure_sheet_headers(worksheet, FIELDS)
        row = [patient.get(f, "") for f in FIELDS]
        worksheet.append_row(row, value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        st.error(f"Failed to append patient to sheet: {e}")
        return False


def update_patient_in_sheet(client: gspread.Client, spreadsheet_id: str, index_0_based: int, patient: Dict) -> bool:
    """
    Update a row in the sheet given the 0-based data index (first data row is index 0 => sheet row 2).
    Uses a single range update for the whole row.
    """
    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.get_worksheet(0)
        # Data rows start at row 2 (row 1 is header)
        sheet_row = index_0_based + 2
        values = [patient.get(f, "") for f in FIELDS]
        # Compute last column letter (works while len(FIELDS) <= 26)
        last_col = chr(64 + len(values))
        range_a1 = f"A{sheet_row}:{last_col}{sheet_row}"
        worksheet.update(range_a1, [values], value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        st.error(f"Failed to update patient in sheet: {e}")
        return False


def delete_patient_in_sheet(client: gspread.Client, spreadsheet_id: str, index_0_based: int) -> bool:
    """
    Delete a row corresponding to the 0-based data index.
    """
    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.get_worksheet(0)
        sheet_row = index_0_based + 2
        worksheet.delete_rows(sheet_row)
        return True
    except Exception as e:
        st.error(f"Failed to delete patient row in sheet: {e}")
        return False


# -------------------------
# UI and state management
# -------------------------
def safe_index(options: List, value, default=0):
    """Return index of value in options or default if not found."""
    try:
        return options.index(value)
    except Exception:
        return default


def init_session_state():
    if "patients_df" not in st.session_state:
        st.session_state.patients_df = pd.DataFrame(columns=FIELDS)
    if "editing_mode" not in st.session_state:
        st.session_state.editing_mode = False
    if "selected_idx" not in st.session_state:
        st.session_state.selected_idx = None
    if "is_new" not in st.session_state:
        st.session_state.is_new = False


# -------------------------
# App layout
# -------------------------
init_session_state()
st.title("🦠 AMR Patient Data Collector")
st.markdown("Collect patient records into a single Google Sheet and export as CSV for ML training")

# Verify required secrets
if "spreadsheet_id" not in st.secrets or "gcp_service_account" not in st.secrets:
    st.error("Please configure Streamlit secrets with `spreadsheet_id` and `gcp_service_account`.")
    st.info(
        "Create a Google Service Account JSON and add it under [gcp_service_account] in .streamlit/secrets.toml, "
        "and add spreadsheet_id = 'YOUR_SHEET_ID'."
    )
    st.stop()

spreadsheet_id = st.secrets["spreadsheet_id"]
client = get_google_sheets_client()

# Sidebar controls
with st.sidebar:
    st.header("Data Controls")
    total = len(st.session_state.patients_df)
    st.metric("Total records", total)

    if st.button("🔄 Sync from Google Sheet"):
        if client:
            df = load_data_from_sheets(client, spreadsheet_id)
            st.session_state.patients_df = df
            st.success("Data synced from Google Sheets")
            st.experimental_rerun()
        else:
            st.error("Not connected to Google Sheets")

    if st.button("➕ Add new record"):
        st.session_state.editing_mode = True
        st.session_state.is_new = True
        st.session_state.selected_idx = len(st.session_state.patients_df)
        st.experimental_rerun()

    st.markdown("---")
    st.subheader("Export")
    if len(st.session_state.patients_df) > 0:
        csv_bytes = st.session_state.patients_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download CSV",
            data=csv_bytes,
            file_name=f"amr_data_{datetime.date.today()}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.info("No data to export yet")

    st.markdown("---")
    st.subheader("Connection")
    if client:
        st.success("✅ Connected to Google Sheets")
    else:
        st.error("❌ Not connected")


# Main area: show table or form
if not st.session_state.editing_mode:
    st.markdown("### Records")
    if st.session_state.patients_df.empty:
        st.info("No records available. Use 'Add new record' to start.")
    else:
        df_display = st.session_state.patients_df.reset_index(drop=True)
        col1, col2 = st.columns([4, 1])
        with col1:
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        with col2:
            st.markdown("#### Actions")
            for idx in range(len(df_display)):
                # Buttons for each record
                c1, c2 = st.columns([1, 1])
                with c1:
                    if st.button("✏️ Edit", key=f"edit_{idx}"):
                        st.session_state.editing_mode = True
                        st.session_state.is_new = False
                        st.session_state.selected_idx = idx
                        st.experimental_rerun()
                with c2:
                    if st.button("🗑️ Delete", key=f"del_{idx}"):
                        # Delete locally and in sheet (if connected)
                        if client:
                            if delete_patient_in_sheet(client, spreadsheet_id, idx):
                                # reload after deletion
                                df = load_data_from_sheets(client, spreadsheet_id)
                                st.session_state.patients_df = df
                                st.success(f"Record {idx+1} deleted from sheet")
                                st.experimental_rerun()
                            else:
                                st.error("Failed to delete record in sheet")
                        else:
                            # Local delete only
                            st.session_state.patients_df = st.session_state.patients_df.drop(index=idx).reset_index(drop=True)
                            st.success("Record deleted (local only)")
                            st.experimental_rerun()
else:
    # Editing form
    idx = st.session_state.selected_idx or 0
    is_new = st.session_state.is_new
    st.markdown(f"### {'➕ Add new record' if is_new else f'✏️ Edit record {idx+1}'}")

    existing = {} if is_new or st.session_state.patients_df.empty else st.session_state.patients_df.iloc[idx].to_dict()

    with st.form("patient_form", clear_on_submit=False):
        col_a, col_b = st.columns(2)
        with col_a:
            age = st.number_input("Age", min_value=0, max_value=120, value=int(existing.get("Age", 65) or 65))
            gender_opts = ["Male", "Female", "Other"]
            gender = st.selectbox("Gender", gender_opts, index=safe_index(gender_opts, existing.get("Gender", "Male")))
            species_opts = ["E. coli", "Klebsiella spp.", "Proteus spp.", "Pseudomonas spp.", "Acinetobacter spp.", "Other"]
            species = st.selectbox("Species", species_opts, index=safe_index(species_opts, existing.get("Species", "E. coli")))
            rectal = st.selectbox("Rectal CPE Positive", [0, 1], index=safe_index([0, 1], int(existing.get("Rectal_CPE_Pos", 0))))
            setting_opts = ["ICU", "Internal Medicine", "Emergency", "Surgical Ward"]
            setting = st.selectbox("Setting", setting_opts, index=safe_index(setting_opts, existing.get("Setting", "ICU")))
            acquisition = st.selectbox("Acquisition", ["Community", "Hospital"], index=safe_index(["Community", "Hospital"], existing.get("Acquisition", "Community")))
            bsi_opts = ["Primary", "Lung", "Abdomen", "UTI", "Catheter", "Other"]
            bsi_source = st.selectbox("BSI Source", bsi_opts, index=safe_index(bsi_opts, existing.get("BSI_Source", "Primary")))

        with col_b:
            chf = st.selectbox("CHF", [0, 1], index=safe_index([0, 1], int(existing.get("CHF", 0))))
            ckd = st.selectbox("CKD", [0, 1], index=safe_index([0, 1], int(existing.get("CKD", 0))))
            tumor = st.selectbox("Tumor", [0, 1], index=safe_index([0, 1], int(existing.get("Tumor", 0))))
            diabetes = st.selectbox("Diabetes", [0, 1], index=safe_index([0, 1], int(existing.get("Diabetes", 0))))
            imsup = st.selectbox("Immunosuppressed", [0, 1], index=safe_index([0, 1], int(existing.get("Immunosuppressed", 0))))
            cr = st.selectbox("CR (Carbapenem Resistance)", [0, 1], index=safe_index([0, 1], int(existing.get("CR", 0))))
            blbli = st.selectbox("BLBLI_R", [0, 1], index=safe_index([0, 1], int(existing.get("BLBLI_R", 0))))
            fqr = st.selectbox("FQR", [0, 1], index=safe_index([0, 1], int(existing.get("FQR", 0))))
            gc3 = st.selectbox("3GC_R", [0, 1], index=safe_index([0, 1], int(existing.get("GC3_R", 0))))

        save_btn = st.form_submit_button("💾 Save")
        cancel_btn = st.form_submit_button("❌ Cancel")

        if save_btn:
            record = {
                "Age": age,
                "Gender": gender,
                "Species": species,
                "Rectal_CPE_Pos": rectal,
                "Setting": setting,
                "Acquisition": acquisition,
                "BSI_Source": bsi_source,
                "CHF": chf,
                "CKD": ckd,
                "Tumor": tumor,
                "Diabetes": diabetes,
                "Immunosuppressed": imsup,
                "CR": cr,
                "BLBLI_R": blbli,
                "FQR": fqr,
                "GC3_R": gc3,
                "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Entry_By": st.secrets.get("user_email", "Unknown"),
            }

            # Local update
            if is_new:
                st.session_state.patients_df = st.session_state.patients_df.append(record, ignore_index=True)
            else:
                st.session_state.patients_df.iloc[idx] = pd.Series(record)

            # Push to sheet if connected
            if client:
                if is_new:
                    ok = append_patient_to_sheet(client, spreadsheet_id, record)
                    if ok:
                        # refresh entire sheet for consistent ordering and ids
                        st.session_state.patients_df = load_data_from_sheets(client, spreadsheet_id)
                        st.success("New record added to Google Sheet.")
                    else:
                        st.error("Failed to add record to Google Sheet.")
                else:
                    ok = update_patient_in_sheet(client, spreadsheet_id, idx, record)
                    if ok:
                        st.session_state.patients_df = load_data_from_sheets(client, spreadsheet_id)
                        st.success("Record updated in Google Sheet.")
                    else:
                        st.error("Failed to update record in Google Sheet.")

            else:
                st.info("Saved locally (Google Sheets not connected). Use Sync later to push/fetch changes.")

            st.session_state.editing_mode = False
            st.session_state.is_new = False
            st.session_state.selected_idx = None
            st.experimental_rerun()

        if cancel_btn:
            st.session_state.editing_mode = False
            st.session_state.is_new = False
            st.session_state.selected_idx = None
            st.experimental_rerun()


# Footer instructions
with st.expander("Setup & Notes"):
    st.write(
        "1) Create a Google Cloud Service Account and enable Sheets & Drive APIs.\n"
        "2) Share your Google Sheet with the service account email.\n"
        "3) Add service account JSON contents under [gcp_service_account] in .streamlit/secrets.toml and set spreadsheet_id.\n"
        "4) If you paste the private_key into secrets.toml, escape newlines as \\n; this app will fix them automatically."
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
