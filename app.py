import streamlit as st
from docx import Document
import json
import requests
import os
import io

st.set_page_config(page_title="Сравнение спецификаций", layout="wide")
st.title("📄 Сравнение спецификаций оборудования")

def extract_compact_data(file_obj):
    """
    Читает .docx, вытаскивает таблицы, возвращает компактный текст.
    Плюс выводит в интерфейс отладочную информацию.
    """
    # Исправляем чтение байтов для Streamlit Cloud
    doc = Document(io.BytesIO(file_obj.read()))
    
    lines = []
    tables_found = 0
    rows_processed = 0
    
    for table in doc.tables:
        tables_found += 1
        if len(table.rows) < 2:
            continue
            
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if not any(cells):
                continue
            
            # Берем только первые 5 колонок
            compact_line = ";".join(cells[:5])
            lines.append(compact_line)
            rows_processed += 1

    # --- ОТЛАДКА: показываем, что реально ушло в нейросеть ---
    if lines:
        st.write(f"✅ Найдено таблиц: {tables_found}")
        st.info(f"📦 Подготовлено строк для анализа: {rows_processed}")
        
        st.caption("👀 Первые 3 строки (формат: Код;Наименование;Ед;Кол;Цена):")
        # st.code делает красивый моноширинный блок, чтобы видно было структуру
        for line in lines[:3]:
            st.code(line, language="text")
        
        # Если хочешь видеть ВСЁ (для очень маленьких файлов), раскомментируй строку ниже:
        # st.write("Полный сырой список:", "\n".join(lines))
    else:
        st.warning("⚠️ В файлах не найдено данных в таблицах.")

    return "\n".join(lines)

def get_llm_response(doc1_data, doc2_data):
    IAM_TOKEN = os.getenv("YANDEX_IAM_TOKEN")
    FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

    if not IAM_TOKEN or not FOLDER_ID:
        return "❌ Ошибка: Не заданы переменные YANDEX_IAM_TOKEN и YANDEX_FOLDER_ID в настройках Streamlit."

    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        "Authorization": f"Bearer {IAM_TOKEN}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""
    Ты — инженер-сметчик. Сравни данные из двух спецификаций (формат: Код;Наименование;Ед;Кол-во;Цена).
    1. Сопоставь позиции по смыслу.
    2. Верни ТОЛЬКО валидный JSON массив объектов в начале ответа.
       Структура: {{"code": "...", "name": "...", "unit": "...", "qty1": число/null, "qty2": число/null, "status": "same|changed|added|removed"}}
    3. После JSON напиши краткий отчёт на русском (до 100 слов).
    
    Данные Документа 1:
    {doc1_data}
    
    Данные Документа 2:
    {doc2_data}
    """

    data = {
        "modelUri": f"gpt://{FOLDER_ID}/yandexgpt/latest",
        "completionOptions": {
            "stream": False,
            "temperature": 0.1,
            "maxTokens": "2000"
        },
        "messages": [
            {"role": "user", "text": prompt}
        ]
    }

    try:
        resp = requests.post(url, headers=headers, json=data)
        resp.raise_for_status()
        result = resp.json()['result']['alternatives'][0]['message']['text']
        return result
    except Exception as e:
        return f"Ошибка API: {str(e)}"

col1, col2 = st.columns(2)
with col1:
    file1 = st.file_uploader("Загрузите первую спецификацию (.docx)", type=['docx'])
with col2:
    file2 = st.file_uploader("Загрузите вторую спецификацию (.docx)", type=['docx'])

if file1 and file2:
    with st.spinner('Анализируем таблицы и сравниваем...'):
        text1 = extract_compact_data(file1)
        text2 = extract_compact_data(file2)
        
        if not text1 or not text2:
            st.error("В файлах не найдено таблиц.")
        else:
            raw_response = get_llm_response(text1, text2)
            
            start = raw_response.find('[')
            end = raw_response.rfind(']') + 1
            json_part = []
            report_part = raw_response
            
            if start != -1 and end != -1:
                json_str = raw_response[start:end]
                report_part = raw_response[:start] + raw_response[end:]
                try:
                    json_part = json.loads(json_str)
                except json.JSONDecodeError:
                    st.warning("Не удалось распарсить JSON. Сырой ответ:")
                    st.code(raw_response)
            
            if json_part:
                st.dataframe(json_part)
                import csv
                output = io.StringIO()
                if json_part:
                    writer = csv.DictWriter(output, fieldnames=json_part[0].keys())
                    writer.writeheader()
                    writer.writerows(json_part)
                    csv_data = output.getvalue()
                
                st.download_button("💾 Скачать отчёт (CSV)", csv_data, "report.csv")
            
            st.subheader("📝 Отчёт от ИИ")
            st.markdown(report_part)
else:
    st.info("Загрузите оба файла (.docx) для начала работы.")
