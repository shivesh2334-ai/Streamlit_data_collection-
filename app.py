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

import datetime
from typing import List, Dict

import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials
import gspread

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
            bsi_opts = ["Primary", "Lung", "Secondary", "Unknown"]

