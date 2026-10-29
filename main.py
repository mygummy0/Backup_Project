import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import shutil
import os
import datetime
import threading
import sys
import re
import ctypes # [추가된 부분] 윈도우 작업표시줄 아이콘 설정을 위해 필요

# --- 디자인 설정 (다크모드 & 테마) ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class ModernBackupApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- [추가된 부분] 1. 작업 표시줄 아이콘 분리 (중요!) ---
        # 윈도우가 이 프로그램을 파이썬(Python)이 아니라 '별도의 앱'으로 인식하게 만듭니다.
        myappid = 'mycompany.myproduct.backup.v1' # 임의의 고유 ID
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass # 윈도우가 아니거나 오류가 나면 무시

        # --- 2. 창 크기 설정 ---
        window_width = 950
        window_height = 600
        self.title("자동 백업 프로그램")
        self.resizable(False, False)

        # --- [추가된 부분] 3. 아이콘 설정 (.ico 파일 필요) ---
        # 파일이 같은 폴더에 있어야 합니다. 없으면 에러가 나므로 try-except로 감쌉니다.
        try:
            base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            self.iconbitmap(os.path.join(base_dir, "img", "icon.ico"))
        except Exception as e:
            print(f"아이콘 로드 실패: {e}")

        # --- 4. 화면 중앙 좌표 계산 ---
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        center_x = int((screen_width / 2) - (window_width / 2))
        center_y = int((screen_height / 2) - (window_height / 2))
        self.geometry(f"{window_width}x{window_height}+{center_x}+{center_y}")

        # 데이터 변수
        self.source_dir = tk.StringVar()
        self.target_dir = tk.StringVar()
        self.is_auto_running = False
        self.backup_lock = threading.Lock()  # 이전 백업이 끝나기 전에 다음 백업이 겹쳐 실행되는 것을 방지
        self.next_backup_time = None
        self.keep_map = {"무제한": 0, "최근 3개": 3, "최근 5개": 5, "최근 10개": 10, "최근 30개": 30}
        self.interval_map = {"30초": 30, "1분": 60, "5분": 300, "10분": 600, "30분": 1800, "1시간": 3600}

        # --- 레이아웃 구성 ---
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 왼쪽 사이드바
        self.sidebar_frame = ctk.CTkFrame(self, width=300, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.setup_sidebar()

        # 오른쪽 메인
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.setup_main_area()

    def setup_sidebar(self):
        # 1. 원본 폴더 설정
        ctk.CTkLabel(self.sidebar_frame, text="원본 폴더 (Source)", anchor="w").pack(padx=20, pady=(10, 0), anchor="w")
        self.entry_src = ctk.CTkEntry(self.sidebar_frame, textvariable=self.source_dir, placeholder_text="선택된 폴더 없음")
        self.entry_src.pack(padx=20, pady=5, fill="x")
        
        self.btn_src = ctk.CTkButton(self.sidebar_frame, text="폴더 선택", command=self.select_source, fg_color="#444", hover_color="#555")
        self.btn_src.pack(padx=20, pady=5, fill="x")

        ctk.CTkLabel(self.sidebar_frame, text="", height=10).pack()

        # 2. 저장 폴더 설정
        ctk.CTkLabel(self.sidebar_frame, text="저장 폴더 (Target)", anchor="w").pack(padx=20, pady=(10, 0), anchor="w")
        self.entry_dst = ctk.CTkEntry(self.sidebar_frame, textvariable=self.target_dir, placeholder_text="선택된 폴더 없음")
        self.entry_dst.pack(padx=20, pady=5, fill="x")
        
        self.btn_dst = ctk.CTkButton(self.sidebar_frame, text="폴더 선택", command=self.select_target, fg_color="#444", hover_color="#555")
        self.btn_dst.pack(padx=20, pady=5, fill="x")

        # 3. 주기 설정
        ctk.CTkLabel(self.sidebar_frame, text="백업 주기", anchor="w").pack(padx=20, pady=(30, 0), anchor="w")
        self.option_interval = ctk.CTkOptionMenu(self.sidebar_frame, values=list(self.interval_map.keys()))
        self.option_interval.pack(padx=20, pady=5, fill="x")

        # 3-1. 보관 개수 설정
        ctk.CTkLabel(self.sidebar_frame, text="보관할 백업 개수", anchor="w").pack(padx=20, pady=(20, 0), anchor="w")
        self.option_keep = ctk.CTkOptionMenu(self.sidebar_frame, values=list(self.keep_map.keys()))
        self.option_keep.pack(padx=20, pady=5, fill="x")

        # 4. 시작/중지 버튼
        self.btn_toggle = ctk.CTkButton(self.sidebar_frame, text="자동 백업 시작", command=self.toggle_backup, 
                                        height=50, font=ctk.CTkFont(size=16, weight="bold"),
                                        fg_color="#2CC985", hover_color="#229A65")
        self.btn_toggle.pack(padx=20, pady=(40, 20), fill="x", side="bottom")

        # 5. 타이머 표시
        self.timer_label = ctk.CTkLabel(self.sidebar_frame, text="준비중", font=ctk.CTkFont(size=30, weight="bold"), text_color="#2CC985")
        self.timer_label.pack(side="bottom", pady=10)

    def setup_main_area(self):
        ctk.CTkLabel(self.main_frame, text="실시간 작업 로그", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", pady=(0, 10))
        self.log_textbox = ctk.CTkTextbox(self.main_frame, width=400, corner_radius=10, font=("Consolas", 14))
        self.log_textbox.pack(fill="both", expand=True)
        self.log_textbox.insert("0.0", "시스템이 준비되었습니다.\n설정 후 '자동 백업 시작'을 눌러주세요.\n\n")
        self.log_textbox.configure(state="disabled")

    def set_input_state(self, state):
        self.entry_src.configure(state=state)
        self.btn_src.configure(state=state)
        self.entry_dst.configure(state=state)
        self.btn_dst.configure(state=state)
        self.option_interval.configure(state=state)
        self.option_keep.configure(state=state)

    def log(self, message):
        self.log_textbox.configure(state="normal")
        now = datetime.datetime.now().strftime("[%H:%M:%S]")
        self.log_textbox.insert("end", f"{now} {message}\n")
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    def select_source(self):
        path = filedialog.askdirectory()
        if path:
            self.source_dir.set(path)
            self.log(f"원본 경로 설정됨: {path}")

    def select_target(self):
        path = filedialog.askdirectory()
        if path:
            self.target_dir.set(path)
            self.log(f"저장 경로 설정됨: {path}")

    def toggle_backup(self):
        if self.is_auto_running:
            self.stop_backup()
        else:
            self.start_backup()

    def start_backup(self):
        if not self.source_dir.get() or not self.target_dir.get():
            messagebox.showwarning("누락", "원본 및 저장 폴더를 모두 선택해주세요.")
            return

        error = self.validate_paths(self.source_dir.get(), self.target_dir.get())
        if error:
            messagebox.showwarning("경로 오류", error)
            return

        self.set_input_state("disabled")
        messagebox.showinfo("알림", "자동 백업이 시작되었습니다.\n실행 중에는 설정을 변경할 수 없습니다.")
        
        self.is_auto_running = True
        self.btn_toggle.configure(text="백업 중지 (Stop)", fg_color="#FF5555", hover_color="#CC0000")
        self.timer_label.configure(text_color="#FF5555")
        
        interval_str = self.option_interval.get()
        self.log(f"자동 백업 시작됨 (주기: {interval_str})")
        
        self.run_backup_process()
        self.schedule_next()
        self.update_timer()

    @staticmethod
    def validate_paths(src, dst):
        """폴더 존재 여부와, 저장 폴더가 원본 폴더 안에 있는 경우(무한 복사)를 검사합니다."""
        if not os.path.isdir(src):
            return f"원본 폴더가 존재하지 않습니다:\n{src}"
        if not os.path.isdir(dst):
            return f"저장 폴더가 존재하지 않습니다:\n{dst}"
        real_src, real_dst = os.path.realpath(src), os.path.realpath(dst)
        try:
            inside = os.path.commonpath([real_src, real_dst]) == real_src
        except ValueError:  # 서로 다른 드라이브
            inside = False
        if inside:
            return "저장 폴더는 원본 폴더 안에 있을 수 없습니다.\n(백업이 자기 자신을 계속 복사하게 됩니다)"
        return None

    def stop_backup(self):
        self.is_auto_running = False
        
        self.set_input_state("normal")
        messagebox.showinfo("알림", "자동 백업이 중지되었습니다.\n이제 설정을 변경할 수 있습니다.")

        self.btn_toggle.configure(text="자동 백업 시작", fg_color="#2CC985", hover_color="#229A65")
        self.timer_label.configure(text="Stopped", text_color="gray")
        self.log("자동 백업이 사용자에 의해 중지되었습니다.")

    def schedule_next(self):
        if not self.is_auto_running: return
        interval_sec = self.interval_map[self.option_interval.get()]
        self.next_backup_time = datetime.datetime.now() + datetime.timedelta(seconds=interval_sec)

    def update_timer(self):
        if not self.is_auto_running: return

        remaining = (self.next_backup_time - datetime.datetime.now()).total_seconds()
        
        if remaining > 0:
            m, s = divmod(int(remaining), 60)
            self.timer_label.configure(text=f"{m:02d}:{s:02d}")
            self.after(1000, self.update_timer)
        else:
            self.timer_label.configure(text="✅ 백업 완료")
            self.run_backup_process()
            self.schedule_next()
            self.after(1000, self.update_timer)

    def run_backup_process(self):
        self._keep_choice = self.option_keep.get()
        threading.Thread(target=self._backup_task, daemon=True).start()

    def _backup_task(self):
        if not self.backup_lock.acquire(blocking=False):
            self.after(0, lambda: self.log("⚠ 이전 백업이 아직 진행 중이라 이번 백업은 건너뜁니다."))
            return
        try:
            self._do_backup()
        finally:
            self.backup_lock.release()

    def _prune_old_backups(self, dst, base, keep):
        if keep <= 0:
            return
        pattern = re.compile(re.escape(base) + r"_\d{8}_\d{6}$")
        names = sorted(n for n in os.listdir(dst)
                       if pattern.fullmatch(n) and os.path.isdir(os.path.join(dst, n)))
        for old in names[:-keep]:
            try:
                shutil.rmtree(os.path.join(dst, old))
                self.after(0, lambda o=old: self.log(f"🗑 오래된 백업 삭제: {o}"))
            except Exception as e:
                self.after(0, lambda o=old, err=e: self.log(f"❌ 오래된 백업 삭제 실패: {o} ({err})"))

    def _do_backup(self):
        src = self.source_dir.get()
        dst = self.target_dir.get()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        target_path = os.path.join(dst, f"{os.path.basename(src)}_{timestamp}")

        try:
            # 1️⃣ 폴더 복사
            shutil.copytree(src, target_path)

            # 2️⃣ 타겟 폴더 전체 용량 계산
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(dst):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    try:
                        total_size += os.path.getsize(fp)
                    except Exception:
                        pass

            # 3️⃣ 사람이 읽기 좋은 단위로 변환
            def readable_size(size_bytes):
                for unit in ['B','KB','MB','GB','TB']:
                    if size_bytes < 1024:
                        return f"{size_bytes:.1f} {unit}"
                    size_bytes /= 1024
                return f"{size_bytes:.1f} PB"

            size_str = readable_size(total_size)

            # 4️⃣ 로그 출력
            self.after(0, lambda: self.log(f"✅ 백업 완료: {os.path.basename(target_path)} (폴더 용량: {size_str})"))

            self._prune_old_backups(dst, os.path.basename(src), self.keep_map[self._keep_choice])

        except Exception as e:
            self.after(0, lambda err=e: self.log(f"❌ 오류 발생: {err}"))


if __name__ == "__main__":
    app = ModernBackupApp()
    app.mainloop()