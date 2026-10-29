# Design System v1.0 Applied
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog
from tkinter import font as tkfont
import os
import datetime
import queue
import threading
import time
import sys
import ctypes  # 윈도우 작업표시줄 아이콘 설정을 위해 필요

import backup_core as core
import design_tokens as dt

SP = dt.SPACE


def detect_theme():
    """OS 설정을 따른다. BACKUP_THEME=light|dark 로 강제할 수 있다."""
    forced = os.environ.get("BACKUP_THEME", "").lower()
    if forced in dt.THEMES:
        return forced
    ctk.set_appearance_mode("System")
    return "dark" if ctk.get_appearance_mode() == "Dark" else "light"


THEME = detect_theme()
ctk.set_appearance_mode(THEME.capitalize())
C = dt.theme_colors(THEME)  # role -> hex


def animate(widget, key, apply, start, end):
    """색상 전환: duration-200, cubic-bezier(0.16, 1, 0.3, 1). 같은 key의 진행 중인 전환은 취소한다."""
    ids = widget.__dict__.setdefault("_anim_ids", {})
    if key in ids:
        try:
            widget.after_cancel(ids.pop(key))
        except tk.TclError:
            pass
    t0 = time.monotonic()

    def step():
        t = (time.monotonic() - t0) * 1000 / dt.DURATION_MS
        try:
            apply(dt.lerp_color(start, end, dt.ease_out(min(t, 1.0))))
            if t < 1:
                ids[key] = widget.after(16, step)
            else:
                ids.pop(key, None)
        except tk.TclError:  # 위젯이 이미 파괴됨
            ids.pop(key, None)

    step()


class Button(ctk.CTkButton):
    """primary / secondary. hover, active(pressed), disabled 상태를 모두 구현한다."""
    STYLES = {
        "primary": dict(base="primary", hover="primary_hover", active="primary_active", text="on_primary",
                        border="primary", off_bg="off_bg", off_text="off_text", off_border="off_bg",
                        ring="ring_on_primary"),
        "secondary": dict(base="secondary", hover="secondary_hover", active="secondary_active", text="text",
                          border="border", off_bg="off_surface", off_text="off_text", off_border="border",
                          ring="ring"),
    }

    def __init__(self, master, text, command, font, variant="secondary", width=dt.CONTROL_HEIGHT * 2):
        st = self.STYLES[variant]
        super().__init__(master, text=text, command=command, font=font, width=width, height=dt.CONTROL_HEIGHT,
                         corner_radius=dt.RADIUS_CONTROL, border_width=dt.BORDER, hover=False,
                         fg_color=C[st["base"]], border_color=C[st["border"]],
                         text_color=C[st["text"]], text_color_disabled=C[st["off_text"]])
        self._variant, self._current, self._inside, self._enabled = variant, C[st["base"]], False, True
        self._focused = False
        # 키보드 접근: Tab으로 포커스를 받고 Space/Enter로 누른다. 마우스 클릭은 포커스를 옮기지 않으므로
        # 포커스 링은 키보드로 이동했을 때만 나타난다 (focus-visible).
        self._canvas.configure(takefocus=1)
        self._canvas.bind("<FocusIn>", lambda e: self._focus(True), add="+")
        self._canvas.bind("<FocusOut>", lambda e: self._focus(False), add="+")
        self._canvas.bind("<space>", lambda e: self.invoke(), add="+")
        self._canvas.bind("<Return>", lambda e: self.invoke(), add="+")
        self.bind("<Enter>", lambda e: self._enter(), add="+")
        self.bind("<Leave>", lambda e: self._leave(), add="+")
        self.bind("<ButtonPress-1>", lambda e: self._go("active"), add="+")
        self.bind("<ButtonRelease-1>", lambda e: self._go("hover" if self._inside else "base"), add="+")

    def _paint(self, color):
        self._current = color
        self.configure(fg_color=color)

    def _focus(self, on):
        self._focused = on and self._enabled
        self._apply_border()

    def _apply_border(self):
        st = self.STYLES[self._variant]
        if self._focused:
            self.configure(border_width=dt.FOCUS_BORDER, border_color=C[st["ring"]])
        else:
            self.configure(border_width=dt.BORDER,
                           border_color=C[st["border"] if self._enabled else st["off_border"]])

    def _go(self, key):
        if self._enabled:
            animate(self, "bg", self._paint, self._current, C[self.STYLES[self._variant][key]])

    def _enter(self):
        self._inside = True
        self._go("hover")

    def _leave(self):
        self._inside = False
        self._go("base")

    def set_variant(self, variant, text):
        st = self.STYLES[variant]
        self._variant = variant
        self.configure(text=text, text_color=C[st["text"]], text_color_disabled=C[st["off_text"]])
        self._apply_border()
        self._go("hover" if self._inside else "base")

    def set_enabled(self, enabled):
        st = self.STYLES[self._variant]
        self._enabled = enabled
        self._canvas.configure(takefocus=1 if enabled else 0)
        self.configure(state="normal" if enabled else "disabled")
        self._focused = self._focused and enabled
        self._apply_border()
        self._paint(C[st["base" if enabled else "off_bg"]])


class Field(ctk.CTkEntry):
    """입력창. focus 시 brand 테두리(2px)로 전환, disabled 시 배경/글자색 변경."""

    def __init__(self, master, variable, placeholder, font):
        super().__init__(master, textvariable=variable, placeholder_text=placeholder, font=font,
                         height=dt.CONTROL_HEIGHT, corner_radius=dt.RADIUS_CONTROL, border_width=dt.BORDER,
                         fg_color=C["field"], border_color=C["border"], text_color=C["text"],
                         placeholder_text_color=C["text_sub"])
        self._border = C["border"]
        self._invalid, self._focused = False, False
        self.bind("<FocusIn>", lambda e: self._focus(True), add="+")
        self.bind("<FocusOut>", lambda e: self._focus(False), add="+")

    def _paint(self, color):
        self._border = color
        self.configure(border_color=color)

    def _rest_color(self):
        return C["error" if self._invalid else "border"]

    def _focus(self, on):
        self._focused = on
        self.configure(border_width=dt.FOCUS_BORDER if on else dt.BORDER)
        animate(self, "border", self._paint, self._border, C["ring"] if on else self._rest_color())

    def set_invalid(self, invalid):
        """검증 실패를 컨트롤 자체에 표시한다 (테두리 색 + 문구는 폼 아래)."""
        self._invalid = invalid
        if not self._focused:
            animate(self, "border", self._paint, self._border, self._rest_color())

    def set_enabled(self, enabled):
        if not enabled:  # 포커스 링 초기화
            self._focused = False
            self.configure(border_width=dt.BORDER)
            self._paint(self._rest_color())
        self.configure(state="normal" if enabled else "disabled",
                       fg_color=C["field" if enabled else "off_surface"],
                       text_color=C["text" if enabled else "off_text"])


class Select(ctk.CTkFrame):
    """테두리가 있는 드롭다운 (OptionMenu는 border를 지원하지 않아 Frame으로 감싼다)."""

    def __init__(self, master, values, font):
        super().__init__(master, height=dt.CONTROL_HEIGHT, corner_radius=dt.RADIUS_CONTROL,
                         border_width=dt.BORDER, border_color=C["border"], fg_color=C["field"])
        self.menu = ctk.CTkOptionMenu(
            self, values=values, font=font, dropdown_font=font, anchor="w",
            height=dt.CONTROL_HEIGHT - 2 * dt.BORDER, corner_radius=dt.RADIUS_CONTROL - dt.BORDER,
            fg_color=C["field"], button_color=C["field"], button_hover_color=C["secondary_hover"],
            text_color=C["text"], text_color_disabled=C["off_text"],
            dropdown_fg_color=C["card"], dropdown_hover_color=C["menu_hover"], dropdown_text_color=C["text"])
        self.menu.pack(fill="x", padx=dt.BORDER, pady=dt.BORDER)

    def get(self):
        return self.menu.get()

    def set(self, value):
        self.menu.set(value)

    def set_enabled(self, enabled):
        bg = C["field" if enabled else "off_surface"]
        self.configure(fg_color=bg)
        self.menu.configure(state="normal" if enabled else "disabled", fg_color=bg, button_color=bg)


class ModernBackupApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # 윈도우가 이 프로그램을 파이썬이 아니라 '별도의 앱'으로 인식하게 만든다 (작업 표시줄 아이콘 분리)
        myappid = 'mycompany.myproduct.backup.v1'
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass  # 윈도우가 아니거나 오류가 나면 무시

        window_width = 640
        window_height = min(800, self.winfo_screenheight() - SP["16"] - 2 * SP["4"])
        self.title("자동 백업")
        self.resizable(False, True)  # 세로로 늘리면 작업 기록이 넓어진다
        self.minsize(window_width, 640)
        self.configure(fg_color=C["page"])

        try:
            base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            self.iconbitmap(os.path.join(base_dir, "img", "icon.ico"))
        except Exception as e:
            print(f"아이콘 로드 실패: {e}")

        center_x = int((self.winfo_screenwidth() - window_width) / 2)
        center_y = int((self.winfo_screenheight() - window_height) / 2)
        self.geometry(f"{window_width}x{window_height}+{center_x}+{center_y}")

        self.source_dir = tk.StringVar()
        self.target_dir = tk.StringVar()
        self.is_auto_running = False
        self.backup_lock = threading.Lock()  # 이전 백업이 끝나기 전에 다음 백업이 겹쳐 실행되는 것을 방지
        self.next_backup_time = None
        self.keep_map = {"무제한": 0, "최근 3개": 3, "최근 5개": 5, "최근 10개": 10, "최근 30개": 30}
        self.interval_map = {"30초": 30, "1분": 60, "5분": 300, "10분": 600, "30분": 1800, "1시간": 3600}

        families = set(tkfont.families(self))
        family = next((f for f in dt.FONT_CANDIDATES if f in families), None)
        self.fonts = {role: ctk.CTkFont(family=family, size=px, weight=weight)
                      for role, (px, weight) in dt.TYPE.items()}

        self.current_cancel = None  # 진행 중인 백업을 취소하는 이벤트
        self.ui_queue = queue.Queue()  # 백업 스레드 -> 메인 스레드 (tkinter는 스레드 안전하지 않다)
        self.build_layout()
        for var in (self.source_dir, self.target_dir):
            var.trace_add("write", lambda *a: self.clear_error())
        self.drain_ui_queue()

    # ---- layout ---------------------------------------------------------------------
    def label(self, parent, text, role, color="text"):
        return ctk.CTkLabel(parent, text=text, font=self.fonts[role], text_color=C[color], anchor="w")

    def card(self, row, **grid):
        frame = ctk.CTkFrame(self, corner_radius=dt.RADIUS_CARD, border_width=dt.BORDER,
                             border_color=C["border"], fg_color=C["card"])
        frame.grid(row=row, column=0, sticky="nsew", padx=SP["6"], **grid)
        return frame

    def build_layout(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        pad, gap = SP["6"], SP["4"]

        # 헤더
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=pad, pady=(pad, gap))
        header.grid_columnconfigure(0, weight=1)
        self.label(header, "자동 백업", "h1").grid(row=0, column=0, sticky="w")

        # 설정 카드
        form = self.card(1, pady=(0, gap))
        form.grid_columnconfigure(0, weight=1)
        inner = ctk.CTkFrame(form, fg_color="transparent")
        inner.pack(fill="x", padx=pad, pady=pad)
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_columnconfigure(1, weight=1)

        self.label(inner, "원본 폴더", "caption", "text_sub").grid(row=0, column=0, columnspan=2, sticky="w")
        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(SP["2"], gap))
        row.grid_columnconfigure(0, weight=1)
        self.entry_src = Field(row, self.source_dir, "백업할 폴더를 선택하세요", self.fonts["body"])
        self.entry_src.grid(row=0, column=0, sticky="ew")
        self.btn_src = Button(row, "선택", self.select_source, self.fonts["body"])
        self.btn_src.grid(row=0, column=1, padx=(SP["2"], 0))

        self.label(inner, "저장 폴더", "caption", "text_sub").grid(row=2, column=0, columnspan=2, sticky="w")
        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(SP["2"], gap))
        row.grid_columnconfigure(0, weight=1)
        self.entry_dst = Field(row, self.target_dir, "백업을 저장할 폴더를 선택하세요", self.fonts["body"])
        self.entry_dst.grid(row=0, column=0, sticky="ew")
        self.btn_dst = Button(row, "선택", self.select_target, self.fonts["body"])
        self.btn_dst.grid(row=0, column=1, padx=(SP["2"], 0))

        self.label(inner, "백업 주기", "caption", "text_sub").grid(row=4, column=0, sticky="w")
        self.label(inner, "보관할 개수", "caption", "text_sub").grid(row=4, column=1, sticky="w", padx=(gap, 0))
        self.option_interval = Select(inner, list(self.interval_map.keys()), self.fonts["body"])
        self.option_interval.set("5분")
        self.option_interval.grid(row=5, column=0, sticky="ew", pady=(SP["2"], 0))
        self.option_keep = Select(inner, list(self.keep_map.keys()), self.fonts["body"])
        self.option_keep.grid(row=5, column=1, sticky="ew", padx=(gap, 0), pady=(SP["2"], 0))

        self.error_label = ctk.CTkLabel(inner, text="", height=SP["4"], font=self.fonts["caption"],
                                        text_color=C["error"], anchor="w")
        self.error_label.grid(row=6, column=0, columnspan=2, sticky="w", pady=(SP["2"], 0))

        # 실행 카드: 타이머 + 시작/중지 + 진행 표시
        control = self.card(2, pady=(0, gap))
        control.grid_columnconfigure(0, weight=1)
        left = ctk.CTkFrame(control, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w", padx=pad, pady=pad)
        self.label(left, "다음 백업까지", "caption", "text_sub").pack(anchor="w")
        self.timer_label = self.label(left, "--:--", "display1", "text_sub")
        self.timer_label.pack(anchor="w")
        self.btn_toggle = Button(control, "시작", self.toggle_backup, self.fonts["body"], variant="primary",
                                 width=SP["16"] * 2)
        self.btn_toggle.grid(row=0, column=1, padx=pad)
        self.progress = ctk.CTkProgressBar(control, mode="determinate", height=SP["1"], corner_radius=SP["1"] // 2,
                                           fg_color=C["track"], progress_color=C["track"])
        self.progress.set(0)
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew", padx=pad, pady=(0, pad))

        # 기록 카드
        history = self.card(3, pady=(0, pad))
        history.grid_columnconfigure(0, weight=1)
        history.grid_rowconfigure(1, weight=1)
        self.label(history, "작업 기록", "h2").grid(row=0, column=0, sticky="w", padx=pad, pady=(pad, gap))
        wrap = ctk.CTkFrame(history, corner_radius=dt.RADIUS_CONTROL, fg_color=C["log_bg"])
        wrap.grid(row=1, column=0, sticky="nsew", padx=pad, pady=(0, pad))
        self.log_textbox = ctk.CTkTextbox(wrap, fg_color="transparent", text_color=C["text"],
                                          font=self.fonts["body"], border_width=0, wrap="word",
                                          scrollbar_button_color=C["border"],
                                          scrollbar_button_hover_color=C["text_sub"])
        self.log_textbox.pack(fill="both", expand=True, padx=SP["2"], pady=SP["2"])
        self.log_textbox.tag_config("ts", foreground=C["text_sub"])
        self.log_textbox.tag_config("success", foreground=C["success"])
        self.log_textbox.tag_config("error", foreground=C["error"])
        self.log_textbox.tag_config("warn", foreground=C["warn"])
        self.log_textbox.configure(state="disabled")


    def post(self, fn, *args):
        """백업 스레드에서 UI 작업을 예약한다. 실제 실행은 메인 스레드가 한다."""
        self.ui_queue.put((fn, args))

    def drain_ui_queue(self):
        try:
            while True:
                fn, args = self.ui_queue.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.after(50, self.drain_ui_queue)

    # ---- view helpers ---------------------------------------------------------------
    def set_input_state(self, state):
        enabled = state == "normal"
        for widget in (self.entry_src, self.btn_src, self.entry_dst, self.btn_dst,
                       self.option_interval, self.option_keep):
            widget.set_enabled(enabled)

    def show_error(self, message):
        self.error_label.configure(text=message)

    def clear_error(self):
        self.error_label.configure(text="")
        self.entry_src.set_invalid(False)
        self.entry_dst.set_invalid(False)

    def set_busy(self, busy):
        if busy:  # 대기 중에는 진행 색을 트랙과 같게 해서 보이지 않게 한다
            self.progress.configure(mode="indeterminate", progress_color=C["primary"])
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate", progress_color=C["track"])
            self.progress.set(0)

    @staticmethod
    def level_of(message):
        if message.startswith("백업 완료"):
            return "success"
        if message.startswith(("오류", "삭제 실패")):
            return "error"
        if "건너뜁니다" in message:
            return "warn"
        return None

    def log(self, message):
        self.log_textbox.configure(state="normal")
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_textbox.insert("end", now, "ts")
        self.log_textbox.insert("end", "  " + message + "\n", self.level_of(message) or ())
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
        problem = self.validate_paths(self.source_dir.get(), self.target_dir.get())
        if problem:
            fields, message = problem
            self.show_error(message)
            self.entry_src.set_invalid("source" in fields)
            self.entry_dst.set_invalid("target" in fields)
            return

        self.clear_error()
        self.set_input_state("disabled")

        self.is_auto_running = True
        self.btn_toggle.set_variant("secondary", "중지")
        self.timer_label.configure(text_color=C["text"])

        interval_str = self.option_interval.get()
        self.log(f"자동 백업 시작됨 (주기: {interval_str})")

        self.run_backup_process()
        self.schedule_next()
        self.update_timer()

    @staticmethod
    def validate_paths(src, dst):
        """문제가 있으면 (문제의 입력 목록, 메시지), 없으면 None.
        폴더 존재 여부와, 저장 폴더가 원본 폴더 안에 있는 경우(무한 복사)를 검사한다."""
        if not src or not dst:
            fields = {"source"} if not src else set()
            if not dst:
                fields.add("target")
            return fields, "원본 폴더와 저장 폴더를 모두 선택해주세요."
        if not os.path.isdir(src):
            return {"source"}, "원본 폴더가 존재하지 않습니다."
        if not os.path.isdir(dst):
            return {"target"}, "저장 폴더가 존재하지 않습니다."
        real_src, real_dst = os.path.realpath(src), os.path.realpath(dst)
        try:
            inside = os.path.commonpath([real_src, real_dst]) == real_src
        except ValueError:  # 서로 다른 드라이브
            inside = False
        if inside:
            return {"target"}, "저장 폴더는 원본 폴더 안에 있을 수 없습니다."
        return None

    def stop_backup(self):
        self.is_auto_running = False
        if self.current_cancel is not None:
            self.current_cancel.set()  # 진행 중인 복사도 중단한다
        
        self.set_input_state("normal")

        self.btn_toggle.set_variant("primary", "시작")
        self.timer_label.configure(text="--:--", text_color=C["text_sub"])
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
            self.timer_label.configure(text="00:00")
            self.run_backup_process()
            self.schedule_next()
            self.after(1000, self.update_timer)

    def run_backup_process(self):
        # tkinter 변수/위젯은 메인 스레드에서만 읽는다: 값을 먼저 꺼내서 스레드에 넘긴다
        cancel = threading.Event()
        self.current_cancel = cancel
        job = (self.source_dir.get(), self.target_dir.get(), self.keep_map[self.option_keep.get()], cancel)
        threading.Thread(target=self._backup_task, args=job, daemon=True).start()

    def _backup_task(self, src, dst, keep, cancel):
        if not self.backup_lock.acquire(blocking=False):
            self.post(lambda: self.log("이전 백업이 진행 중이라 건너뜁니다."))
            return
        self.post(self.set_busy, True)
        try:
            self._do_backup(src, dst, keep, cancel)
        finally:
            self.backup_lock.release()
            self.post(self.set_busy, False)

    def _do_backup(self, src, dst, keep, cancel):
        try:
            name = core.run_backup(src, dst, cancel)
        except core.Cancelled:
            self.post(lambda: self.log("백업이 취소되어 건너뜁니다."))
            return
        except Exception as e:
            self.post(lambda err=e: self.log(f"오류: {err}"))
            return
        size = core.readable_size(core.folder_size(dst))
        self.post(lambda: self.log(f"백업 완료: {name} (폴더 용량: {size})"))
        deleted, failed = core.prune(dst, os.path.basename(os.path.normpath(src)), keep)
        for old in deleted:
            self.post(lambda o=old: self.log(f"삭제: {o}"))
        for old, err in failed:
            self.post(lambda o=old, e=err: self.log(f"삭제 실패: {o} ({e})"))


if __name__ == "__main__":
    app = ModernBackupApp()
    app.mainloop()