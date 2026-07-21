import streamlit as st
import os
import uuid
import tempfile
import pandas as pd

# Import our pipeline modules
from extractors.excel_extractor import parse_excel_invoice
from extractors.pdf_extractor import parse_pdf_invoice
from extractors.xml_extractor import parse_xml_invoice
from validators.invoice_validator import validate_invoice
from integrators.uyumsoft_excel import export_to_uyumsoft_excel

st.set_page_config(page_title="Invoice Pipeline", page_icon="📄", layout="wide", initial_sidebar_state="collapsed")

# ----------------- CUSTOM CSS -----------------
st.markdown("""
<style>
    /* Global Background and Fonts */
    .stApp {
        background-color: #0f172a;
        color: #f8fafc;
        font-family: 'Inter', sans-serif;
    }
    
    /* Main App Container */
    [data-testid="block-container"] {
        background-color: #1e293b;
        border-radius: 12px;
        padding: 2rem 3rem;
        margin-top: 2rem;
        border: 1px solid #334155;
    }

    /* Gradient Title */
    .main-title {
        text-align: center;
        background: linear-gradient(90deg, #38bdf8, #34d399);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 3rem;
        font-weight: bold;
        margin-bottom: 0.5rem;
    }
    .sub-title {
        text-align: center;
        color: #94a3b8;
        font-size: 1.1rem;
        margin-bottom: 3rem;
    }

    /* Section Headers */
    .section-header {
        font-size: 1.5rem;
        font-weight: 600;
        color: #f8fafc;
        margin-top: 2rem;
        margin-bottom: 1.5rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    
    /* Valid Badge */
    .valid-badge {
        background-color: #064e3b;
        color: #34d399;
        padding: 0.3rem 1rem;
        border-radius: 9999px;
        font-size: 0.875rem;
        font-weight: 600;
        border: 1px solid #059669;
    }
    
    .error-badge {
        background-color: #7f1d1d;
        color: #fca5a5;
        padding: 0.3rem 1rem;
        border-radius: 9999px;
        font-size: 0.875rem;
        font-weight: 600;
        border: 1px solid #ef4444;
    }

    /* Metric Cards (Overriding st.metric) */
    [data-testid="stMetric"] {
        background-color: #0f172a;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #334155;
    }
    [data-testid="stMetricLabel"] {
        color: #94a3b8;
        font-size: 0.75rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    [data-testid="stMetricValue"] {
        color: #f8fafc;
        font-size: 1.25rem !important;
        font-weight: 600;
    }

    /* Custom HTML Table */
    .custom-table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 1rem;
        font-size: 0.95rem;
    }
    .custom-table th {
        background-color: transparent;
        color: #94a3b8;
        text-align: left;
        padding: 1rem;
        border-bottom: 1px solid #334155;
        font-weight: 500;
    }
    .custom-table td {
        padding: 1rem;
        border-bottom: 1px solid #1e293b;
        color: #f8fafc;
    }
    .custom-table tr:hover {
        background-color: #1e293b;
    }
</style>
""", unsafe_allow_html=True)
# ----------------------------------------------

st.markdown("<div class='main-title'>Fatura Veri Otomasyonu</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-title'>Faturalarınızı (PDF, XML, Excel) sisteme yükleyin, kalemleri otomatik olarak ayıklansın ve Uyumsoft şablonuna aktarılsın.</div>", unsafe_allow_html=True)

uploaded_file = st.file_uploader("Faturanızı Yükleyin", type=["pdf", "xml", "xlsx", "xls", "csv"], label_visibility="collapsed")

if uploaded_file is not None:
    st.info(f"İşleniyor: {uploaded_file.name}...")
    
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
        temp_file.write(uploaded_file.getvalue())
        temp_path = temp_file.name
        
    try:
        data = None
        if ext in ['.xlsx', '.xls', '.csv']:
            data = parse_excel_invoice(temp_path)
        elif ext == '.pdf':
            data = parse_pdf_invoice(temp_path)
        elif ext == '.xml':
            data = parse_xml_invoice(temp_path)
        else:
            st.error(f"Desteklenmeyen dosya formatı: {ext}")
            st.stop()
            
        if data is None:
             st.error("Fatura okunamadı.")
        else:
            is_valid, errors = validate_invoice(data)
            
            # Validation Badge HTML
            if is_valid:
                badge_html = "<span class='valid-badge'>GEÇERLİ</span>"
            else:
                badge_html = "<span class='error-badge'>HATALI</span>"
            
            # --- METRICS SECTION ---
            st.markdown(f"<div class='section-header'><div>Fatura Özeti</div><div>{badge_html}</div></div>", unsafe_allow_html=True)
            
            # Show errors if any
            if not is_valid:
                for err in errors:
                    st.error(err)

            c1, c2, c3, c4, c5 = st.columns(5)
            
            vkn = data.get("customer_tax_id", "-")
            
            with c1:
                st.metric("TARİH", data.get("date", "-"))
            with c2:
                st.metric("MÜŞTERİ VKN", vkn)
            with c3:
                st.metric("ARA TOPLAM", f"₺{data.get('subtotal', '-')}")
            with c4:
                st.metric("KDV", f"₺{data.get('tax_amount', '-')}")
            with c5:
                st.metric("GENEL TOPLAM", f"₺{data.get('total_amount', '-')}")
            
            # --- ITEMS SECTION ---
            st.markdown("<div class='section-header'>Fatura Kalemleri</div>", unsafe_allow_html=True)
            
            items = data.get("items", [])
            if items:
                df = pd.DataFrame(items)
                
                # Format to nice strings, replacing None with "-"
                df = df.fillna("-")
                
                # Translate columns
                rename_map = {
                    "code": "Ürün Kodu",
                    "description": "Ürün Açıklaması",
                    "quantity": "Miktar",
                    "unit_price": "Birim Fiyat",
                    "tax_rate": "KDV Oranı",
                    "total_price": "Satır Toplamı",
                    "line_total": "Satır Toplamı"
                }
                df = df.rename(columns=rename_map)
                
                # Convert DataFrame to custom HTML table
                html_table = df.to_html(index=False, classes="custom-table", escape=False)
                st.markdown(html_table, unsafe_allow_html=True)
                
            else:
                st.info("Herhangi bir kalem bulunamadı.")
            
            st.write("")
            st.write("")
            
            # --- EXPORT SECTION ---
            if is_valid and items:
                output_excel_path = f"Uyumsoft_{file_id}.xlsx"
                export_to_uyumsoft_excel([data], output_excel_path)
                
                with open(output_excel_path, "rb") as file:
                    st.download_button(
                        label="⬇️ Uyumsoft Excel Taslağını İndir",
                        data=file,
                        file_name=f"Uyumsoft_Aktarim_{uploaded_file.name}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                os.remove(output_excel_path)

    except Exception as e:
        st.error(f"Beklenmeyen bir hata oluştu: {str(e)}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
