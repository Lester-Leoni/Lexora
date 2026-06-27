import os
import sys
import customtkinter as ctk
from tkinter import filedialog
from tkinterdnd2 import DND_FILES, COPY
from bootstrap import application_path

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

def init_fonts():
    global FONT_BODY, FONT_BODY_MED, FONT_HEADING, FONT_SMALL, FONT_MONO, FONT_MONO_BOLD
    FONT_BODY = ctk.CTkFont(family="Inter", size=14)
    FONT_BODY_MED = ctk.CTkFont(family="Inter", size=13, weight="bold")
    FONT_HEADING = ctk.CTkFont(family="Inter", size=18, weight="bold")
    FONT_SMALL = ctk.CTkFont(family="Inter", size=12)
    FONT_MONO = ctk.CTkFont(family="Consolas", size=13)
    FONT_MONO_BOLD = ctk.CTkFont(family="Consolas", size=13, weight="bold")

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


class VadSettingsWindow(ctk.CTkToplevel):
    """Интерактивное графическое окно тонкой ручной калибровки ИИ-движка (VAD)"""
    def __init__(self, master, current_config, on_save_callback):
        super().__init__(master)
        self.on_save_callback = on_save_callback
        
        self.title("Калибровка ИИ-фильтров VAD")
        self.geometry("480x420")
        self.resizable(False, False)
        self.configure(fg_color=THEME_NEURAL_OBSIDIAN["window_bg"])
        self.transient(master)
        self.grab_set()

        import copy
        self.config = copy.deepcopy(current_config)

        self.update_idletasks()
        x = master.winfo_x() + (master.winfo_width() // 2) - (480 // 2)
        y = master.winfo_y() + (master.winfo_height() // 2) - (420 // 2)
        self.geometry(f"+{x}+{y}")

        main_frame = ctk.CTkFrame(self, fg_color=THEME_NEURAL_OBSIDIAN["frame_bg"], corner_radius=CORNER_RADIUS_DEFAULT)
        main_frame.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(main_frame, text="Калибровка детектора активности голоса", font=FONT_HEADING, text_color=THEME_NEURAL_OBSIDIAN["cyan_neon"]).pack(pady=(14, 14))

        # Слайдер 1: Порог чувствительности (Threshold)
        frame_onset = ctk.CTkFrame(main_frame, fg_color=THEME_NEURAL_OBSIDIAN["card_bg"], corner_radius=8)
        frame_onset.pack(fill="x", padx=14, pady=6)
        
        self.lbl_thresh = ctk.CTkLabel(frame_onset, text="Порог активации: 0.50", font=FONT_BODY_MED, text_color=THEME_NEURAL_OBSIDIAN["text_main"])
        self.lbl_thresh.pack(anchor="w", padx=14, pady=(8, 0))
        
        self.slider_thresh = ctk.CTkSlider(frame_onset, from_=0.1, to=0.9, number_of_steps=16, progress_color=THEME_NEURAL_OBSIDIAN["cyan_neon"], button_color=THEME_NEURAL_OBSIDIAN["cyan_neon"], command=self._update_thresh)
        self.slider_thresh.pack(fill="x", padx=14, pady=10)
        
        self.hint_thresh = ctk.CTkLabel(frame_onset, text="Стандартные настройки", font=FONT_SMALL, text_color=THEME_NEURAL_OBSIDIAN["text_dim"])
        self.hint_thresh.pack(anchor="w", padx=14, pady=(0, 8))

        # Слайдер 2: Минимальная пауза (min_duration_off)
        frame_off = ctk.CTkFrame(main_frame, fg_color=THEME_NEURAL_OBSIDIAN["card_bg"], corner_radius=8)
        frame_off.pack(fill="x", padx=14, pady=6)
        
        self.lbl_off = ctk.CTkLabel(frame_off, text="Минимальная пауза: 0.50с", font=FONT_BODY_MED, text_color=THEME_NEURAL_OBSIDIAN["text_main"])
        self.lbl_off.pack(anchor="w", padx=14, pady=(8, 0))
        
        self.slider_off = ctk.CTkSlider(frame_off, from_=0.1, to=3.0, number_of_steps=29, progress_color=THEME_NEURAL_OBSIDIAN["cyan_neon"], button_color=THEME_NEURAL_OBSIDIAN["cyan_neon"], command=self._update_off)
        self.slider_off.pack(fill="x", padx=14, pady=10)
        
        self.hint_off = ctk.CTkLabel(frame_off, text="Стандартные настройки", font=FONT_SMALL, text_color=THEME_NEURAL_OBSIDIAN["text_dim"])
        self.hint_off.pack(anchor="w", padx=14, pady=(0, 8))

        # Слайдер 3: Минимальный звук (min_duration_on)
        frame_on = ctk.CTkFrame(main_frame, fg_color=THEME_NEURAL_OBSIDIAN["card_bg"], corner_radius=8)
        frame_on.pack(fill="x", padx=14, pady=6)
        
        self.lbl_on = ctk.CTkLabel(frame_on, text="Фильтр коротких звуков: 0.20с", font=FONT_BODY_MED, text_color=THEME_NEURAL_OBSIDIAN["text_main"])
        self.lbl_on.pack(anchor="w", padx=14, pady=(8, 0))
        
        self.slider_on = ctk.CTkSlider(frame_on, from_=0.05, to=1.5, number_of_steps=29, progress_color=THEME_NEURAL_OBSIDIAN["cyan_neon"], button_color=THEME_NEURAL_OBSIDIAN["cyan_neon"], command=self._update_on)
        self.slider_on.pack(fill="x", padx=14, pady=10)
        
        self.hint_on = ctk.CTkLabel(frame_on, text="Стандартные настройки", font=FONT_SMALL, text_color=THEME_NEURAL_OBSIDIAN["text_dim"])
        self.hint_on.pack(anchor="w", padx=14, pady=(0, 8))

        # Кнопка сохранения конфигурации
        btn_save = ctk.CTkButton(
            main_frame, text="Применить калибровку", font=FONT_BODY_MED,
            fg_color=THEME_NEURAL_OBSIDIAN["cyan_neon"], text_color="#000000",
            hover_color=THEME_NEURAL_OBSIDIAN["cyan_dim"], corner_radius=CORNER_RADIUS_DEFAULT,
            command=self._save_action
        )
        btn_save.pack(pady=(10, 0))

        self._init_values()

    def _init_values(self):
        self.slider_thresh.set(self.config["segmentation"]["threshold"])
        self._update_thresh(self.config["segmentation"]["threshold"])
        self.slider_off.set(self.config["segmentation"]["min_duration_off"])
        self._update_off(self.config["segmentation"]["min_duration_off"])
        self.slider_on.set(self.config["segmentation"]["min_duration_on"])
        self._update_on(self.config["segmentation"]["min_duration_on"])

    def _update_thresh(self, val):
        val = round(float(val), 2)
        self.config["segmentation"]["threshold"] = val
        self.config["segmentation"]["offset"] = val  # Сквозной дублирующий порог деактивации для ИИ
        desc = " (Слабый фильтр)" if val < 0.4 else " (Стандарт)" if val <= 0.6 else " (Агрессивное шумоподавление)"
        self.lbl_thresh.configure(text=f"Порог активации: {val:.2f}")
        self.hint_thresh.configure(text=desc)

    def _update_off(self, val):
        val = round(float(val), 2)
        self.config["segmentation"]["min_duration_off"] = val
        desc = " (Дробить фразы)" if val < 0.4 else " (Норма)" if val <= 1.0 else " (Не разделять при паузах)"
        self.lbl_off.configure(text=f"Минимальная пауза: {val:.2f}с")
        self.hint_off.configure(text=desc)

    def _update_on(self, val):
        val = round(float(val), 2)
        self.config["segmentation"]["min_duration_on"] = val
        desc = " (Все звуки)" if val < 0.12 else " (Пропуск кашля и вздохов)"
        self.lbl_on.configure(text=f"Фильтр коротких звуков: {val:.2f}с")
        self.hint_on.configure(text=desc)

    def _save_action(self):
        self.on_save_callback(self.config)
        self.destroy()