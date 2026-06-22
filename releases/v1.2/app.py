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
    os.environ["PATH"] += os.pathsep + application_path
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

# Устанавливаем рабочую директорию
os.chdir(application_path)

# ==============================================================================
# ФИКС WinError 448 (RCA: см. NOTES — общий пользовательский HF/torch-кэш
# в %USERPROFILE%\.cache хранит symlink на путь ПОСЛЕДНЕЙ запускавшейся
# копии приложения. Перемещение/удаление этой копии делает symlink
# недостижимым для всех ОСТАЛЬНЫХ копий (включая установленную через
# Inno Setup), вызывая WinError 448 при попытке прочитать diarization-веса.
#
# Решение: переопределяем переменные окружения, отвечающие за расположение
# HF/torch кэша, на путь ВНУТРИ самого приложения (application_path),
# ДО импорта speechbrain/pyannote/huggingface_hub. Каждая копия приложения
# получает собственный, независимый кэш — общий путь больше не используется.
#
# ИЗВЕСТНЫЙ ОСТАТОЧНЫЙ РИСК (зафиксирован, не устранён в этой версии):
# Установленная копия в Program Files может не иметь прав на запись
# в application_path для обычного (непривилегированного) пользователя.
# Если это проявится — потребуется fallback на %LOCALAPPDATA%, который
# в этой версии патча сознательно не реализован.
# ==============================================================================
_local_cache_dir = os.path.join(application_path, ".cache")
os.environ["HF_HOME"] = _local_cache_dir
os.environ["TORCH_HOME"] = _local_cache_dir
os.environ["XDG_CACHE_HOME"] = _local_cache_dir
os.environ["HF_HUB_CACHE"] = _local_cache_dir
os.makedirs(_local_cache_dir, exist_ok=True)

# ==============================================================================
# СТАНДАРТНЫЕ ИМПОРТЫ И БЛОКИРОВКА СЕТИ
# ==============================================================================
import threading
import gc
import traceback
import types
import tempfile
import subprocess
import customtkinter as ctk
from tkinter import filedialog, messagebox
import torch
from tkinterdnd2 import TkinterDnD, DND_FILES
from faster_whisper import WhisperModel

# Жесткая блокировка сети
os.environ["HF_HUB_OFFLINE"] = "1"

# Фикс кодировки Windows для чтения config.yaml
import locale
locale.getpreferredencoding = lambda *args: 'utf-8'

# Заглушка для k2 (отключение ленивого поиска C++ компиляторов)
sys.modules["k2"] = types.ModuleType("k2")

# ==============================================================================
# ДИНАМИЧЕСКИЕ ПАТЧИ SPEECHBRAIN (БЕЗ СИМЛИНКОВ И С УДАЛЕНИЕМ AUTH_TOKEN)
# ==============================================================================
import speechbrain.utils.fetching
import speechbrain.inference.interfaces

# --- ПАТЧ А: Отключение симлинков (Фикс WinError 448, первая линия защиты) ---
_original_fetch = speechbrain.utils.fetching.fetch

def _direct_local_fetch(filename, source, *args, **kwargs):
    """Принудительно возвращает прямой локальный путь, обходя создание symlink/junction."""
    if isinstance(source, str) and os.path.isdir(source):
        local_file = os.path.join(source, filename)
        if os.path.exists(local_file):
            return local_file
    return _original_fetch(filename, source, *args, **kwargs)

speechbrain.utils.fetching.fetch = _direct_local_fetch

# --- ПАТЧ Б: Устранение конфликта версий Pyannote 3.x и SpeechBrain 1.x ---
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
    """Перехватывает инициализацию и удаляет устаревший аргумент."""
    kwargs.pop('use_auth_token', None)
    return _original_from_hparams.__func__(cls, *args, **kwargs)

speechbrain.inference.interfaces.Pretrained.from_hparams = _patched_from_hparams

# Импортируем Pipeline строго после всех фиксов среды
from pyannote.audio import Pipeline

# ==============================================================================
# ОСНОВНАЯ ЛОГИКА ПРИЛОЖЕНИЯ
# ==============================================================================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

WHISPER_MODEL_PATH = os.path.join(application_path, "model_weights", "medium")
DIARIZATION_CONFIG_PATH = os.path.join(application_path, "model_weights", "diarization", "config.yaml")

class DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)

class LexoraApp(DnDCTk):
    def __init__(self):
        super().__init__()
        self.title("Lexora")
        self.geometry("850x600")
        self.resizable(True, True)

        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.handle_drop_event)

        self.transcribed_segments = []
        self.current_audio_path = None
        self.is_running = False

        self.show_time_var = ctk.BooleanVar(value=True)
        self.use_roles_var = ctk.BooleanVar(value=False)

        self.top_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.top_frame.pack(pady=10, padx=10, fill="x")

        self.btn_select = ctk.CTkButton(self.top_frame, text="Выбрать файл", command=self.start_processing)
        self.btn_select.pack(side="left", padx=5)

        self.btn_stop = ctk.CTkButton(self.top_frame, text="Стоп", fg_color="#c93434", hover_color="#a32a2a", state="disabled", command=self.stop_processing)
        self.btn_stop.pack(side="left", padx=5)

        self.btn_copy = ctk.CTkButton(self.top_frame, text="Копировать", fg_color="#4f6b7d", hover_color="#3e5563", command=self.copy_text)
        self.btn_copy.pack(side="left", padx=5)

        self.switch_timecodes = ctk.CTkSwitch(
            self.top_frame, text="Таймкоды",
            variable=self.show_time_var,
            command=self.redraw_interface
        )
        self.switch_timecodes.pack(side="right", padx=10)

        self.switch_diarization = ctk.CTkSwitch(
            self.top_frame, text="Диалог (Роли)",
            variable=self.use_roles_var
        )
        self.switch_diarization.pack(side="right", padx=10)

        self.progressbar = ctk.CTkProgressBar(self)
        self.progressbar.pack(padx=15, pady=(0, 10), fill="x")
        self.progressbar.set(0)

        self.textbox = ctk.CTkTextbox(self, state="disabled", font=("Consolas", 14))
        self.textbox.pack(padx=10, pady=(0, 10), fill="both", expand=True)

    def format_time(self, seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def redraw_interface(self):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")

        for start, end, text in self.transcribed_segments:
            line = f"[{self.format_time(start)} -> {self.format_time(end)}] {text}\n" if self.show_time_var.get() else f"{text}\n"
            self.textbox.insert("end", line)

        self.textbox.see("end")
        self.textbox.configure(state="disabled")

    def append_segment_ui(self, start, end, text):
        self.transcribed_segments.append((start, end, text))
        line = f"[{self.format_time(start)} -> {self.format_time(end)}] {text}\n" if self.show_time_var.get() else f"{text}\n"

        self.textbox.configure(state="normal")
        self.textbox.insert("end", line)
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

    def handle_drop_event(self, event):
        if self.is_running:
            messagebox.showwarning("Внимание", "Дождитесь окончания текущей транскрибации!")
            return

        files = self.tk.splitlist(event.data)
        if files:
            self.start_processing(files[0])

    def start_processing(self, filepath=None):
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

        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")
        self.progressbar.set(0)

        self.system_log_ui(f"[*] Выбран файл: {os.path.basename(filepath)}")

        threading.Thread(target=self.process_audio, args=(filepath, use_diarization), daemon=True).start()

    def _convert_to_wav(self, input_file):
        """Конвертирует любой медиафайл в 16kHz Mono WAV через FFmpeg."""
        temp_fd, temp_path = tempfile.mkstemp(suffix=".wav")
        os.close(temp_fd)

        command = [
            "ffmpeg", "-y", "-i", input_file,
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

        try:
            self.after(0, self.system_log_ui, "[*] Извлечение и нормализация аудио (FFmpeg)...")
            temp_wav_path = self._convert_to_wav(audio_file)
            audio_file = temp_wav_path

            self.after(0, self.system_log_ui, f"[*] Инициализация оборудования: {device.upper()}")

            if use_diarization:
                self.after(0, self.system_log_ui, "[*] Загрузка локальной модели Pyannote (Разделение ролей)...")
                try:
                    diarize_model = Pipeline.from_pretrained(DIARIZATION_CONFIG_PATH)
                    if device == "cuda":
                        diarize_model.to(torch.device("cuda"))
                except Exception as e:
                    self.after(0, self.system_log_ui, f"\n[-] ОШИБКА ИНИЦИАЛИЗАЦИИ PYANNOTE:\n{str(e)}")
                    self.is_running = False
                    return

            if not self.is_running: return

            self.after(0, self.system_log_ui, "[*] Загрузка локальной модели Whisper...")
            whisper_model = WhisperModel(WHISPER_MODEL_PATH, device=device, compute_type="float16" if device == "cuda" else "int8")

            if not self.is_running: return

            self.after(0, self.system_log_ui, "\n[*] Транскрибация аудио (Потоковый вывод):")
            segments, info = whisper_model.transcribe(audio_file, beam_size=5)
            duration = info.duration

            # ЭТАП 1: Транскрибация
            for segment in segments:
                if not self.is_running: break

                self.after(0, self.append_segment_ui, segment.start, segment.end, segment.text.strip())

                progress_val = min(segment.end / duration, 1.0)
                ui_progress = progress_val * 0.8 if use_diarization else progress_val
                self.after(0, self.progressbar.set, ui_progress)

            if not self.is_running: return
            self.after(0, self.system_log_ui, f"\n[+] Транскрибация завершена.")

            # ЭТАП 2: Диаризация
            if use_diarization and diarize_model:
                self.after(0, self.system_log_ui, "\n[*] Запуск разделения по ролям (Pyannote). Пожалуйста, подождите...")
                diarization_result = diarize_model(audio_file)

                if not self.is_running: return

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

            if self.is_running:
                self.after(0, self.progressbar.set, 1.0)
                self.save_to_file()

        except Exception as e:
            self.after(0, self.system_log_ui, f"\n[-] КРИТИЧЕСКАЯ ОШИБКА:\n{traceback.format_exc()}")

        finally:
            self.is_running = False
            del whisper_model
            del diarize_model
            gc.collect()
            if device == "cuda": torch.cuda.empty_cache()

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
        if not self.current_audio_path or not self.transcribed_segments: return
        output_txt = os.path.splitext(self.current_audio_path)[0] + "_transcript.txt"
        try:
            with open(output_txt, "w", encoding="utf-8") as f:
                for start, end, text in self.transcribed_segments:
                    if self.show_time_var.get():
                        f.write(f"[{self.format_time(start)} -> {self.format_time(end)}] {text}\n")
                    else:
                        f.write(f"{text}\n")
            self.after(0, self.system_log_ui, f"\n[+] Сохранено: {output_txt}")
        except Exception as e:
            self.after(0, self.system_log_ui, f"\n[-] Ошибка сохранения: {str(e)}")

if __name__ == "__main__":
    app = LexoraApp()
    app.mainloop()
