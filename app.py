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
st.set_page_config(page_title="船舶軌跡下載神器", page_icon="🚢", layout="wide")

st.title("🚢 船舶軌跡資料批次下載")
st.markdown("輸入 MMSI 與日期，系統將自動抓取 MarineTraffic 資料並打包下載。")

# --- 側邊欄設定 (輸入區) ---
with st.sidebar:
    st.header("⚙️ 參數設定")
    
    api_key = st.text_input("MarineTraffic API Key", type="password", help="請輸入您的 API 金鑰")
    
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("開始日期", value=parse_date("2023-01-01"))
    with col2:
        end_date = st.date_input("結束日期", value=parse_date("2023-01-05"))
        
    sleep_sec = st.number_input("每艘船間隔 (秒)", min_value=1, value=60, help="避免請求太快被封鎖，建議 60 秒")
    
    st.info("💡 提示：因為有設定冷卻時間，請耐心等候倒數結束。")

# --- 主要內容區 ---
col_input, col_status = st.columns([1, 2])

with col_input:
    st.subheader("📋 1. 輸入清單")
    mmsi_input = st.text_area("請輸入 MMSI (一行一艘)", height=200, placeholder="416123456\n416987654")
    btn_start = st.button("🚀 開始下載", use_container_width=True)

with col_status:
    st.subheader("📊 2. 執行狀態")
    # 這裡放佔位符，之後會動態更新
    status_container = st.container()
    
    with status_container:
        # 預設顯示的空狀態
        st.info("👈 請在左側輸入資料並按下開始...")
        
# --- 核心邏輯 ---
async def process_download(api_key, mmsi_list, start_dt, end_dt, sleep_sec, status_placeholders):
    temp_dir = "./temp_web"
    results = [] 
    
    # 解包佔位符
    main_status = status_placeholders['main']
    progress_bar = status_placeholders['bar']
    log_area = status_placeholders['log']
    
    total = len(mmsi_list)
    logs = [] # 儲存歷史訊息
    
    progress_bar.progress(0, text="準備開始...")

    for index, mmsi in enumerate(mmsi_list):
        current_num = index + 1
        
        # 1. 更新大標題：正在下載
        main_status.markdown(f"""
        ### 🚀 正在處理第 {current_num}/{total} 艘
        **MMSI:** `{mmsi}`  
        **狀態:** 📥 向 MarineTraffic 請求資料中...
        """)
        
        # 記錄 Log
        logs.append(f"[{time.strftime('%H:%M:%S')}] 開始下載 MMSI: {mmsi}")
        log_area.text_area("詳細執行紀錄", "\n".join(logs[::-1]), height=200) # 反向顯示，最新的在上面

        # 重試機制
        max_retries = 2
        success = False
        
        for attempt in range(1, max_retries + 1):
            try:
                res = await download_vessel_track_data(api_key, mmsi, start_dt, end_dt, temp_dir)
                
                if res:
                    # 模擬合併檔案邏輯 (簡化版)
                    output_dir = get_output_dir_path(mmsi, temp_dir)
                    if os.path.exists(output_dir):
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
                        
                        logs.append(f"[{time.strftime('%H:%M:%S')}] ✅ 成功下載！")
                        success = True
                        break # 成功就跳出重試迴圈
                        
            except Exception as e:
                 logs.append(f"[{time.strftime('%H:%M:%S')}] ❌ 錯誤: {e}")
            
            # 失敗重試的冷卻
            if not success and attempt < max_retries:
                logs.append(f"[{time.strftime('%H:%M:%S')}] ⚠️ 下載失敗，進入重試冷卻 (120秒)...")
                for i in range(120, 0, -1):
                    main_status.markdown(f"""
                    ### ⚠️ 暫時受阻，準備重試
                    **MMSI:** `{mmsi}`  
                    **狀態:** ❄️ 冷卻中，剩餘 **{i}** 秒...
                    """)
                    time.sleep(1)
                logs.append(f"[{time.strftime('%H:%M:%S')}] 🔄 重試中...")

        # 更新進度條
        progress_bar.progress(current_num / total, text=f"進度：{current_num} / {total}")
        log_area.text_area("詳細執行紀錄", "\n".join(logs[::-1]), height=200)

        # 2. 成功後的休息時間 (除了最後一艘)
        if current_num < total:
            if success:
                # 倒數計時顯示
                for i in range(sleep_sec, 0, -1):
                    main_status.markdown(f"""
                    ### ☕ 休息一下 (防封鎖機制)
                    **上一艘:** `{mmsi}` (成功)  
                    **下一艘:** `{mmsi_list[index+1]}`  
                    **狀態:** ⏳ 倒數 **{i}** 秒後繼續...
                    """)
                    # 更新顏色條讓它看起來在動
                    progress_bar.progress(current_num / total, text=f"等待冷卻中... {i}s")
                    time.sleep(1)
            else:
                logs.append(f"[{time.strftime('%H:%M:%S')}] ❌ 放棄此艘，繼續下一艘")
    
    # 全部完成
    main_status.markdown(f"""
    ### 🎉 全部完成！
    共成功下載 **{len(results)}** 艘船隻資料。
    """)
    progress_bar.progress(1.0, text="執行結束")
    
    return results

# --- 按鈕觸發 ---
if btn_start:
    if not api_key:
        st.error("請在左側輸入 API Key")
    elif not mmsi_input.strip():
        st.error("請輸入 MMSI")
    else:
        mmsi_list = [x.strip() for x in mmsi_input.split('\n') if x.strip()]
        
        # 清空右側狀態區，準備放入動態元件
        with status_container:
            st.empty() # 清除原本的提示文字
            
            # 建立三個固定位置的元件，之後只更新這三個，不會一直往下長
            ph_main = st.empty()    # 放大大標題
            ph_bar = st.progress(0) # 放進度條
            st.write("---")         # 分隔線
            ph_log = st.empty()     # 放滾動日誌
            
            # 打包給函數用
            placeholders = {
                'main': ph_main,
                'bar': ph_bar,
                'log': ph_log
            }
        
        # 執行
        results = asyncio.run(process_download(api_key, mmsi_list, start_date, end_date, sleep_sec, placeholders))
        
        if results:
            st.success("檔案打包完成！請點擊下方按鈕下載。")
            
            # 打包 ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                for item in results:
                    zf.writestr(item["filename"], item["data"])
            
            st.download_button(
                label="📥 下載 ZIP 壓縮檔",
                data=zip_buffer.getvalue(),
                file_name="vessel_tracks.zip",
                mime="application/zip",
                use_container_width=True
            )
        else:
            st.warning("沒有成功下載任何資料。")