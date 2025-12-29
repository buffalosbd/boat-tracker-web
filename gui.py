import tkinter as tk
from tkinter import messagebox, scrolledtext
from tkinter import ttk
import asyncio
import threading
import os
import shutil
import csv
import time  # 引入時間模組
from dotenv import load_dotenv
from date_utils import parse_date
# 引用原本的模組
from download_api import download_vessel_track_data
from path_utils import get_output_dir_path, final_result_dir_path

# 載入 .env
load_dotenv()

class VesselApp:
    def __init__(self, root):
        self.root = root
        self.root.title("船舶資料批次下載器 (防封鎖版)")
        self.root.geometry("600x700")  # 視窗大小
        
        # --- 樣式設定 ---
        style = ttk.Style()
        style.configure("TButton", font=("Microsoft JhengHei", 12))
        style.configure("TLabel", font=("Microsoft JhengHei", 10))

        # --- 1. API Key ---
        self.lbl_api = ttk.Label(root, text="MarineTraffic API Key:")
        self.lbl_api.pack(pady=(15, 5), padx=20, anchor="w")
        
        self.entry_api = ttk.Entry(root, width=50)
        self.entry_api.pack(pady=0, padx=20, fill="x")
        default_key = os.getenv("MARINE_TRAFFIC_API_KEY", "")
        self.entry_api.insert(0, default_key)

        # --- 2. MMSI (多行輸入) ---
        self.lbl_mmsi = ttk.Label(root, text="MMSI 清單 (請一行輸入一艘):")
        self.lbl_mmsi.pack(pady=(15, 5), padx=20, anchor="w")
        
        # 使用 ScrolledText 讓使用者可以貼很多行
        self.txt_mmsi = scrolledtext.ScrolledText(root, height=6, font=("Consolas", 10))
        self.txt_mmsi.pack(pady=0, padx=20, fill="x")

        # --- 3. 日期與間隔設定區塊 ---
        frame_settings = ttk.Frame(root)
        frame_settings.pack(pady=15, padx=20, fill="x")

        # 開始日期
        self.lbl_start = ttk.Label(frame_settings, text="開始日期:")
        self.lbl_start.grid(row=0, column=0, sticky="w")
        self.entry_start = ttk.Entry(frame_settings, width=15)
        self.entry_start.grid(row=1, column=0, sticky="w", padx=(0, 10))
        self.entry_start.insert(0, "2023-01-01") 

        # 結束日期
        self.lbl_end = ttk.Label(frame_settings, text="結束日期:")
        self.lbl_end.grid(row=0, column=1, sticky="w")
        self.entry_end = ttk.Entry(frame_settings, width=15)
        self.entry_end.grid(row=1, column=1, sticky="w", padx=(0, 10))
        self.entry_end.insert(0, "2023-01-05") 

        # 間隔秒數 (Sleep)
        self.lbl_sleep = ttk.Label(frame_settings, text="每艘間隔(秒):")
        self.lbl_sleep.grid(row=0, column=2, sticky="w")
        self.entry_sleep = ttk.Entry(frame_settings, width=10)
        self.entry_sleep.grid(row=1, column=2, sticky="w")
        # --- 修改處：預設改為 60 秒 ---
        self.entry_sleep.insert(0, "60") 

        # --- 4. 執行按鈕 ---
        self.btn_run = ttk.Button(root, text="開始批次下載", command=self.start_thread)
        self.btn_run.pack(pady=15, ipadx=20, ipady=5)

        # --- 5. 進度條 ---
        self.progress = ttk.Progressbar(root, mode='indeterminate')
        self.progress.pack(pady=(0, 10), padx=20, fill="x")

        # --- 6. 狀態顯示區 ---
        self.log_area = scrolledtext.ScrolledText(root, height=12, state='disabled', font=("Consolas", 9))
        self.log_area.pack(pady=(0, 20), padx=20, fill="both", expand=True)

    def log(self, message):
        """將訊息寫入下方文字框，並自動捲動到底部"""
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')

    def start_thread(self):
        """準備資料並啟動執行緒"""
        api_key = self.entry_api.get().strip()
        
        # 取得多行 MMSI
        raw_mmsi = self.txt_mmsi.get("1.0", tk.END)
        mmsi_list = [line.strip() for line in raw_mmsi.split('\n') if line.strip()]

        start_date = self.entry_start.get().strip()
        end_date = self.entry_end.get().strip()
        sleep_sec = self.entry_sleep.get().strip()

        if not api_key:
            messagebox.showwarning("警告", "請輸入 API Key！")
            return
        
        if not mmsi_list:
            messagebox.showwarning("警告", "請至少輸入一組 MMSI！")
            return

        if not sleep_sec.isdigit():
            messagebox.showwarning("警告", "間隔秒數請輸入數字！")
            return

        # 鎖定介面
        self.btn_run.config(state='disabled', text="排程處理中...")
        self.progress.start(10)
        self.log(">>> 任務開始...")
        self.log(f"共計 {len(mmsi_list)} 艘船，每艘間隔 {sleep_sec} 秒。")

        # 開新執行緒
        threading.Thread(target=self.run_process, args=(api_key, mmsi_list, start_date, end_date, int(sleep_sec)), daemon=True).start()

    def run_process(self, api_key, mmsi_list, from_date, to_date, sleep_sec):
        """批次處理邏輯"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            start_dt = parse_date(from_date)
            end_dt = parse_date(to_date)
            temp_dir = "./temp"
            results_dir = "./results"

            success_count = 0
            fail_count = 0

            # --- 迴圈開始 ---
            for index, mmsi in enumerate(mmsi_list):
                current_num = index + 1
                total = len(mmsi_list)
                
                self.log(f"----------------------------------------")
                self.log(f"[{current_num}/{total}] 正在處理 MMSI: {mmsi}")
                
                try:
                    res = loop.run_until_complete(download_vessel_track_data(
                        api_key=api_key,
                        mmsi=mmsi,
                        start_date=start_dt,
                        end_date=end_dt,
                        temp_dir=temp_dir
                    ))

                    if not res:
                        self.log(f"⚠️ MMSI {mmsi} 下載失敗或無資料。")
                        fail_count += 1
                    else:
                        self.log(f"正在合併檔案...")
                        self.combine_files(mmsi, temp_dir, results_dir)
                        self.log(f"✅ MMSI {mmsi} 完成。")
                        success_count += 1
                
                except Exception as inner_e:
                    self.log(f"❌ MMSI {mmsi} 發生錯誤: {str(inner_e)}")
                    fail_count += 1
                
                # --- 休息時間 ---
                if current_num < total: # 如果不是最後一艘，就休息
                    self.log(f"⏳ 休息 {sleep_sec} 秒後繼續...")
                    time.sleep(sleep_sec)
            
            # --- 迴圈結束 ---
            self.log(f"========================================")
            self.log(f"所有任務結束。")
            self.log(f"成功: {success_count} / 失敗: {fail_count}")
            
            messagebox.showinfo("完成", f"批次處理結束！\n成功: {success_count}\n失敗: {fail_count}")

        except Exception as e:
            self.log(f"❌ 系統發生嚴重錯誤: {str(e)}")
            messagebox.showerror("錯誤", f"系統錯誤:\n{str(e)}")
        finally:
            self.root.after(0, self.reset_ui)

    def reset_ui(self):
        self.progress.stop()
        self.btn_run.config(state='normal', text="開始批次下載")

    def combine_files(self, mmsi, temp_dir, results_dir):
        """合併檔案邏輯"""
        output_dir = get_output_dir_path(mmsi=mmsi, temp_dir=temp_dir)
        
        if not os.path.exists(output_dir):
            return

        final_result_dir = final_result_dir_path(mmsi=mmsi, results_dir=results_dir)
        if os.path.exists(final_result_dir):
            shutil.rmtree(final_result_dir)
        os.makedirs(final_result_dir, exist_ok=True)

        combined_file_path = f"{final_result_dir}/vessel_track_{mmsi}_combined.csv"
        csv_files = [f for f in os.listdir(output_dir) if f.endswith(".csv")]
        csv_files.sort()

        header_saved = False
        with open(combined_file_path, "w", newline="", encoding="utf-8") as outfile:
            writer = None
            for filename in csv_files:
                file_path = os.path.join(output_dir, filename)
                with open(file_path, "r", newline="", encoding="utf-8") as infile:
                    reader = csv.reader(infile)
                    try:
                        header = next(reader)
                        if not header_saved:
                            writer = csv.writer(outfile)
                            writer.writerow(header)
                            header_saved = True
                        for row in reader:
                            writer.writerow(row)
                    except StopIteration:
                        continue

if __name__ == "__main__":
    root = tk.Tk()
    app = VesselApp(root)
    root.mainloop()