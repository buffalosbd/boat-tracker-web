import streamlit as st
import asyncio
import os
import csv
import time
import zipfile
import io
from date_utils import parse_date
from download_api import download_vessel_track_data
from path_utils import get_output_dir_path

# --- 網頁設定 ---
st.set_page_config(page_title="船舶軌跡下載神器", page_icon="🚢")

st.title("🚢 船舶軌跡資料批次下載")
st.markdown("輸入 MMSI 與日期，系統將自動抓取 MarineTraffic 資料並打包下載。")

# --- 側邊欄設定 (輸入區) ---
with st.sidebar:
    st.header("⚙️ 參數設定")
    
    # API Key 輸入 (設為密碼格式，隱藏起來)
    api_key = st.text_input("MarineTraffic API Key", type="password", help="請輸入您的 API 金鑰")
    
    # 日期選擇
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("開始日期", value=parse_date("2023-01-01"))
    with col2:
        end_date = st.date_input("結束日期", value=parse_date("2023-01-05"))
        
    # 間隔設定
    sleep_sec = st.number_input("每艘船間隔 (秒)", min_value=1, value=30, help="避免請求太快被封鎖，建議 30 秒以上")
    
    st.info("💡 建議：大量下載時請耐心等候，切勿關閉視窗。")

# --- 主要內容區 ---
st.subheader("📋 MMSI 清單")
mmsi_input = st.text_area("請輸入 MMSI (一行一艘)", height=150, placeholder="416123456\n416987654")

# --- 下載邏輯 ---
async def process_download(api_key, mmsi_list, start_dt, end_dt, sleep_sec, log_container):
    temp_dir = "./temp_web"
    results = [] # 存放生成的 CSV 內容
    
    # 進度條
    progress_bar = st.progress(0)
    
    for index, mmsi in enumerate(mmsi_list):
        current_num = index + 1
        total = len(mmsi_list)
        
        log_container.write(f"⏳ [{current_num}/{total}] 正在處理 MMSI: {mmsi} ...")
        
        # 重試機制
        max_retries = 2
        success = False
        
        for attempt in range(1, max_retries + 1):
            try:
                # 這裡要稍微改寫 download_api 以適應 stream (或直接存暫存檔)
                # 為了簡單，我們先存本機暫存，再讀取
                res = await download_vessel_track_data(api_key, mmsi, start_dt, end_dt, temp_dir)
                
                if res:
                    # 讀取剛剛下載並合併好的檔案 (需自行實作合併邏輯或是簡化)
                    # 這裡簡化邏輯：假設 download_api 會產出片段，我們需要合併
                    # 為了網頁版效率，建議直接回傳數據，但若沿用舊架構：
                    output_dir = get_output_dir_path(mmsi, temp_dir)
                    if os.path.exists(output_dir):
                        # 合併記憶體中的 CSV
                        csv_buffer = io.StringIO()
                        writer = None
                        all_files = sorted([f for f in os.listdir(output_dir) if f.endswith(".csv")])
                        
                        header_saved = False
                        for f in all_files:
                            with open(os.path.join(output_dir, f), "r", encoding="utf-8") as infile:
                                reader = csv.reader(infile)
                                try:
                                    header = next(reader)
                                    if not header_saved:
                                        writer = csv.writer(csv_buffer)
                                        writer.writerow(header)
                                        header_saved = True
                                    for row in reader:
                                        writer.writerow(row)
                                except StopIteration:
                                    pass
                        
                        results.append({"filename": f"vessel_{mmsi}.csv", "data": csv_buffer.getvalue()})
                        log_container.write(f"✅ {mmsi} 下載成功！")
                        success = True
                        break
            except Exception as e:
                 log_container.error(f"❌ {mmsi} 錯誤: {e}")
            
            if not success and attempt < max_retries:
                log_container.warning(f"❄️ 冷卻中 (120s)...")
                time.sleep(120)

        # 更新進度條
        progress_bar.progress(current_num / total)

        # 間隔休息
        if current_num < total and success:
             time.sleep(sleep_sec)
    
    return results

# --- 按鈕觸發 ---
if st.button("🚀 開始下載"):
    if not api_key:
        st.error("請輸入 API Key")
    elif not mmsi_input.strip():
        st.error("請輸入 MMSI")
    else:
        mmsi_list = [x.strip() for x in mmsi_input.split('\n') if x.strip()]
        
        log_box = st.empty() # 建立一個空容器放 Log
        
        # 執行異步任務
        results = asyncio.run(process_download(api_key, mmsi_list, start_date, end_date, sleep_sec, log_box))
        
        if results:
            st.success(f"🎉 處理完成！共成功 {len(results)} 艘。")
            
            # 打包成 ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                for item in results:
                    zf.writestr(item["filename"], item["data"])
            
            st.download_button(
                label="📥 下載 ZIP 壓縮檔",
                data=zip_buffer.getvalue(),
                file_name="vessel_tracks.zip",
                mime="application/zip"
            )
        else:
            st.warning("沒有成功下載任何資料。")