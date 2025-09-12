import streamlit as st
import pandas as pd
import datetime
from io import BytesIO

# Page configuration
st.set_page_config(
    page_title="Antimicrobial Resistance Data Collection",
    page_icon="🦠",
    layout="wide"
)

# Initialize session state
if 'patients_data' not in st.session_state:
    st.session_state.patients_data = []

st.title("🦠 Patient Records - Antimicrobial Resistance Study")
st.markdown("### Data Collection for Machine Learning Model Training")

# Sidebar for patient navigation
with st.sidebar:
    st.header("📊 Data Management")
    patient_count = len(st.session_state.patients_data)
    st.metric("Total Patients", patient_count)
    
    if st.button("➕ Add New Patient"):
        st.session_state.patients_data.append({})
        st.rerun()
    
    if patient_count > 0:
        if st.button("📥 Download CSV"):
            df = pd.DataFrame(st.session_state.patients_data)
            csv = df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"patient_data_{datetime.date.today()}.csv",
                mime="text/csv"
            )

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
                'timestamp': datetime.datetime.now().isoformat()
            }
            st.success(f"✅ Patient {patient_idx + 1} data saved!")
    
    # Display current data
    if st.session_state.patients_data:
        st.markdown("### 📋 Current Data Summary")
        df = pd.DataFrame(st.session_state.patients_data)
        st.dataframe(df, use_container_width=True)

# Instructions
with st.expander("📖 Deployment Instructions"):
    st.markdown("""
    **To deploy this app:**
    
    1. **Save this code** as `app.py`
    2. **Create requirements.txt:**
       ```
       streamlit
       pandas
       ```
    3. **Deploy options:**
       - **Streamlit Cloud:** Push to GitHub → streamlit.io → Deploy
       - **Heroku:** `git push heroku main`
       - **Local:** `streamlit run app.py`
    
    **For production use:**
    - Add authentication (streamlit-authenticator)
    - Connect to database (PostgreSQL, MongoDB)
    - Add data validation and error handling
    - Implement user roles and permissions
    """)
