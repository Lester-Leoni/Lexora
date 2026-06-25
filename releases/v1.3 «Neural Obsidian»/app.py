import os
import sys

# ==============================================================================
# ИЗОЛЯЦИЯ ПУТЕЙ И КОРРЕКТИРОВКА RUNTIME ДЛЯ PYINSTALLER & PORTABLE
# ==============================================================================
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
    _internal_path = os.path.join(application_path, "_internal")
    if _internal_path not in sys.path:
        sys.path.insert(0, _internal_path)
    os.environ["PATH"] = application_path + os.pathsep + os.environ["PATH"]
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

os.chdir(application_path)

import locale
locale.getpreferredencoding = lambda *args: 'utf-8'


def _crash_log_startup_failure():
    import traceback
    import datetime
    log_root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    log_path = os.path.join(log_root, "Lexora", "startup_crash.log")
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.datetime.now()}]\n{traceback.format_exc()}\n")
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            f"Lexora не удалось запустить.\nПодробности записаны в лог:\n{log_path}",
            "Lexora — ошибка запуска",
            0x10
        )
    except Exception:
        pass


def _init_cache_dir():
    primary = os.path.join(application_path, ".cache")
    try:
        os.makedirs(primary, exist_ok=True)
        probe = os.path.join(primary, ".write_test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return primary
    except OSError:
        fallback_root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        fallback = os.path.join(fallback_root, "Lexora", "cache")
        os.makedirs(fallback, exist_ok=True)
        return fallback


try:
    _local_cache_dir = _init_cache_dir()
    os.environ["HF_HOME"] = _local_cache_dir
    os.environ["TORCH_HOME"] = _local_cache_dir
    os.environ["XDG_CACHE_HOME"] = _local_cache_dir
    os.environ["HF_HUB_CACHE"] = _local_cache_dir

    import threading
    import gc
    import traceback
    import types
    import tempfile
    import subprocess
    import customtkinter as ctk
    from tkinter import filedialog, messagebox
    import torch
    from tkinterdnd2 import TkinterDnD, DND_FILES, COPY
    from faster_whisper import WhisperModel

    os.environ["HF_HUB_OFFLINE"] = "1"

    sys.modules["k2"] = types.ModuleType("k2")

    import speechbrain.utils.fetching
    import speechbrain.inference.interfaces

    _original_fetch = speechbrain.utils.fetching.fetch

    def _direct_local_fetch(filename, source, *args, **kwargs):
        if isinstance(source, str) and os.path.isdir(source):
            local_file = os.path.join(source, filename)
            if os.path.exists(local_file):
                return local_file
        return _original_fetch(filename, source, *args, **kwargs)

    speechbrain.utils.fetching.fetch = _direct_local_fetch

    original_pretrained_from_hparams = speechbrain.inference.interfaces.pretrained_from_hparams

    def patched_pretrained_from_hparams(*args, **kwargs):
        kwargs.pop("use_auth_token", None)
        kwargs.pop("revision", None)

        if "run_opts" in kwargs and kwargs["run_opts"] is not None:
            if "device" in kwargs["run_opts"]:
                if isinstance(kwargs["run_opts"]["device"], torch.device):
                    kwargs["run_opts"]["device"] = str(kwargs["run_opts"]["device"])

        return original_pretrained_from_hparams(*args, **kwargs)

    speechbrain.inference.interfaces.pretrained_from_hparams = patched_pretrained_from_hparams

    _original_from_hparams = speechbrain.inference.interfaces.Pretrained.from_hparams

    @classmethod
    def _patched_from_hparams(cls, *args, **kwargs):
        kwargs.pop('use_auth_token', None)
        return _original_from_hparams.__func__(cls, *args, **kwargs)

    speechbrain.inference.interfaces.Pretrained.from_hparams = _patched_from_hparams

    # ==========================================================================
    # ФИКС: speechbrain LazyModule — ложное срабатывание lazy-импорта на Windows
    # ==========================================================================
    import inspect
    import speechbrain.utils.importutils

    _sb_importutils = speechbrain.utils.importutils
    _original_ensure_module = _sb_importutils.LazyModule.ensure_module

    def _patched_ensure_module(self, stacklevel):
        try:
            _importer_frame = inspect.getframeinfo(sys._getframe(stacklevel + 1))
            if os.path.basename(_importer_frame.filename) == "inspect.py":
                raise AttributeError()
        except AttributeError:
            raise
        except Exception:
            pass
        return _original_ensure_module(self, stacklevel)

    _sb_importutils.LazyModule.ensure_module = _patched_ensure_module

    from pyannote.audio import Pipeline

except Exception:
    _crash_log_startup_failure()
    sys.exit(1)

# ==============================================================================
# ВИЗУАЛЬНАЯ СИСТЕМА "NEURAL OBSIDIAN"
# ==============================================================================

THEME_NEURAL_OBSIDIAN = {
    "window_bg":  ("#FFFFFF", "#0A0A0C"),
    "frame_bg":   ("#F2F2F4", "#13131A"),
    "card_bg":    ("#FFFFFF", "#1A1D21"),
    "cyan_neon":  ("#0089A0", "#00F0FF"),
    "cyan_dim":   ("#9FD6DC", "#0F4C56"),
    "navy_card":  ("#DCEAF2", "#003366"),
    "text_main":  ("#101014", "#F0F0F0"),
    "text_dim":   ("#5A5A60", "#9A9AA2"),
}

CORNER_RADIUS_DEFAULT = 12
CORNER_RADIUS_DROPZONE = 16
BORDER_WIDTH_DEFAULT = 2

FONT_DIR = os.path.join(application_path, "fonts")
for _font_file in ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf", "consola.ttf"):
    _font_path = os.path.join(FONT_DIR, _font_file)
    if os.path.exists(_font_path):
        ctk.FontManager.load_font(_font_path)

FONT_BODY = None
FONT_BODY_MED = None
FONT_HEADING = None
FONT_SMALL = None
FONT_MONO = None
FONT_MONO_BOLD = None


def _init_fonts():
    global FONT_BODY, FONT_BODY_MED, FONT_HEADING, FONT_SMALL, FONT_MONO, FONT_MONO_BOLD
    FONT_BODY = ctk.CTkFont(family="Inter", size=14)
    FONT_BODY_MED = ctk.CTkFont(family="Inter", size=13, weight="bold")
    FONT_HEADING = ctk.CTkFont(family="Inter", size=18, weight="bold")
    FONT_SMALL = ctk.CTkFont(family="Inter", size=12)
    FONT_MONO = ctk.CTkFont(family="Consolas", size=13)
    FONT_MONO_BOLD = ctk.CTkFont(family="Consolas", size=13, weight="bold")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

WHISPER_MODEL_PATH = os.path.join(application_path, "model_weights", "medium")
DIARIZATION_CONFIG_PATH = os.path.join(application_path, "model_weights", "diarization", "config.yaml")
FFMPEG_PATH = os.path.join(application_path, "ffmpeg.exe")

SPEAKER_PALETTE = [
    THEME_NEURAL_OBSIDIAN["cyan_neon"],
    THEME_NEURAL_OBSIDIAN["navy_card"],
    ("#B98A2E", "#E5A23A"),
    ("#7A4FB5", "#9D6FE0"),
]


def speaker_color(speaker_id: str):
    try:
        idx = int(str(speaker_id).split("_")[-1])
    except (ValueError, IndexError):
        idx = 0
    return SPEAKER_PALETTE[idx % len(SPEAKER_PALETTE)]


class SpeakerCard(ctk.CTkFrame):
    """Карточка идентификации спикера — спец. 3.4 Инструкции.

    Модифицирована для поддержки In-place редактирования имени через ctk.CTkEntry.
    """

    def __init__(self, master, speaker_id: str, speak_seconds: float, total_seconds: float, current_name: str, on_rename_callback, **kwargs):
        super().__init__(
            master,
            corner_radius=CORNER_RADIUS_DEFAULT,
            fg_color=THEME_NEURAL_OBSIDIAN["card_bg"],
            border_width=1,
            border_color=THEME_NEURAL_OBSIDIAN["cyan_dim"],
            **kwargs,
        )
        self.speaker_id = speaker_id
        color = speaker_color(speaker_id)
        share = 0.0 if total_seconds <= 0 else min(speak_seconds / total_seconds, 1.0)

        self.grid_columnconfigure(1, weight=1)

        self.badge = ctk.CTkLabel(
            self, text=str(speaker_id).replace("SPEAKER_", "S"),
            width=36, height=36, corner_radius=18,
            fg_color=color, text_color="#000000",
            font=FONT_BODY_MED,
        )
        self.badge.grid(row=0, column=0, rowspan=2, padx=(12, 10), pady=12)

        # Поле ввода вместо статического CTkLabel для интуитивного переименования на месте
        self.name_entry = ctk.CTkEntry(
            self,
            font=FONT_BODY_MED,
            fg_color="transparent",
            border_width=0,
            text_color=THEME_NEURAL_OBSIDIAN["text_main"],
            corner_radius=4
        )
        self.name_entry.insert(0, current_name)
        self.name_entry.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(12, 0))

        # Навешивание обработчиков событий: подтверждение ввода (Enter) и потеря фокуса
        self.name_entry.bind("<Return>", lambda event: on_rename_callback(self.speaker_id))
        self.name_entry.bind("<FocusOut>", lambda event: on_rename_callback(self.speaker_id))

        ctk.CTkLabel(
            self, text=f"{speak_seconds:.0f} сек · {share * 100:.0f}% эфира", anchor="w",
            text_color=THEME_NEURAL_OBSIDIAN["text_dim"], font=FONT_SMALL,
        ).grid(row=1, column=1, sticky="w", padx=(0, 12), pady=(0, 10))

        track = ctk.CTkFrame(self, height=6, corner_radius=3, fg_color=THEME_NEURAL_OBSIDIAN["frame_bg"])
        track.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12))
        ctk.CTkFrame(track, height=6, corner_radius=3, fg_color=color).place(
            relx=0, rely=0, relwidth=max(share, 0.03), relheight=1
        )

    def set_active(self, is_active: bool):
        if is_active:
            self.configure(border_color=THEME_NEURAL_OBSIDIAN["cyan_neon"], border_width=2)
        else:
            self.configure(border_color=THEME_NEURAL_OBSIDIAN["cyan_dim"], border_width=1)


class DropZone(ctk.CTkFrame):
    """Зона drag-and-drop — спец. 3.2 Инструкции."""

    def __init__(self, master, on_file_dropped, **kwargs):
        super().__init__(
            master,
            corner_radius=CORNER_RADIUS_DROPZONE,
            border_width=BORDER_WIDTH_DEFAULT,
            border_color=THEME_NEURAL_OBSIDIAN["cyan_dim"],
            fg_color=THEME_NEURAL_OBSIDIAN["frame_bg"],
            **kwargs,
        )
        self.on_file_dropped = on_file_dropped
        self._idle_text = "Перетащите аудио/видео файл сюда\nили нажмите, чтобы выбрать"

        self.icon_label = ctk.CTkLabel(self, text="⇪", font=ctk.CTkFont(size=30),
                                        text_color=THEME_NEURAL_OBSIDIAN["cyan_neon"])
        self.icon_label.pack(pady=(26, 4))
        self.hint_label = ctk.CTkLabel(self, text=self._idle_text, font=FONT_SMALL,
                                        text_color=THEME_NEURAL_OBSIDIAN["text_dim"])
        self.hint_label.pack(pady=(0, 26))

        for widget in (self, self.icon_label, self.hint_label):
            widget.bind("<Button-1>", self._on_click)

        self.drop_target_register(DND_FILES)
        self.dnd_bind("<<DropEnter>>", self._on_enter)
        self.dnd_bind("<<DropPosition>>", lambda event: COPY)
        self.dnd_bind("<<DropLeave>>", self._on_leave)
        self.dnd_bind("<<Drop>>", self._on_drop)

    def _on_click(self, event):
        filepath = filedialog.askopenfilename(
            title="Выберите аудио/видео файл",
            filetypes=[("Media Files", "*.mp3 *.wav *.m4a *.mp4 *.mkv"), ("All Files", "*.*")]
        )
        if filepath:
            self.on_file_dropped(filepath)

    def _on_enter(self, event):
        self.configure(border_color=THEME_NEURAL_OBSIDIAN["cyan_neon"], border_width=BORDER_WIDTH_DEFAULT + 1)
        self.hint_label.configure(text="Отпустите файл для загрузки")
        return COPY

    def _on_leave(self, event):
        self.configure(border_color=THEME_NEURAL_OBSIDIAN["cyan_dim"], border_width=BORDER_WIDTH_DEFAULT)
        self.hint_label.configure(text=self._idle_text)

    def _on_drop(self, event):
        self._on_leave(event)
        files = self.tk.splitlist(event.data)
        if files:
            self.on_file_dropped(files[0])
        return COPY


class DotMatrixProgressBar(ctk.CTkFrame):
    """Буквальная точечная сетка прогресса — Canvas-вариант."""

    def __init__(self, master, dot_count: int = 28, dot_size: int = 8, gap: int = 4, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.dot_count = dot_count
        self.dot_size = dot_size
        self.gap = gap
        width = dot_count * (dot_size + gap) - gap
        self.canvas = ctk.CTkCanvas(
            self, width=width, height=dot_size, highlightthickness=0,
            bg=self._apply_appearance_mode(THEME_NEURAL_OBSIDIAN["frame_bg"]),
        )
        self.canvas.pack()
        self._dots = []
        for i in range(dot_count):
            x0 = i * (dot_size + gap)
            dot = self.canvas.create_rectangle(
                x0, 0, x0 + dot_size, dot_size,
                fill=self._apply_appearance_mode(THEME_NEURAL_OBSIDIAN["cyan_dim"]),
                outline="",
            )
            self._dots.append(dot)

    def set(self, fraction: float):
        fraction = max(0.0, min(1.0, fraction))
        filled = round(fraction * self.dot_count)
        for i, dot in enumerate(self._dots):
            color_key = "cyan_neon" if i < filled else "cyan_dim"
            self.canvas.itemconfig(dot, fill=self._apply_appearance_mode(THEME_NEURAL_OBSIDIAN[color_key]))


class DiarizationProgressHook:
    """Hook для pyannote.audio.Pipeline.__call__(file, hook=...) — спец. 3.3."""

    STEP_LABELS = {
        "segmentation": "Поиск речевых сегментов",
        "speaker_counting": "Оценка количества спикеров",
        "embeddings": "Извлечение голосовых отпечатков",
        "discrete_diarization": "Финальная кластеризация",
    }

    STEP_WEIGHTS = {
        "segmentation": (0.00, 0.15),
        "speaker_counting": (0.15, 0.20),
        "embeddings": (0.20, 0.85),
        "discrete_diarization": (0.85, 1.00),
    }

    def __init__(self, app, start_fraction: float = 0.0, end_fraction: float = 1.0):
        self.app = app
        self.start_fraction = start_fraction
        self.end_fraction = end_fraction

    def __call__(self, step_name, step_artifact, file=None, total=None, completed=None):
        label = self.STEP_LABELS.get(step_name, step_name)
        lo, hi = self.STEP_WEIGHTS.get(step_name, (0.0, 1.0))
        if total and completed is not None and total > 0:
            local_fraction = completed / total
            text = f"{label} ({completed}/{total})"
        else:
            local_fraction = 1.0
            text = label
        phase_fraction = lo + (hi - lo) * local_fraction
        span = self.end_fraction - self.start_fraction
        global_fraction = self.start_fraction + span * phase_fraction
        self.app.after(0, self.app.update_diarization_progress, text, global_fraction)


class DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)


class LexoraApp(DnDCTk):
    def __init__(self):
        super().__init__()
        _init_fonts()
        self.title("Lexora")
        self.geometry("960x680")
        self.minsize(820, 600)
        self.resizable(True, True)
        self.configure(fg_color=THEME_NEURAL_OBSIDIAN["window_bg"])

        self.transcribed_segments = []
        self.speaker_cards = {}
        self.current_audio_path = None
        self.is_running = False

        # Хранилища для отслеживания динамического переименования спикеров
        self.speaker_names_map = {}
        self.speaker_entries = {}

        self.show_time_var = ctk.BooleanVar(value=True)
        self.use_roles_var = ctk.BooleanVar(value=False)

        # -------------------- верхняя панель управления --------------------
        self.top_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.top_frame.pack(pady=(14, 8), padx=14, fill="x")

        self.btn_select = ctk.CTkButton(
            self.top_frame, text="Выбрать файл", font=FONT_BODY_MED,
            fg_color=THEME_NEURAL_OBSIDIAN["cyan_neon"], text_color="#000000",
            hover_color=THEME_NEURAL_OBSIDIAN["cyan_dim"], corner_radius=CORNER_RADIUS_DEFAULT,
            command=self.start_processing,
        )
        self.btn_select.pack(side="left", padx=5)

        self.btn_stop = ctk.CTkButton(
            self.top_frame, text="Стоп", font=FONT_BODY_MED,
            fg_color="#c93434", hover_color="#a32a2a", corner_radius=CORNER_RADIUS_DEFAULT,
            state="disabled", command=self.stop_processing,
        )
        self.btn_stop.pack(side="left", padx=5)

        self.btn_copy = ctk.CTkButton(
            self.top_frame, text="Копировать", font=FONT_BODY,
            fg_color=THEME_NEURAL_OBSIDIAN["frame_bg"], text_color=THEME_NEURAL_OBSIDIAN["text_main"],
            hover_color=THEME_NEURAL_OBSIDIAN["card_bg"], corner_radius=CORNER_RADIUS_DEFAULT,
            command=self.copy_text,
        )
        self.btn_copy.pack(side="left", padx=5)

        self.switch_timecodes = ctk.CTkSwitch(
            self.top_frame, text="Таймкоды", font=FONT_SMALL,
            progress_color=THEME_NEURAL_OBSIDIAN["cyan_neon"],
            variable=self.show_time_var, command=self.redraw_interface,
        )
        self.switch_timecodes.pack(side="right", padx=10)

        self.switch_diarization = ctk.CTkSwitch(
            self.top_frame, text="Диалог (Роли)", font=FONT_SMALL,
            progress_color=THEME_NEURAL_OBSIDIAN["cyan_neon"],
            variable=self.use_roles_var,
        )
        self.switch_diarization.pack(side="right", padx=10)

        # -------------------- зона загрузки (DropZone, спец. 3.2) --------------------
        self.drop_zone = DropZone(self, on_file_dropped=self.start_processing, height=120)
        self.drop_zone.pack(padx=14, pady=(0, 10), fill="x")

        # -------------------- статус и прогресс (спец. 3.3) --------------------
        status_frame = ctk.CTkFrame(self, fg_color="transparent")
        status_frame.pack(padx=14, pady=(0, 10), fill="x")

        self.status_label = ctk.CTkLabel(
            status_frame, text="Ожидание файла", font=FONT_SMALL, anchor="w",
            text_color=THEME_NEURAL_OBSIDIAN["text_dim"],
        )
        self.status_label.pack(fill="x")

        self.progressbar = ctk.CTkProgressBar(
            status_frame, mode="determinate",
            progress_color=THEME_NEURAL_OBSIDIAN["cyan_neon"],
            fg_color=THEME_NEURAL_OBSIDIAN["frame_bg"],
            corner_radius=CORNER_RADIUS_DEFAULT // 2,
        )
        self.progressbar.pack(pady=(4, 0), fill="x")
        self.progressbar.set(0)

        # -------------------- основная рабочая область --------------------
        body_frame = ctk.CTkFrame(self, fg_color="transparent")
        body_frame.pack(padx=14, pady=(0, 14), fill="both", expand=True)
        body_frame.grid_columnconfigure(0, weight=3)
        body_frame.grid_columnconfigure(1, weight=1)
        body_frame.grid_rowconfigure(0, weight=1)

        # -- транскрипт (спец. 3.6) --
        self.textbox = ctk.CTkTextbox(
            body_frame, state="disabled", font=FONT_MONO,
            fg_color=THEME_NEURAL_OBSIDIAN["window_bg"],
            text_color=THEME_NEURAL_OBSIDIAN["text_main"],
            corner_radius=CORNER_RADIUS_DEFAULT,
        )
        self.textbox.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        self._raw_textbox = self.textbox._textbox
        self._raw_textbox.tag_config("ts", foreground=self._fg("text_dim"))
        self._raw_textbox.tag_config("spk", foreground=self._fg("cyan_neon"), font=("Consolas", 13, "bold"))
        self._raw_textbox.tag_config("seg_hover", background=self._fg("frame_bg"))

        # -- панель карточек спикеров (спец. 3.4) --
        cards_outer = ctk.CTkFrame(body_frame, fg_color=THEME_NEURAL_OBSIDIAN["frame_bg"],
                                    corner_radius=CORNER_RADIUS_DEFAULT)
        cards_outer.grid(row=0, column=1, sticky="nsew")
        ctk.CTkLabel(cards_outer, text="СПИКЕРЫ", font=FONT_SMALL,
                     text_color=THEME_NEURAL_OBSIDIAN["text_dim"]).pack(anchor="w", padx=14, pady=(12, 4))

        self.cards_panel = ctk.CTkScrollableFrame(
            cards_outer, fg_color="transparent",
        )
        self.cards_panel.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.cards_empty_label = ctk.CTkLabel(
            self.cards_panel, text="Появятся после диаризации", font=FONT_SMALL,
            text_color=THEME_NEURAL_OBSIDIAN["text_dim"], wraplength=160,
        )
        self.cards_empty_label.pack(pady=20)

    # -------------------- утилиты темы --------------------
    def _fg(self, theme_key: str) -> str:
        light, dark = THEME_NEURAL_OBSIDIAN[theme_key]
        return dark if ctk.get_appearance_mode() == "Dark" else light

    # -------------------- прогресс/статус --------------------
    def update_diarization_progress(self, text: str, fraction: float):
        self.status_label.configure(text=text)
        self.progressbar.set(fraction)

    def format_time(self, seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def redraw_interface(self):
        """Очищает и полностью обновляет текстовое окно с подстановкой актуальных имен из карты маппинга."""
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        for idx, (start, end, text) in enumerate(self.transcribed_segments):
            self._insert_segment_line(idx, start, end, text)
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def _insert_segment_line(self, idx, start, end, text):
        """Вставляет строку сегмента, динамически заменяя технические ID спикеров на кастомные."""
        seg_tag = f"seg_{idx}"
        if self.show_time_var.get():
            self.textbox.insert("end", f"[{self.format_time(start)} -> {self.format_time(end)}] ", ("ts", seg_tag))

        speaker_label = None
        body_text = text
        if text.startswith("[") and "] " in text:
            maybe_speaker, _, rest = text[1:].partition("] ")
            if maybe_speaker.startswith("SPEAKER_"):
                speaker_label = maybe_speaker
                body_text = rest

        if speaker_label:
            # Если спикер переименован, берем измененное имя пользователя из словаря
            display_name = self.speaker_names_map.get(speaker_label, speaker_label)
            self.textbox.insert("end", f"{display_name}: ", ("spk", seg_tag))
        self.textbox.insert("end", f"{body_text}\n", (seg_tag,))

        if speaker_label:
            self._raw_textbox.tag_bind(seg_tag, "<Button-1>",
                                        lambda e, spk=speaker_label: self._on_transcript_segment_click(spk))

    def _on_transcript_segment_click(self, speaker_id: str):
        for sid, card in self.speaker_cards.items():
            card.set_active(sid == speaker_id)

    def append_segment_ui(self, start, end, text):
        idx = len(self.transcribed_segments)
        self.transcribed_segments.append((start, end, text))
        self.textbox.configure(state="normal")
        self._insert_segment_line(idx, start, end, text)
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

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

    def stop_processing(self):
        if self.is_running:
            self.is_running = False
            self.system_log_ui("\n[!] Остановка процесса по команде пользователя...")
            self.btn_select.configure(state="normal")
            self.btn_stop.configure(state="disabled")

    def start_processing(self, filepath=None):
        if self.is_running:
            messagebox.showwarning("Внимание", "Дождитесь окончания текущей транскрибации!")
            return

        if not filepath:
            filepath = filedialog.askopenfilename(
                title="Выберите аудио/видео файл",
                filetypes=[("Media Files", "*.mp3 *.wav *.m4a *.mp4 *.mkv"), ("All Files", "*.*")]
            )
        if not filepath:
            return

        self.current_audio_path = filepath
        self.transcribed_segments.clear()
        self.is_running = True

        use_diarization = self.use_roles_var.get()

        self.btn_select.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.switch_diarization.configure(state="disabled")

        self._clear_speaker_cards()

        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")
        self.progressbar.configure(mode="determinate")
        self.progressbar.set(0)
        self.status_label.configure(text=f"Выбран файл: {os.path.basename(filepath)}")

        threading.Thread(target=self.process_audio, args=(filepath, use_diarization), daemon=True).start()

    def _clear_speaker_cards(self):
        for card in self.speaker_cards.values():
            card.destroy()
        self.speaker_cards.clear()
        self.speaker_entries.clear()
        self.speaker_names_map.clear()  # Полная очистка словаря соответствий при инициализации новой сессии
        self.cards_empty_label.pack(pady=20)

    def _populate_speaker_cards(self, diarization_result):
        durations = {}
        for turn, _, speaker in diarization_result.itertracks(yield_label=True):
            durations[speaker] = durations.get(speaker, 0.0) + (turn.end - turn.start)

        if not durations:
            return

        self.cards_empty_label.pack_forget()
        total = sum(durations.values())
        
        self.speaker_entries.clear()
        
        for speaker in sorted(durations.keys()):
            if speaker not in self.speaker_names_map:
                self.speaker_names_map[speaker] = speaker

            current_display_name = self.speaker_names_map[speaker]

            # Создание карточки с передачей текущего имени и обратного колбэка
            card = SpeakerCard(
                self.cards_panel, 
                speaker, 
                durations[speaker], 
                total, 
                current_display_name,
                self._on_speaker_renamed
            )
            card.pack(fill="x", padx=4, pady=4)
            self.speaker_cards[speaker] = card
            self.speaker_entries[speaker] = card.name_entry

    def _on_speaker_renamed(self, speaker_id: str):
        """Callback-приемник событий <Return> и <FocusOut> от полей ввода SpeakerCard.
        
        Обновляет карту имен, инициирует сквозную перезапись текстового поля и файла.
        """
        entry = self.speaker_entries.get(speaker_id)
        if not entry:
            return

        new_name = entry.get().strip()
        
        # Если имя стерто пользователем, принудительно возвращаем технический ID
        if not new_name:
            new_name = speaker_id
            entry.delete(0, "end")
            entry.insert(0, speaker_id)

        # Если имя не изменилось, завершаем выполнение для экономии ресурсов
        if self.speaker_names_map.get(speaker_id) == new_name:
            return

        self.speaker_names_map[speaker_id] = new_name

        # Мягкий визуальный фидбек: кратковременная рамка циана вокруг поля ввода
        entry.configure(border_width=1, border_color=self._fg("cyan_neon"))
        self.after(400, lambda: entry.configure(border_width=0))

        # Перерисовка основного UI с сохранением текущего положения прокрутки
        current_scroll = self.textbox.yview()
        self.redraw_interface()
        self.textbox.yview_moveto(current_scroll[0])
        
        # Реактивное обновление финального файла результатов
        self.save_to_file()

    def _convert_to_wav(self, input_file):
        temp_fd, temp_path = tempfile.mkstemp(suffix=".wav")
        os.close(temp_fd)

        command = [
            FFMPEG_PATH, "-y", "-i", input_file,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            temp_path
        ]

        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo, check=True)
        return temp_path

    def process_audio(self, audio_file, use_diarization):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        whisper_model = None
        diarize_model = None
        temp_wav_path = None
        diarization_result = None

        try:
            self.after(0, self.update_diarization_progress, "Конвертация аудио (FFmpeg)...", 0.02)
            temp_wav_path = self._convert_to_wav(audio_file)
            audio_file = temp_wav_path

            self.after(0, self.system_log_ui, f"[*] Инициализация оборудования: {device.upper()}")

            if use_diarization:
                self.after(0, self.update_diarization_progress, "Загрузка модели Pyannote...", 0.04)
                try:
                    diarize_model = Pipeline.from_pretrained(DIARIZATION_CONFIG_PATH)
                    if device == "cuda":
                        diarize_model.to(torch.device("cuda"))
                except Exception as e:
                    self.after(0, self.system_log_ui, f"\n[-] ОШИБКА ИНИЦИАЛИЗАЦИИ PYANNOTE:\n{str(e)}")
                    self.is_running = False
                    return

            if not self.is_running:
                return

            self.after(0, self.update_diarization_progress, "Загрузка модели Whisper...", 0.06)
            whisper_model = WhisperModel(WHISPER_MODEL_PATH, device=device, compute_type="float16" if device == "cuda" else "int8")

            if not self.is_running:
                return

            self.after(0, self.system_log_ui, "\n[*] Транскрибация аудио:")
            segments, info = whisper_model.transcribe(audio_file, beam_size=5)
            duration = info.duration

            transcribe_budget = 0.35 if use_diarization else 0.94
            for segment in segments:
                if not self.is_running:
                    break
                self.after(0, self.append_segment_ui, segment.start, segment.end, segment.text.strip())
                local_fraction = min(segment.end / duration, 1.0) if duration else 1.0
                self.after(0, self.update_diarization_progress,
                           f"Транскрибация ({self.format_time(segment.end)} / {self.format_time(duration)})",
                           0.06 + transcribe_budget * local_fraction)

            if not self.is_running:
                return
            self.after(0, self.system_log_ui, "\n[+] Транскрибация завершена.")

            if use_diarization and diarize_model:
                self.after(0, self.system_log_ui, "\n[*] Запуск разделения по ролям (Pyannote)...")
                diarization_start_fraction = 0.06 + transcribe_budget
                hook = DiarizationProgressHook(self, start_fraction=diarization_start_fraction, end_fraction=1.0)
                diarization_result = diarize_model(audio_file, hook=hook)

                if not self.is_running:
                    return

                final_segments = []
                for start, end, text in self.transcribed_segments:
                    max_overlap = 0
                    best_speaker = "UNKNOWN"
                    for turn, _, speaker in diarization_result.itertracks(yield_label=True):
                        overlap = min(end, turn.end) - max(start, turn.start)
                        if overlap > max_overlap:
                            max_overlap = overlap
                            best_speaker = speaker

                    speaker_prefix = f"[{best_speaker}] " if best_speaker != "UNKNOWN" else ""
                    final_segments.append((start, end, speaker_prefix + text))

                self.transcribed_segments = final_segments
                self.after(0, self.system_log_ui, "[+] Разделение ролей завершено. Обновление интерфейса...\n")
                self.after(0, self.redraw_interface)
                self.after(0, self._populate_speaker_cards, diarization_result)

            if self.is_running:
                self.after(0, self.update_diarization_progress, "Готово", 1.0)
                self.save_to_file()

        except Exception:
            self.after(0, self.system_log_ui, f"\n[-] КРИТИЧЕСКАЯ ОШИБКА:\n{traceback.format_exc()}")

        finally:
            self.is_running = False
            del whisper_model
            del diarize_model
            gc.collect()
            if device == "cuda":
                torch.cuda.empty_cache()

            if temp_wav_path and os.path.exists(temp_wav_path):
                try:
                    os.remove(temp_wav_path)
                except Exception:
                    pass

            def reset_ui():
                self.btn_select.configure(state="normal")
                self.btn_stop.configure(state="disabled")
                self.switch_diarization.configure(state="normal")
            self.after(0, reset_ui)

    def save_to_file(self):
        """Экспортирует итоговый файл транскрипции на диск, подставляя пользовательские имена из маппинга."""
        if not self.current_audio_path or not self.transcribed_segments:
            return
        output_txt = os.path.splitext(self.current_audio_path)[0] + "_transcript.txt"
        try:
            with open(output_txt, "w", encoding="utf-8") as f:
                for start, end, text in self.transcribed_segments:
                    processed_text = text
                    if text.startswith("[") and "] " in text:
                        maybe_speaker, _, rest = text[1:].partition("] ")
                        if maybe_speaker.startswith("SPEAKER_"):
                            display_name = self.speaker_names_map.get(maybe_speaker, maybe_speaker)
                            processed_text = f"{display_name}: {rest}"

                    if self.show_time_var.get():
                        f.write(f"[{self.format_time(start)} -> {self.format_time(end)}] {processed_text}\n")
                    else:
                        f.write(f"{processed_text}\n")
            self.after(0, self.system_log_ui, f"\n[+] Сохранено: {output_txt}")
        except Exception as e:
            self.after(0, self.system_log_ui, f"\n[-] Ошибка保存: {str(e)}")


if __name__ == "__main__":
    app = LexoraApp()
    app.mainloop()