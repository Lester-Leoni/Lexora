import bootstrap  # CRITICAL: Must be the absolute first line
import sys
import os

# --- ИНТЕРЦЕПТОР ДЛЯ ИЗОЛИРОВАННЫХ ПРОЦЕССОВ ---
if len(sys.argv) > 1 and sys.argv[1].endswith("summary_engine.py"):
    import summary_engine
    summary_engine.main()
    sys.exit(0)

# --- ХАК ДЛЯ PYINSTALLER ---
if False:
    import llama_cpp
    import summary_engine

import time
import queue
import threading
import json
import csv
import datetime
import sqlite3
import multiprocessing
import gc
from contextlib import closing
import customtkinter as ctk
from tkinter import filedialog, messagebox
from tkinterdnd2 import TkinterDnD
import ui_components as ui
from ui_components import SpeakerCard, DropZone, DotMatrixProgressBar, THEME_NEURAL_OBSIDIAN, VadSettingsWindow, HistoryCard
from worker import AudioProcessingWorker, SummaryWorker

LOCALIZATION_DATA = {
    "RU": {
        "BTN_SELECT": "Выбрать файл",
        "BTN_STOP": "Стоп",
        "BTN_COPY": "Копировать",
        "BTN_SAVE_DEFAULT": "Сохранить как...",
        "BTN_SETTINGS": "⚙ Настройки VAD",
        "SWITCH_TIMECODES": "Таймкоды",
        "SWITCH_DIARIZATION": "Диалог (Роли)",
        "STATUS_IDLE": "Ожидание файла",
        "SEARCH_PLACEHOLDER": "Поиск по тексту...",
        "SEARCH_FOUND": "Найдено: ",
        "HEADER_SPEAKERS": "СПИКЕРЫ",
        "CARDS_EMPTY": "Появятся после диаризации",
        "LOG_VAD_INJECT": "[+] Новая калибровка VAD применена в рантайме.",
        "LOG_STOP_SIGNAL": "[!] Остановка процесса по команде пользователя. Ожидание завершения потока...",
        "LOG_STOP_TIMEOUT": "[!] Превышено время ожидания завершения потока. Возврат в рабочий режим.",
        "TELEMETRY_CPU": "⚙️ Вычисления: CPU RAM",
        "TELEMETRY_CUDA": "⚙️ CUDA VRAM",
        "DROP_ZONE": "Перетащите аудио/видео файл сюда\nили нажмите, чтобы выбрать",
        "HEADER_HISTORY": "ИСТОРИЯ СЕССИЙ",
        "BTN_LOAD": "Открыть",
        "BTN_DELETE": "Удалить",
        "TAB_SPEAKERS": "Спикеры",
        "TAB_HISTORY": "История",
        "BTN_CLEAR_ALL": "Очистить всю историю",
        "CONFIRM_TITLE": "Удаление истории",
        "CONFIRM_MSG": "Вы уверены, что хотите БЕЗВОЗВРАТНО удалить всю историю сессий и транскрипций?",
        "TAB_ANALYTICS": "ИИ Аналитика",
        "BTN_SUMMARY": "Сгенерировать ИИ-Суммаризацию",
        "SUMMARY_PLACEHOLDER": "Здесь появится краткое содержание текста после запуска анализа...",
        "STATUS_SUMMARY": "Локальный ИИ (Qwen) формирует отчет...",
        "WORKER_CONVERT": "Конвертация аудио (FFmpeg)...",
        "WORKER_WHISPER": "Загрузка модели Whisper...",
        "WORKER_PYANNOTE": "Загрузка модели Pyannote...",
        "WORKER_TRANSCRIBE": "Транскрибация",
        "WORKER_DIARIZE": "Диаризация Pyannote...",
        "WORKER_DONE": "Готово",
        "segmentation": "Поиск речевых сегментов",
        "speaker_counting": "Оценка количества спикеров",
        "embeddings": "Извлечение голосовых отпечатков",
        "discrete_diarization": "Финальная кластеризация"
    },
    "UK": {
        "BTN_SELECT": "Обрати файл",
        "BTN_STOP": "Стоп",
        "BTN_COPY": "Копіювати",
        "BTN_SAVE_DEFAULT": "Зберегти як...",
        "BTN_SETTINGS": "⚙ Налаштування VAD",
        "SWITCH_TIMECODES": "Таймкоди",
        "SWITCH_DIARIZATION": "Діалог (Ролі)",
        "STATUS_IDLE": "Очікування файлу",
        "SEARCH_PLACEHOLDER": "Пошук по тексту...",
        "SEARCH_FOUND": "Знайдено: ",
        "HEADER_SPEAKERS": "СПІКЕРИ",
        "CARDS_EMPTY": "З'являться після діаризації",
        "LOG_VAD_INJECT": "[+] Нова калібровка VAD застосована в рантаймі.",
        "LOG_STOP_SIGNAL": "[!] Зупинка процесу за командою користувача. Очікування завершення потоку...",
        "LOG_STOP_TIMEOUT": "[!] Перевищено час очікування завершення потоку. Повернення в робочий режим.",
        "TELEMETRY_CPU": "⚙️ Обчислення: CPU RAM",
        "TELEMETRY_CUDA": "⚙️ CUDA VRAM",
        "DROP_ZONE": "Перетягніть адіо/відео файл сюди\nабо натисніть, щоб обрати",
        "HEADER_HISTORY": "ІСТОРІЯ СЕСІЙ",
        "BTN_LOAD": "Відкрити",
        "BTN_DELETE": "Вилучити",
        "TAB_SPEAKERS": "Спікери",
        "TAB_HISTORY": "Історія",
        "BTN_CLEAR_ALL": "Очистити всю історію",
        "CONFIRM_TITLE": "Видалення історії",
        "CONFIRM_MSG": "Ви впевнені, що хочете БЕЗПОВОРОТНО видалити всю історію сесій та транскрипцій?",
        "TAB_ANALYTICS": "ШІ Аналітика",
        "BTN_SUMMARY": "Згенерувати ШІ-Суммаризацію",
        "SUMMARY_PLACEHOLDER": "Тут з'явиться короткий зміст текста после запуска аналізу...",
        "STATUS_SUMMARY": "Локальний ШІ (Qwen) формує звіт...",
        "WORKER_CONVERT": "Конвертація аудіо (FFmpeg)...",
        "WORKER_WHISPER": "Завантаження моделі Whisper...",
        "WORKER_PYANNOTE": "Завантаження моделі Pyannote...",
        "WORKER_TRANSCRIBE": "Транскрибация",
        "WORKER_DIARIZE": "Діаризація Pyannote...",
        "WORKER_DONE": "Готово",
        "segmentation": "Пошу мовних сегментов",
        "speaker_counting": "Оцінка кількості спікерів",
        "embeddings": "Виття голосових відбитків",
        "discrete_diarization": "Финальна кластеризація"
    },
    "EN": {
        "BTN_SELECT": "Select File",
        "BTN_STOP": "Stop",
        "BTN_COPY": "Copy",
        "BTN_SAVE_DEFAULT": "Save as...",
        "BTN_SETTINGS": "⚙ VAD Settings",
        "SWITCH_TIMECODES": "Timecodes",
        "SWITCH_DIARIZATION": "Dialogue (Roles)",
        "STATUS_IDLE": "Waiting for file",
        "SEARCH_PLACEHOLDER": "Search text...",
        "SEARCH_FOUND": "Found: ",
        "HEADER_SPEAKERS": "SPEAKERS",
        "CARDS_EMPTY": "Will appear after diarization",
        "LOG_VAD_INJECT": "[+] New VAD calibration applied at runtime.",
        "LOG_STOP_SIGNAL": "[!] Process stopped by user. Waiting for thread shutdown...",
        "LOG_STOP_TIMEOUT": "[!] Thread shutdown timeout exceeded. Returning to operational state.",
        "TELEMETRY_CPU": "⚙️ Computing: CPU RAM",
        "TELEMETRY_CUDA": "⚙️ CUDA VRAM",
        "DROP_ZONE": "Drag and drop audio/video file here\nor click to select",
        "HEADER_HISTORY": "SESSION HISTORY",
        "BTN_LOAD": "Open",
        "BTN_DELETE": "Delete",
        "TAB_SPEAKERS": "Speakers",
        "TAB_HISTORY": "History",
        "BTN_CLEAR_ALL": "Clear all history",
        "CONFIRM_TITLE": "Delete History",
        "CONFIRM_MSG": "Are you sure you want to PERMANENTLY delete all session and transcription history?",
        "TAB_ANALYTICS": "AI Analytics",
        "BTN_SUMMARY": "Generate AI Summary",
        "STATUS_SUMMARY": "Local AI (Qwen) is generating report...",
        "WORKER_CONVERT": "Converting audio (FFmpeg)...",
        "WORKER_WHISPER": "Loading Whisper model...",
        "WORKER_PYANNOTE": "Loading Pyannote model...",
        "WORKER_TRANSCRIBE": "Transcription",
        "WORKER_DIARIZE": "Pyannote Diarization...",
        "WORKER_DONE": "Done",
        "segmentation": "Voice segment detection",
        "speaker_counting": "Speaker count estimation",
        "embeddings": "Extracting voice embeddings",
        "discrete_diarization": "Final clustering"
    }
}


class DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)


class LexoraApp(DnDCTk):
    def tr(self, key: str) -> str:
        lang_dict = LOCALIZATION_DATA.get(self.current_lang, LOCALIZATION_DATA["RU"])
        return lang_dict.get(key, LOCALIZATION_DATA["RU"].get(key, key))

    def _fg(self, theme_key: str) -> str:
        light, dark = ui.THEME_NEURAL_OBSIDIAN[theme_key]
        return dark if ctk.get_appearance_mode() == "Dark" else light

    def __init__(self):
        super().__init__()
        self.current_lang = "RU"
        ui.init_fonts()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        self.title("Lexora v1.7.2")
        self.geometry("960x680")
        self.minsize(820, 600)
        self.resizable(True, True)
        self.configure(fg_color=ui.THEME_NEURAL_OBSIDIAN["window_bg"])

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.transcribed_segments = []
        self.speaker_cards = {}
        self.current_audio_path = None
        self.is_running = False
        self.current_status_text = ""

        self.speaker_names_map = {}
        self.speaker_entries = {}

        self.show_time_var = ctk.BooleanVar(value=True)
        self.use_roles_var = ctk.BooleanVar(value=False)

        self.search_matches = []
        self.current_match_idx = -1

        self.vad_config = {"segmentation": {"threshold": 0.50, "min_duration_off": 0.50, "min_duration_on": 0.20}}
        self.settings_window = None
        self.current_summary_text = ""
        
        self._init_db()

        # Панель управления верхняя
        self.top_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.top_frame.pack(pady=(14, 8), padx=14, fill="x")

        self.btn_select = ctk.CTkButton(self.top_frame, text=self.tr("BTN_SELECT"), font=ui.FONT_BODY_MED, fg_color=ui.THEME_NEURAL_OBSIDIAN["cyan_neon"], text_color="#000000", hover_color=ui.THEME_NEURAL_OBSIDIAN["cyan_dim"], corner_radius=ui.CORNER_RADIUS_DEFAULT, command=self.start_processing)
        self.btn_select.pack(side="left", padx=5)

        self.btn_stop = ctk.CTkButton(self.top_frame, text=self.tr("BTN_STOP"), font=ui.FONT_BODY_MED, fg_color="#c93434", hover_color="#a32a2a", corner_radius=ui.CORNER_RADIUS_DEFAULT, state="disabled", command=self.stop_processing)
        self.btn_stop.pack(side="left", padx=5)

        self.btn_copy = ctk.CTkButton(self.top_frame, text=self.tr("BTN_COPY"), font=ui.FONT_BODY, fg_color=ui.THEME_NEURAL_OBSIDIAN["frame_bg"], text_color=ui.THEME_NEURAL_OBSIDIAN["text_main"], hover_color=ui.THEME_NEURAL_OBSIDIAN["card_bg"], corner_radius=ui.CORNER_RADIUS_DEFAULT, command=self.copy_text)
        self.btn_copy.pack(side="left", padx=5)

        self.btn_save = ctk.CTkOptionMenu(self.top_frame, values=["Текст (.txt)", "Субтитры (.srt)", "Субтитры (.vtt)", "Данные JSON (.json)", "Таблица CSV (.csv)"], font=ui.FONT_BODY, fg_color=ui.THEME_NEURAL_OBSIDIAN["frame_bg"], button_color=ui.THEME_NEURAL_OBSIDIAN["cyan_dim"], button_hover_color=ui.THEME_NEURAL_OBSIDIAN["cyan_neon"], text_color=ui.THEME_NEURAL_OBSIDIAN["text_main"], dropdown_fg_color=ui.THEME_NEURAL_OBSIDIAN["card_bg"], dropdown_text_color=ui.THEME_NEURAL_OBSIDIAN["text_main"], dropdown_hover_color=ui.THEME_NEURAL_OBSIDIAN["frame_bg"], corner_radius=ui.CORNER_RADIUS_DEFAULT, state="disabled", command=self._on_save_dropdown_click)
        self.btn_save.set(self.tr("BTN_SAVE_DEFAULT"))
        self.btn_save.pack(side="left", padx=5)

        self.btn_settings = ctk.CTkButton(self.top_frame, text=self.tr("BTN_SETTINGS"), font=ui.FONT_SMALL, fg_color=ui.THEME_NEURAL_OBSIDIAN["frame_bg"], text_color=ui.THEME_NEURAL_OBSIDIAN["text_main"], hover_color=ui.THEME_NEURAL_OBSIDIAN["card_bg"], border_width=1, border_color=ui.THEME_NEURAL_OBSIDIAN["cyan_dim"], corner_radius=ui.CORNER_RADIUS_DEFAULT, command=self.open_vad_settings)
        self.btn_settings.pack(side="left", padx=5)

        self.switch_timecodes = ctk.CTkSwitch(self.top_frame, text=self.tr("SWITCH_TIMECODES"), font=ui.FONT_SMALL, progress_color=ui.THEME_NEURAL_OBSIDIAN["cyan_neon"], variable=self.show_time_var, command=self.redraw_interface)
        self.switch_timecodes.pack(side="right", padx=10)

        self.switch_diarization = ctk.CTkSwitch(self.top_frame, text=self.tr("SWITCH_DIARIZATION"), font=ui.FONT_SMALL, progress_color=ui.THEME_NEURAL_OBSIDIAN["cyan_neon"], variable=self.use_roles_var)
        self.switch_diarization.pack(side="right", padx=10)

        self.btn_lang = ctk.CTkButton(self.top_frame, text=self.current_lang, width=44, font=ui.FONT_BODY_MED, fg_color=ui.THEME_NEURAL_OBSIDIAN["frame_bg"], text_color=ui.THEME_NEURAL_OBSIDIAN["text_main"], hover_color=ui.THEME_NEURAL_OBSIDIAN["card_bg"], corner_radius=ui.CORNER_RADIUS_DEFAULT, command=self._cycle_language)
        self.btn_lang.pack(side="right", padx=5)

        self.drop_zone = ui.DropZone(self, on_file_dropped=self.start_processing, height=120)
        self.drop_zone.hint_label.configure(text=self.tr("DROP_ZONE"))
        self.drop_zone.pack(padx=14, pady=(0, 10), fill="x")

        status_frame = ctk.CTkFrame(self, fg_color="transparent")
        status_frame.pack(padx=14, pady=(0, 10), fill="x")

        labels_frame = ctk.CTkFrame(status_frame, fg_color="transparent")
        labels_frame.pack(fill="x")

        self.status_label = ctk.CTkLabel(labels_frame, text=self.tr("STATUS_IDLE"), font=ui.FONT_SMALL, anchor="w", text_color=ui.THEME_NEURAL_OBSIDIAN["text_dim"])
        self.status_label.pack(side="left")

        self.telemetry_label = ctk.CTkLabel(labels_frame, text="", font=ui.FONT_SMALL, anchor="e", text_color=ui.THEME_NEURAL_OBSIDIAN["cyan_neon"])
        self.telemetry_label.pack(side="right")

        self.progressbar = ctk.CTkProgressBar(status_frame, mode="determinate", progress_color=ui.THEME_NEURAL_OBSIDIAN["cyan_neon"], fg_color=ui.THEME_NEURAL_OBSIDIAN["frame_bg"], corner_radius=ui.CORNER_RADIUS_DEFAULT // 2)
        self.progressbar.pack(pady=(4, 0), fill="x")
        self.progressbar.set(0)

        body_frame = ctk.CTkFrame(self, fg_color="transparent")
        body_frame.pack(padx=14, pady=(0, 14), fill="both", expand=True)
        body_frame.grid_columnconfigure(0, weight=3)
        body_frame.grid_columnconfigure(1, weight=1)
        body_frame.grid_rowconfigure(1, weight=1)

        self.search_frame = ctk.CTkFrame(body_frame, fg_color="transparent")
        self.search_frame.grid(row=0, column=0, sticky="ew", padx=(0, 10), pady=(0, 8))

        self.search_entry = ctk.CTkEntry(self.search_frame, placeholder_text=self.tr("SEARCH_PLACEHOLDER"), font=ui.FONT_SMALL, fg_color=ui.THEME_NEURAL_OBSIDIAN["card_bg"], border_color=ui.THEME_NEURAL_OBSIDIAN["cyan_dim"])
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<KeyRelease>", self._execute_text_search)

        self.btn_search_up = ctk.CTkButton(self.search_frame, text="▲", width=28, height=28, font=ui.FONT_SMALL, fg_color=ui.THEME_NEURAL_OBSIDIAN["frame_bg"], text_color=ui.THEME_NEURAL_OBSIDIAN["text_main"], hover_color=ui.THEME_NEURAL_OBSIDIAN["card_bg"], corner_radius=ui.CORNER_RADIUS_DEFAULT, command=self._search_navigate_up)
        self.btn_search_up.pack(side="left", padx=(5, 0))

        self.btn_search_down = ctk.CTkButton(self.search_frame, text="▼", width=28, height=28, font=ui.FONT_SMALL, fg_color=ui.THEME_NEURAL_OBSIDIAN["frame_bg"], text_color=ui.THEME_NEURAL_OBSIDIAN["text_main"], hover_color=ui.THEME_NEURAL_OBSIDIAN["card_bg"], corner_radius=ui.CORNER_RADIUS_DEFAULT, command=self._search_navigate_down)
        self.btn_search_down.pack(side="left", padx=(5, 10))

        self.search_count_label = ctk.CTkLabel(self.search_frame, text=self.tr("SEARCH_FOUND") + "0", font=ui.FONT_SMALL, text_color=ui.THEME_NEURAL_OBSIDIAN["text_dim"])
        self.search_count_label.pack(side="right")

        self.textbox = ctk.CTkTextbox(body_frame, state="disabled", font=ui.FONT_MONO, fg_color=ui.THEME_NEURAL_OBSIDIAN["window_bg"], text_color=ui.THEME_NEURAL_OBSIDIAN["text_main"], corner_radius=ui.CORNER_RADIUS_DEFAULT)
        self.textbox.grid(row=1, column=0, sticky="nsew", padx=(0, 10))

        self._raw_textbox = self.textbox._textbox
        self._raw_textbox.tag_config("ts", foreground=self._fg("text_dim"))
        self._raw_textbox.tag_config("spk", foreground=self._fg("cyan_neon"), font=("Consolas", 13, "bold"))
        self._raw_textbox.tag_config("search_highlight", background=self._fg("cyan_neon"), foreground="#000000")
        self._raw_textbox.tag_config("search_active_highlight", background="#FF9900", foreground="#000000")

        self.right_panel = ctk.CTkFrame(body_frame, fg_color=ui.THEME_NEURAL_OBSIDIAN["frame_bg"], corner_radius=ui.CORNER_RADIUS_DEFAULT)
        self.right_panel.grid(row=0, column=1, rowspan=2, sticky="nsew")
        
        self.right_nav_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        self.right_nav_frame.pack(fill="x", padx=10, pady=(10, 5))
        
        self.btn_tab_speakers = ctk.CTkButton(self.right_nav_frame, text=self.tr("TAB_SPEAKERS"), font=ui.FONT_SMALL, fg_color=ui.THEME_NEURAL_OBSIDIAN["card_bg"], text_color=ui.THEME_NEURAL_OBSIDIAN["text_main"], hover_color=ui.THEME_NEURAL_OBSIDIAN["cyan_dim"], corner_radius=ui.CORNER_RADIUS_DEFAULT, command=lambda: self._switch_right_tab("speakers"))
        self.btn_tab_speakers.pack(side="left", expand=True, padx=(0, 2))
        
        self.btn_tab_history = ctk.CTkButton(self.right_nav_frame, text=self.tr("TAB_HISTORY"), font=ui.FONT_SMALL, fg_color=ui.THEME_NEURAL_OBSIDIAN["card_bg"], text_color=ui.THEME_NEURAL_OBSIDIAN["text_main"], hover_color=ui.THEME_NEURAL_OBSIDIAN["cyan_dim"], corner_radius=ui.CORNER_RADIUS_DEFAULT, command=lambda: self._switch_right_tab("history"))
        self.btn_tab_history.pack(side="left", expand=True, padx=(2, 2))
        
        self.btn_tab_analytics = ctk.CTkButton(self.right_nav_frame, text=self.tr("TAB_ANALYTICS"), font=ui.FONT_SMALL, fg_color=ui.THEME_NEURAL_OBSIDIAN["card_bg"], text_color=ui.THEME_NEURAL_OBSIDIAN["text_main"], hover_color=ui.THEME_NEURAL_OBSIDIAN["cyan_dim"], corner_radius=ui.CORNER_RADIUS_DEFAULT, command=lambda: self._switch_right_tab("analytics"))
        self.btn_tab_analytics.pack(side="left", expand=True, padx=(2, 0))
        
        self.speakers_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        self.history_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        self.analytics_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        
        self.cards_panel = ctk.CTkScrollableFrame(self.speakers_frame, fg_color="transparent")
        self.cards_panel.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.cards_empty_label = ctk.CTkLabel(self.cards_panel, text=self.tr("CARDS_EMPTY"), font=ui.FONT_SMALL, text_color=ui.THEME_NEURAL_OBSIDIAN["text_dim"], wraplength=160)
        self.cards_empty_label.pack(pady=20)
        
        self.history_panel = ctk.CTkScrollableFrame(self.history_frame, fg_color="transparent")
        self.history_panel.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        
        self.btn_clear_all = ctk.CTkButton(self.history_frame, text=self.tr("BTN_CLEAR_ALL"), font=ui.FONT_SMALL, height=28, fg_color="#a32a2a", hover_color="#c93434", corner_radius=ui.CORNER_RADIUS_DEFAULT, command=self._clear_all_history_action)
        self.btn_clear_all.pack(fill="x", padx=8, pady=(0, 8))
        
        self.analytics_textbox = ctk.CTkTextbox(self.analytics_frame, font=ui.FONT_SMALL, fg_color=ui.THEME_NEURAL_OBSIDIAN["card_bg"], text_color=ui.THEME_NEURAL_OBSIDIAN["text_main"], corner_radius=8)
        self.analytics_textbox.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self._write_summary_placeholder()
        
        self.btn_summary = ctk.CTkButton(self.analytics_frame, text=self.tr("BTN_SUMMARY"), font=ui.FONT_BODY_MED, height=32, fg_color=ui.THEME_NEURAL_OBSIDIAN["cyan_dim"], hover_color=ui.THEME_NEURAL_OBSIDIAN["cyan_neon"], text_color="#FFFFFF", corner_radius=6, command=self.trigger_local_summary)
        self.btn_summary.pack(fill="x", padx=8, pady=(0, 8))
        self.btn_summary.configure(state="disabled")
        
        self._switch_right_tab("speakers")
        self._refresh_history_ui()

    def on_closing(self):
        if self.is_running:
            if not messagebox.askokcancel("Выход", "Процесс обработки еще идет. Вы уверены, что хотите прервать его и выйти?"):
                return
                
        if hasattr(self, 'cancel_event'):
            self.cancel_event.set()
            
        if hasattr(self, 'summary_thread') and hasattr(self.summary_thread, 'proc'):
            try: 
                self.summary_thread.proc.kill() 
                self.summary_thread.proc.wait()  # ИСПРАВЛЕНИЕ: Чистое завершение
            except Exception: pass
            
        self.destroy()

    def format_time(self, seconds, decimal_separator=","):
        total_ms = int(round(seconds * 1000))
        hours, remainder = divmod(total_ms, 3600000)
        minutes, remainder = divmod(remainder, 60000)
        secs, ms = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}{decimal_separator}{ms:03d}"

    def _write_summary_placeholder(self):
        self.analytics_textbox.configure(state="normal")
        self.analytics_textbox.delete("1.0", "end")
        self.analytics_textbox.insert("1.0", self.tr("SUMMARY_PLACEHOLDER"))
        self.analytics_textbox.configure(state="disabled")

    def _init_db(self):
        app_data = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        db_dir = os.path.join(app_data, "Lexora")
        os.makedirs(db_dir, exist_ok=True)
        self.db_path = os.path.join(db_dir, "lexora_history.db")
        
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;") 
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        file_name TEXT,
                        file_path TEXT,
                        duration REAL,
                        lang TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS transcripts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id INTEGER,
                        start_sec REAL,
                        end_sec REAL,
                        speaker_raw TEXT,
                        speaker_display TEXT,
                        text TEXT,
                        FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
                    )
                """)

    def _save_session_to_db(self, segments, diarization_result):
        if not segments: return
        duration = segments[-1][1] if segments else 0.0
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file_name = os.path.basename(self.current_audio_path) if self.current_audio_path else "unknown"
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                cursor = conn.cursor()
                with conn:
                    cursor.execute("""
                        INSERT INTO sessions (timestamp, file_name, file_path, duration, lang)
                        VALUES (?, ?, ?, ?, ?)
                    """, (timestamp, file_name, self.current_audio_path, duration, self.current_lang))
                    session_id = cursor.lastrowid
                    for start, end, text in segments:
                        s_raw = ""
                        s_disp = ""
                        processed_text = text
                        if text.startswith("[") and "] " in text:
                            maybe_speaker, _, rest = text[1:].partition("] ")
                            if maybe_speaker.startswith("SPEAKER_"):
                                s_raw = maybe_speaker
                                s_disp = self.speaker_names_map.get(maybe_speaker, maybe_speaker)
                                processed_text = rest
                        cursor.execute("""
                            INSERT INTO transcripts (session_id, start_sec, end_sec, speaker_raw, speaker_display, text)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (session_id, start, end, s_raw, s_disp, processed_text))
            self._refresh_history_ui()
        except Exception as e:
            self.system_log_ui(f"[-] Ошибка сохранения в БД: {e}")

    def _refresh_history_ui(self):
        for widget in self.history_panel.winfo_children(): widget.destroy()
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, timestamp, file_name, duration FROM sessions ORDER BY id DESC")
                rows = cursor.fetchall()
                for row in rows:
                    session_id, timestamp, file_name, duration = row
                    card = HistoryCard(
                        self.history_panel, session_id, timestamp, file_name, duration,
                        self._load_session_from_db, self._delete_session_from_db,
                        self.tr("BTN_LOAD"), self.tr("BTN_DELETE")
                    )
                    card.pack(fill="x", padx=4, pady=4)
        except Exception as e:
            self.system_log_ui(f"[-] Ошибка чтения истории: {e}")

    def _load_session_from_db(self, session_id):
        if self.is_running:
            messagebox.showwarning("Внимание", "Дождитесь окончания текущей транскрибации!")
            return
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT file_path FROM sessions WHERE id = ?", (session_id,))
                row = cursor.fetchone()
                if row: self.current_audio_path = row[0]
                cursor.execute("SELECT start_sec, end_sec, speaker_raw, speaker_display, text FROM transcripts WHERE session_id = ? ORDER BY id ASC", (session_id,))
                transcripts = cursor.fetchall()
                self.transcribed_segments = []
                self.speaker_names_map = {}
                for start, end, speaker_raw, speaker_display, text in transcripts:
                    if speaker_raw:
                        self.speaker_names_map[speaker_raw] = speaker_display
                        full_text = f"[{speaker_raw}] {text}"
                    else: full_text = text
                    self.transcribed_segments.append((start, end, full_text))
            self.redraw_interface()
            self._clear_speaker_cards()
            if self.speaker_names_map:
                self.cards_empty_label.pack_forget()
                durations = {}
                for start, end, text in self.transcribed_segments:
                    if text.startswith("[") and "] " in text:
                        maybe_speaker, _, _ = text[1:].partition("] ")
                        if maybe_speaker.startswith("SPEAKER_"):
                            durations[maybe_speaker] = durations.get(maybe_speaker, 0.0) + (end - start)
                total = sum(durations.values())
                for speaker in sorted(durations.keys()):
                    current_display_name = self.speaker_names_map[speaker]
                    card = SpeakerCard(self.cards_panel, speaker, durations[speaker], total, current_display_name, self._on_speaker_renamed)
                    card.pack(fill="x", padx=4, pady=4)
                    self.speaker_cards[speaker] = card
                    self.speaker_entries[speaker] = card.name_entry
                    
            self.btn_save.configure(state="normal")
            self.btn_summary.configure(state="normal")
            self.current_summary_text = ""
            self._write_summary_placeholder()
            self.status_label.configure(text=f"Загружена сессия: {os.path.basename(self.current_audio_path) if self.current_audio_path else 'unknown'}")
            self._switch_right_tab("speakers")
        except Exception as e:
            self.system_log_ui(f"[-] Ошибка загрузки сессии: {e}")

    def _delete_session_from_db(self, session_id):
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                conn.execute("PRAGMA foreign_keys = ON;")
                with conn:
                    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            self._refresh_history_ui()
        except Exception as e:
            self.system_log_ui(f"[-] Ошибка удаления сессии: {e}")

    def _clear_all_history_action(self):
        if messagebox.askyesno(self.tr("CONFIRM_TITLE"), self.tr("CONFIRM_MSG")):
            try:
                with closing(sqlite3.connect(self.db_path)) as conn:
                    conn.execute("PRAGMA foreign_keys = ON;")
                    with conn:
                        conn.execute("DELETE FROM sessions;")
                self._refresh_history_ui()
                self._reset_ui_state()
            except Exception as e:
                self.system_log_ui(f"[-] Ошибка очистки истории: {e}")

    def _switch_right_tab(self, tab_name):
        self.speakers_frame.pack_forget()
        self.history_frame.pack_forget()
        self.analytics_frame.pack_forget()
        
        self.btn_tab_speakers.configure(fg_color=ui.THEME_NEURAL_OBSIDIAN["card_bg"])
        self.btn_tab_history.configure(fg_color=ui.THEME_NEURAL_OBSIDIAN["card_bg"])
        self.btn_tab_analytics.configure(fg_color=ui.THEME_NEURAL_OBSIDIAN["card_bg"])

        if tab_name == "speakers":
            self.speakers_frame.pack(fill="both", expand=True)
            self.btn_tab_speakers.configure(fg_color=ui.THEME_NEURAL_OBSIDIAN["cyan_dim"])
        elif tab_name == "history":
            self.history_frame.pack(fill="both", expand=True)
            self.btn_tab_history.configure(fg_color=ui.THEME_NEURAL_OBSIDIAN["cyan_dim"])
        elif tab_name == "analytics":
            self.analytics_frame.pack(fill="both", expand=True)
            self.btn_tab_analytics.configure(fg_color=ui.THEME_NEURAL_OBSIDIAN["cyan_dim"])

    def _execute_text_search(self, event=None):
        query = self.search_entry.get().lower().strip()
        self._raw_textbox.tag_remove("search_highlight", "1.0", "end")
        self._raw_textbox.tag_remove("search_active_highlight", "1.0", "end")
        self.search_matches = []
        self.current_match_idx = -1
        if not query:
            self.search_count_label.configure(text=self.tr("SEARCH_FOUND") + "0")
            return
        start_pos = "1.0"
        query_len = len(query)
        while True:
            start_pos = self._raw_textbox.search(query, start_pos, stopindex="end", nocase=True)
            if not start_pos: break
            end_pos = f"{start_pos}+{query_len}c"
            self._raw_textbox.tag_add("search_highlight", start_pos, end_pos)
            self.search_matches.append((start_pos, end_pos))
            start_pos = end_pos
        if self.search_matches:
            self.current_match_idx = 0
            self._highlight_current_match()
        else:
            self.search_count_label.configure(text=self.tr("SEARCH_FOUND") + "0")

    def _highlight_current_match(self):
        if not self.search_matches or self.current_match_idx < 0: return
        self._raw_textbox.tag_remove("search_active_highlight", "1.0", "end")
        start_pos, end_pos = self.search_matches[self.current_match_idx]
        self._raw_textbox.tag_add("search_active_highlight", start_pos, end_pos)
        self._raw_textbox.see(start_pos)
        total = len(self.search_matches)
        self.search_count_label.configure(text=f"{self.tr('SEARCH_FOUND')}{self.current_match_idx + 1}/{total}")

    def _search_navigate_up(self):
        if not self.search_matches: return
        self.current_match_idx -= 1
        if self.current_match_idx < 0: self.current_match_idx = len(self.search_matches) - 1
        self._highlight_current_match()

    def _search_navigate_down(self):
        if not self.search_matches: return
        self.current_match_idx += 1
        if self.current_match_idx >= len(self.search_matches): self.current_match_idx = 0
        self._highlight_current_match()

    def redraw_interface(self):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        for idx, (start, end, text) in enumerate(self.transcribed_segments):
            self._insert_segment_line(idx, start, end, text)
        self.textbox.see("end")
        self.textbox.configure(state="disabled")
        self._execute_text_search()

    def _insert_segment_line(self, idx, start, end, text):
        seg_tag = f"seg_{idx}"
        if self.show_time_var.get():
            ui_time = f"{int(start)//3600:02d}:{int(start)%3600//60:02d}:{int(start)%60:02d}"
            ui_end = f"{int(end)//3600:02d}:{int(end)%3600//60:02d}:{int(end)%60:02d}"
            self.textbox.insert("end", f"[{ui_time} -> {ui_end}] ", ("ts", seg_tag))
        speaker_label = None
        body_text = text
        if text.startswith("[") and "] " in text:
            maybe_speaker, _, rest = text[1:].partition("] ")
            if maybe_speaker.startswith("SPEAKER_"):
                speaker_label = maybe_speaker
                body_text = rest
        if speaker_label:
            display_name = self.speaker_names_map.get(speaker_label, speaker_label)
            self.textbox.insert("end", f"{display_name}: ", ("spk", seg_tag))
            
        # ИСПРАВЛЕНИЕ: Замена эмодзи на стандартный символ неизвестного знака ()
        safe_body_text = ''.join(c if ord(c) <= 0xFFFF else '\ufffd' for c in body_text)
        self.textbox.insert("end", f"{safe_body_text}\n", (seg_tag,))
        
        if speaker_label:
            self._raw_textbox.tag_bind(seg_tag, "<Button-1>", lambda e, spk=speaker_label: self._on_transcript_segment_click(spk))

    def _on_transcript_segment_click(self, speaker_id: str):
        for sid, card in self.speaker_cards.items(): card.set_active(sid == speaker_id)

    def append_segment_ui(self, start, end, text):
        idx = len(self.transcribed_segments)
        self.transcribed_segments.append((start, end, text))
        self.textbox.configure(state="normal")
        self._insert_segment_line(idx, start, end, text)
        self.textbox.see("end")
        self.textbox.configure(state="disabled")
        self._execute_text_search()

    def system_log_ui(self, text):
        self.textbox.configure(state="normal")
        self.textbox.insert("end", text + "\n")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def copy_text(self):
        text = self.textbox.get("1.0", "end-1c")
        if text.strip():
            self.clipboard_clear()
            self.clipboard_append(text)
            messagebox.showinfo("Скопировано", "Текст скопирован в буфер обмена.")

    def _clear_speaker_cards(self):
        for card in self.speaker_cards.values(): card.destroy()
        self.speaker_cards.clear()
        self.speaker_entries.clear()
        self.cards_empty_label.pack(pady=20)

    def _populate_speaker_cards(self, diarization_result):
        durations = {}
        for turn, _, speaker in diarization_result.itertracks(yield_label=True):
            durations[speaker] = durations.get(speaker, 0.0) + (turn.end - turn.start)
        if not durations: return
        self.cards_empty_label.pack_forget()
        total = sum(durations.values())
        self.speaker_entries.clear()
        for speaker in sorted(durations.keys()):
            if speaker not in self.speaker_names_map: self.speaker_names_map[speaker] = speaker
            current_display_name = self.speaker_names_map[speaker]
            card = SpeakerCard(self.cards_panel, speaker, durations[speaker], total, current_display_name, self._on_speaker_renamed)
            card.pack(fill="x", padx=4, pady=4)
            self.speaker_cards[speaker] = card
            self.speaker_entries[speaker] = card.name_entry

    def _on_speaker_renamed(self, speaker_id: str):
        entry = self.speaker_entries.get(speaker_id)
        if not entry: return
        name = entry.get().strip()
        if not name:
            name = speaker_id
            entry.delete(0, "end")
            entry.insert(0, speaker_id)
        if self.speaker_names_map.get(speaker_id) == name: return
        self.speaker_names_map[speaker_id] = name
        entry.configure(border_width=1, border_color=self._fg("cyan_neon"))
        self.after(400, lambda: entry.configure(border_width=0))
        current_scroll = self.textbox.yview()
        self.redraw_interface()
        self.textbox.yview_moveto(current_scroll[0])

    def open_vad_settings(self):
        if self.settings_window is None or not self.settings_window.winfo_exists():
            self.settings_window = VadSettingsWindow(self, self.vad_config, self.save_vad_settings)
        else: self.settings_window.focus()

    def save_vad_settings(self, updated_config):
        self.vad_config = updated_config
        self.system_log_ui(f"\n{self.tr('LOG_VAD_INJECT')}")

    def start_processing(self, filepath=None):
        if self.is_running:
            messagebox.showwarning("Внимание", "Дождитесь окончания текущей транскрибации!")
            return
        if not filepath:
            # ИСПРАВЛЕНИЕ: Выбор только одного файла
            filepath = filedialog.askopenfilename(title="Выберите файл", filetypes=[("Media Files", "*.mp3 *.wav *.m4a *.mp4 *.mkv"), ("All Files", "*.*")])
        if not filepath: return

        self.current_audio_path = filepath
        self.transcribed_segments.clear()
        self.is_running = True
        self.current_summary_text = ""

        self.btn_select.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_settings.configure(state="disabled")  
        self.switch_diarization.configure(state="disabled")
        self.btn_save.configure(state="disabled")
        self.btn_summary.configure(state="disabled")
        self._clear_speaker_cards()
        self._write_summary_placeholder()

        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")
        self.progressbar.set(0)
        self.status_label.configure(text=f"{self.tr('WORKER_CONVERT')}: {os.path.basename(filepath)}")
        self.telemetry_label.configure(text="")
        self.current_status_text = "WORKER_CONVERT"
        self.last_device = "cpu"
        self.last_vram = 0.0

        self.task_queue = queue.Queue()
        self.cancel_event = threading.Event()
        
        self.worker = AudioProcessingWorker(
            audio_file=filepath, use_diarization=self.use_roles_var.get(), 
            task_queue=self.task_queue, cancel_event=self.cancel_event,
            vad_config=self.vad_config
        )
        self.worker.start()
        self._poll_queue()

    def stop_processing(self):
        if getattr(self, 'is_running', False):
            self.system_log_ui(f"\n{self.tr('LOG_STOP_SIGNAL')}")
            self.btn_stop.configure(state="disabled")
            if hasattr(self, 'cancel_event'): self.cancel_event.set()
            
            if hasattr(self, 'summary_thread') and hasattr(self.summary_thread, 'proc'):
                try: 
                    self.summary_thread.proc.kill() 
                    self.summary_thread.proc.wait()  # ИСПРАВЛЕНИЕ: Чистое завершение
                except Exception: pass
                
            self._shutdown_start_time = time.monotonic()
            self._await_worker_shutdown()

    def _await_worker_shutdown(self):
        if hasattr(self, 'worker') and self.worker.is_alive():
            if time.monotonic() - self._shutdown_start_time > 15.0:
                self.system_log_ui(f"\n{self.tr('LOG_STOP_TIMEOUT')}")
                messagebox.showerror("Критическая ошибка", "Фоновый процесс не отвечает.\nВидеопамять (VRAM) может быть заблокирована.\nНастоятельно рекомендуется перезапустить приложение!")
                self._reset_ui_state()
            else: self.after(150, self._await_worker_shutdown)
        else: self._reset_ui_state()

    def trigger_local_summary(self):
        raw_text_list = []
        for _, _, txt in self.transcribed_segments:
            raw_text_list.append(txt)
        full_transcript_text = "\n".join(raw_text_list).strip()

        if not full_transcript_text:
            messagebox.showwarning("Внимание", "Текст расшифровки пуст. Нечего анализировать!")
            return

        if hasattr(self, 'worker'):
            del self.worker
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()

        while not self.task_queue.empty():
            try: self.task_queue.get_nowait()
            except queue.Empty: break

        self.btn_summary.configure(state="disabled", text="⏳ Локальный ИИ думает...")
        self.btn_select.configure(state="disabled")
        self.btn_tab_history.configure(state="disabled")
        self.btn_tab_speakers.configure(state="disabled")
        
        self.btn_stop.configure(state="normal")

        self.analytics_textbox.configure(state="normal")
        self.analytics_textbox.delete("1.0", "end")
        self.analytics_textbox.configure(state="disabled")

        if not hasattr(self, 'cancel_event'):
            self.cancel_event = threading.Event()
        self.summary_thread = SummaryWorker(full_transcript_text, self.current_lang, self.task_queue, self.cancel_event)
        self.summary_thread.start()
        
        if not self.is_running:
            self.is_running = True
            self._poll_queue()

    def _poll_queue(self):
        messages_processed = 0
        while not self.task_queue.empty() and messages_processed < 30:
            try: msg_type, data = self.task_queue.get_nowait()
            except queue.Empty: break
            messages_processed += 1
                
            if msg_type == "STATUS": 
                self.current_status_text = data
                if data.startswith("WORKER_TRANSCRIBE"):
                    phase_key = "WORKER_TRANSCRIBE"
                    extra = data.replace("WORKER_TRANSCRIBE", "").strip()
                    translated_status = f"{self.tr(phase_key)} {extra}"
                else:
                    translated_status = self.tr(data)
                    
                if hasattr(self, 'last_device'):
                    device = self.last_device
                    vram_used = getattr(self, 'last_vram', 0.0)
                    if device == "cuda":
                        self.telemetry_label.configure(text=f"{self.tr('TELEMETRY_CUDA')}: {vram_used:.2f} GB | Статус: {translated_status}")
                    else: self.telemetry_label.configure(text=f"{self.tr('TELEMETRY_CPU')} | Статус: {translated_status}")
                else: self.telemetry_label.configure(text=f"Статус: {translated_status}")
            elif msg_type == "TELEMETRY":
                vram_used, device = data
                self.last_device = device
                self.last_vram = vram_used
                status_text = getattr(self, 'current_status_text', 'Обработка...')
                if status_text.startswith("WORKER_TRANSCRIBE"):
                    translated_status = f"{self.tr('WORKER_TRANSCRIBE')} {status_text.replace('WORKER_TRANSCRIBE', '').strip()}"
                else:
                    translated_status = self.tr(status_text)
                if device == "cuda":
                    self.telemetry_label.configure(text=f"{self.tr('TELEMETRY_CUDA')}: {vram_used:.2f} GB | Статус: {translated_status}")
                else:
                    self.telemetry_label.configure(text=f"{self.tr('TELEMETRY_CPU')} | Статус: {translated_status}")
            elif msg_type == "PROGRESS": self.progressbar.set(data)
            elif msg_type == "LOG": self.system_log_ui(data)
            elif msg_type == "SEGMENT":
                start, end, text = data
                self.append_segment_ui(start, end, text)
            elif msg_type == "DONE":
                final_segments, diarization_result = data
                self.transcribed_segments = final_segments
                self.redraw_interface()
                if diarization_result is not None: self._populate_speaker_cards(diarization_result)
                self.btn_save.configure(state="normal")
                self.btn_summary.configure(state="normal") 
                self._save_session_to_db(final_segments, diarization_result)
                self._reset_ui_state()
                return 
            elif msg_type == "ERROR":
                self.system_log_ui(f"\n[-] КРИТИЧЕСКАЯ ОШИБКА:\n{data}")
                self._reset_ui_state()
                return
            
            elif msg_type == "SUMMARY_STATUS":
                self.status_label.configure(text=self.tr(data))
                self.progressbar.configure(mode="indeterminate")
                self.progressbar.start()
            
            elif msg_type == "SUMMARY_DONE":
                self.progressbar.stop()
                self.progressbar.configure(mode="determinate")
                self.progressbar.set(1.0)

                self.current_summary_text = data
                self.analytics_textbox.configure(state="normal")
                self.analytics_textbox.delete("1.0", "end")
                
                # ИСПРАВЛЕНИЕ: Замена эмодзи на стандартный символ неизвестного знака ()
                safe_data = ''.join(c if ord(c) <= 0xFFFF else '\ufffd' for c in data)
                self.analytics_textbox.insert("1.0", safe_data)
                
                self.analytics_textbox.configure(state="disabled")
                
                self._reset_ui_state()
                self.btn_summary.configure(state="normal", text=self.tr("BTN_SUMMARY"))
                self.btn_tab_history.configure(state="normal")
                self.btn_tab_speakers.configure(state="normal")
            elif msg_type == "SUMMARY_ERROR":
                self.progressbar.stop()
                self.progressbar.configure(mode="determinate")
                self.progressbar.set(0.0)

                messagebox.showerror("Ошибка ШИ-Анализа", data)
                self._write_summary_placeholder()
                
                self._reset_ui_state()
                self.btn_summary.configure(state="normal", text=self.tr("BTN_SUMMARY"))
                self.btn_tab_history.configure(state="normal")
                self.btn_tab_speakers.configure(state="normal")
                
        if getattr(self, 'is_running', False): self.after(50, self._poll_queue)

    def _reset_ui_state(self):
        self.is_running = False
        self.btn_select.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.btn_settings.configure(state="normal")  
        self.switch_diarization.configure(state="normal")
        self.telemetry_label.configure(text="")
        self.status_label.configure(text=self.tr("STATUS_IDLE"))
        
        if self.transcribed_segments:
            self.btn_save.configure(state="normal")
            self.btn_summary.configure(state="normal")
            
        self.search_entry.delete(0, "end")
        self.search_count_label.configure(text=self.tr("SEARCH_FOUND") + "0")
        self._raw_textbox.tag_remove("search_highlight", "1.0", "end")
        self._raw_textbox.tag_remove("search_active_highlight", "1.0", "end")
        self.search_matches = []
        self.current_match_idx = -1

    def _on_save_dropdown_click(self, choice: str):
        if not self.current_audio_path or not self.transcribed_segments:
            messagebox.showwarning("Внимание", "Нет данных для сохранения!")
            self.btn_save.set(self.tr("BTN_SAVE_DEFAULT"))
            return
        base_name = os.path.splitext(os.path.basename(self.current_audio_path))[0]
        if choice == "Текст (.txt)":
            target_path = filedialog.asksaveasfilename(title="Сохранить транскрипт", initialfile=f"{base_name}_transcript", defaultextension=".txt", filetypes=[("Text Files", "*.txt")])
            if target_path: self._export_txt(target_path)
        elif choice == "Субтитры (.srt)":
            target_path = filedialog.asksaveasfilename(title="Сохранить субтитры SRT", initialfile=base_name, defaultextension=".srt", filetypes=[("SubRip Subtitles", "*.srt")])
            if target_path: self._export_srt(target_path)
        elif choice == "Субтитры (.vtt)":
            target_path = filedialog.asksaveasfilename(title="Сохранить субтитры VTT", initialfile=base_name, defaultextension=".vtt", filetypes=[("WebVTT Subtitles", "*.vtt")])
            if target_path: self._export_vtt(target_path)
        elif choice == "Данные JSON (.json)":
            target_path = filedialog.asksaveasfilename(title="Сохранить данные JSON", initialfile=base_name, defaultextension=".json", filetypes=[("JSON Data", "*.json")])
            if target_path: self._export_json(target_path)
        elif choice == "Таблица CSV (.csv)":
            target_path = filedialog.asksaveasfilename(title="Сохранить таблицу CSV", initialfile=base_name, defaultextension=".csv", filetypes=[("CSV Table", "*.csv")])
            if target_path: self._export_csv(target_path)
        self.btn_save.set(self.tr("BTN_SAVE_DEFAULT"))

    def _export_txt(self, target_path: str):
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                for start, end, text in self.transcribed_segments:
                    processed_text = text
                    if text.startswith("[") and "] " in text:
                        maybe_speaker, _, rest = text[1:].partition("] ")
                        if maybe_speaker.startswith("SPEAKER_"):
                            display_name = self.speaker_names_map.get(maybe_speaker, maybe_speaker)
                            processed_text = f"{display_name}: {rest}"
                    if self.show_time_var.get():
                        ui_time = f"{int(start)//3600:02d}:{int(start)%3600//60:02d}:{int(start)%60:02d}"
                        ui_end = f"{int(end)//3600:02d}:{int(end)%3600//60:02d}:{int(end)%60:02d}"
                        f.write(f"[{ui_time} -> {ui_end}] {processed_text}\n")
                    else: f.write(f"{processed_text}\n")
            self.system_log_ui(f"[+] Экспортирован текст: {os.path.basename(target_path)}")
        except Exception as e: messagebox.showerror("Ошибка", f"Не удалось сохранить TXT:\n{str(e)}")

    def _export_srt(self, target_path: str):
        try:
            with open(target_path, "w", encoding="utf-8-sig") as f:
                for i, (start, end, text) in enumerate(self.transcribed_segments, start=1):
                    processed_text = text
                    if text.startswith("[") and "] " in text:
                        maybe_speaker, _, rest = text[1:].partition("] ")
                        if maybe_speaker.startswith("SPEAKER_"):
                            display_name = self.speaker_names_map.get(maybe_speaker, maybe_speaker)
                            processed_text = f"{display_name}: {rest}"
                    srt_start = self.format_time(start, decimal_separator=",")
                    srt_end = self.format_time(end, decimal_separator=",")
                    f.write(f"{i}\n{srt_start} --> {srt_end}\n{processed_text}\n\n")
            self.system_log_ui(f"[+] Экспортированы субтитры SRT: {os.path.basename(target_path)}")
        except Exception as e: messagebox.showerror("Ошибка", f"Не удалось сохранить SRT:\n{str(e)}")

    def _export_vtt(self, target_path: str):
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                f.write("WEBVTT\n\n")
                for i, (start, end, text) in enumerate(self.transcribed_segments, start=1):
                    processed_text = text
                    if text.startswith("[") and "] " in text:
                        maybe_speaker, _, rest = text[1:].partition("] ")
                        if maybe_speaker.startswith("SPEAKER_"):
                            display_name = self.speaker_names_map.get(maybe_speaker, maybe_speaker)
                            processed_text = f"{display_name}: {rest}"
                    vtt_start = self.format_time(start, decimal_separator=".")
                    vtt_end = self.format_time(end, decimal_separator=".")
                    f.write(f"{i}\n{vtt_start} --> {vtt_end}\n{processed_text}\n\n")
            self.system_log_ui(f"[+] Экспортированы субтитры VTT: {os.path.basename(target_path)}")
        except Exception as e: messagebox.showerror("Ошибка", f"Не удалось сохранить VTT:\n{str(e)}")

    def _export_json(self, target_path: str):
        try:
            segments_data = []
            for i, (start, end, text) in enumerate(self.transcribed_segments):
                speaker_raw_id = None
                speaker_display_name = None
                processed_text = text
                if text.startswith("[") and "] " in text:
                    maybe_speaker, _, rest = text[1:].partition("] ")
                    if maybe_speaker.startswith("SPEAKER_"):
                        speaker_raw_id = maybe_speaker
                        speaker_display_name = self.speaker_names_map.get(maybe_speaker, maybe_speaker)
                        processed_text = rest
                segments_data.append({
                    "id": i, "start_seconds": round(start, 3), "end_seconds": round(end, 3),
                    "start_timecode": self.format_time(start, decimal_separator=","), "end_timecode": self.format_time(end, decimal_separator=","),
                    "speaker_raw_id": speaker_raw_id, "speaker_display_name": speaker_display_name, "text": processed_text
                })
            export_data = {
                "program": "Lexora v1.7.1", "export_timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "source_file": os.path.basename(self.current_audio_path) if self.current_audio_path else "unknown", "segments": segments_data
            }
            with open(target_path, "w", encoding="utf-8") as f: json.dump(export_data, f, ensure_ascii=False, indent=4)
            self.system_log_ui(f"[+] Экспортирован JSON: {os.path.basename(target_path)}")
        except Exception as e: messagebox.showerror("Ошибка", f"Не удалось сохранить JSON:\n{str(e)}")

    def _export_csv(self, target_path: str):
        try:
            with open(target_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(["ID", "Start_Seconds", "End_Seconds", "Start_Timecode", "End_Timecode", "Speaker_ID", "Speaker_Name", "Text"])
                for i, (start, end, text) in enumerate(self.transcribed_segments):
                    speaker_raw_id = ""
                    speaker_display_name = ""
                    processed_text = text
                    if text.startswith("[") and "] " in text:
                        maybe_speaker, _, rest = text[1:].partition("] ")
                        if maybe_speaker.startswith("SPEAKER_"):
                            speaker_raw_id = maybe_speaker
                            speaker_display_name = self.speaker_names_map.get(maybe_speaker, maybe_speaker)
                            processed_text = rest
                    writer.writerow([
                        i, round(start, 3), round(end, 3), self.format_time(start, decimal_separator=","), self.format_time(end, decimal_separator=","),
                        speaker_raw_id if speaker_raw_id else "", speaker_display_name if speaker_display_name else "", processed_text
                    ])
            self.system_log_ui(f"[+] Экспортирован CSV: {os.path.basename(target_path)}")
        except Exception as e: messagebox.showerror("Ошибка", f"Не удалось сохранить CSV:\n{str(e)}")

    def _cycle_language(self):
        langs = ["RU", "UK", "EN"]
        idx = langs.index(self.current_lang)
        self.current_lang = langs[(idx + 1) % len(langs)]
        
        self.btn_lang.configure(text=self.current_lang)
        self.btn_select.configure(text=self.tr("BTN_SELECT"))
        self.btn_stop.configure(text=self.tr("BTN_STOP"))
        self.btn_copy.configure(text=self.tr("BTN_COPY"))
        
        current_save_text = self.btn_save.get()
        default_texts = [LOCALIZATION_DATA[l]["BTN_SAVE_DEFAULT"] for l in langs]
        if current_save_text in default_texts:
            self.btn_save.set(self.tr("BTN_SAVE_DEFAULT"))
            
        self.btn_settings.configure(text=self.tr("BTN_SETTINGS"))
        self.switch_timecodes.configure(text=self.tr("SWITCH_TIMECODES"))
        self.switch_diarization.configure(text=self.tr("SWITCH_DIARIZATION"))
        
        if not self.transcribed_segments and not self.is_running:
            self.status_label.configure(text=self.tr("STATUS_IDLE"))
        elif self.is_running:
            status_text = getattr(self, 'current_status_text', 'Обработка...')
            if status_text.startswith("WORKER_TRANSCRIBE"):
                self.status_label.configure(text=f"{self.tr('WORKER_TRANSCRIBE')} {status_text.replace('WORKER_TRANSCRIBE', '').strip()}")
            else:
                self.status_label.configure(text=self.tr(status_text))
            
        self.search_entry.configure(placeholder_text=self.tr("SEARCH_PLACEHOLDER"))
        self.cards_empty_label.configure(text=self.tr("CARDS_EMPTY"))
        self.drop_zone.hint_label.configure(text=self.tr("DROP_ZONE"))
        
        self.btn_tab_speakers.configure(text=self.tr("TAB_SPEAKERS"))
        self.btn_tab_history.configure(text=self.tr("TAB_HISTORY"))
        self.btn_tab_analytics.configure(text=self.tr("TAB_ANALYTICS"))
        self.btn_summary.configure(text=self.tr("BTN_SUMMARY"))
        
        self._write_summary_placeholder()
        self._refresh_history_ui()
        self._execute_text_search()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = LexoraApp()
    app.mainloop()