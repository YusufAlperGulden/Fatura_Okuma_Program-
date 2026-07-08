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

st.set_page_config(page_title="Invoice Data Extractor", page_icon="📄", layout="wide")

st.title("📄 Akıllı Fatura Okuyucu")
st.markdown("Faturalarınızı (PDF, XML, Excel) sisteme yükleyin, kalemleri otomatik olarak ayıklansın ve Uyumsoft şablonuna aktarılsın.")

uploaded_file = st.file_uploader("Faturanızı Yükleyin", type=["pdf", "xml", "xlsx", "xls", "csv"])

if uploaded_file is not None:
    st.info(f"İşleniyor: {uploaded_file.name}...")
    
    # Save the file temporarily
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
        temp_file.write(uploaded_file.getvalue())
        temp_path = temp_file.name
        
    try:
        # Process based on extension
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
            # Validate
            is_valid, errors = validate_invoice(data)
            
            # Layout for results
            col1, col2 = st.columns([1, 2])
            
            with col1:
                st.subheader("Fatura Özeti")
                st.metric("Fatura No", data.get("invoice_number", "-"))
                st.metric("Tarih", data.get("date", "-"))
                
                # Show additional details that were in the old UI
                vkn = data.get("supplier_vkn") or data.get("buyer_vkn") or "-"
                st.write(f"**Müşteri / Satıcı VKN:** {vkn}")
                st.write(f"**Ara Toplam:** {data.get('subtotal', '-')} TL")
                st.write(f"**KDV Toplamı:** {data.get('tax_total', '-')} TL")
                st.write(f"**Genel Toplam:** {data.get('total', '-')} TL")
                
                if is_valid:
                    st.success("✅ Tüm hesaplamalar tutarlı.")
                else:
                    st.error("❌ Hata tespit edildi.")
                    for err in errors:
                        st.warning(err)
            
            with col2:
                st.subheader("Fatura Kalemleri")
                items = data.get("items", [])
                if items:
                    df = pd.DataFrame(items)
                    
                    # Sütun isimlerini Türkçeye çevir ve düzenle
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
                    
                    # Display the dataframe without coercing Turkish numbers to NaN
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info("Herhangi bir kalem bulunamadı.")
            
            # Export to Excel
            if is_valid and items:
                st.subheader("İndirme İşlemleri")
                output_excel_path = f"Uyumsoft_{file_id}.xlsx"
                export_to_uyumsoft_excel([data], output_excel_path)
                
                with open(output_excel_path, "rb") as file:
                    st.download_button(
                        label="⬇️ Uyumsoft Excel Taslağını İndir",
                        data=file,
                        file_name=f"Uyumsoft_Aktarim_{uploaded_file.name}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                # Cleanup output file
                os.remove(output_excel_path)

    except Exception as e:
        st.error(f"Beklenmeyen bir hata oluştu: {str(e)}")
    finally:
        # Cleanup temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)
