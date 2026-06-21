import os
import sys
import threading
import gc
import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk
from tkinterdnd2 import TkinterDnD, DND_FILES
import torch
from faster_whisper import WhisperModel

if sys.stdout is None: sys.stdout = open(os.devnull, "w")
if sys.stderr is None: sys.stderr = open(os.devnull, "w")

if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

os.environ["PATH"] += os.pathsep + application_path
MODEL_DIR = os.path.join(application_path, "model_weights")

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

transcribed_segments = []
current_audio_path = None
stop_event = threading.Event()
is_processing = False

class CTkWithDnD(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)

def format_time(seconds): 
    return f"{int(seconds // 60):02d}:{int(seconds % 60):02d}"

def save_to_file(show_time_var):
    if not current_audio_path or not transcribed_segments: return
    dir_name = os.path.dirname(os.path.abspath(current_audio_path))
    base_name = os.path.splitext(os.path.basename(current_audio_path))[0]
    path = os.path.join(dir_name, f"{base_name}_Текст.txt")
    with open(path, "w", encoding="utf-8") as f:
        for start, end, text in transcribed_segments:
            if show_time_var.get(): f.write(f"[{format_time(start)} -> {format_time(end)}] {text}\n")
            else: f.write(f"{text.strip()}\n")

def redraw_interface(log_widget, show_time_var):
    log_widget.delete("1.0", "end")
    for start, end, text in transcribed_segments:
        line = f"[{format_time(start)} -> {format_time(end)}] {text}\n" if show_time_var.get() else f"{text.strip()}\n"
        log_widget.insert("end", line)
    log_widget.see("end")

def process_audio(file_path, log_widget, btn_select, btn_stop, show_time_var, progress_bar):
    global transcribed_segments, current_audio_path, is_processing
    is_processing = True
    stop_event.clear()
    transcribed_segments.clear()
    current_audio_path = file_path
    
    log_widget.delete("1.0", "end")
    log_widget.insert("end", "[*] Инициализация Lexora v1.1...\n")
    progress_bar.set(0.0)

    use_cuda = torch.cuda.is_available()
    device_type = "cuda" if use_cuda else "cpu"
    compute_type = "float16" if use_cuda else "int8"
    
    log_widget.insert("end", f"[*] Аппаратное ускорение: {'NVIDIA GPU' if use_cuda else 'CPU'}\n")
    
    model = None
    try:
        model = WhisperModel("medium", device=device_type, compute_type=compute_type, download_root=MODEL_DIR)
    except Exception as e:
        log_widget.insert("end", f"[-] Ошибка загрузки модели: {str(e)}\n")
        is_processing = False
        btn_select.configure(state="normal")
        btn_stop.configure(state="disabled")
        return

    log_widget.insert("end", "[*] Анализ аудиопотока...\n\n")
    
    try:
        segments, info = model.transcribe(file_path, beam_size=5, language="ru")
        duration = info.duration
        
        for segment in segments:
            if stop_event.is_set():
                log_widget.insert("end", "\n[!] Процесс прерван пользователем.\n")
                break
            transcribed_segments.append((segment.start, segment.end, segment.text))
            line = f"[{format_time(segment.start)} -> {format_time(segment.end)}] {segment.text}\n" if show_time_var.get() else f"{segment.text.strip()}\n"
            log_widget.insert("end", line)
            log_widget.see("end")
            progress_bar.set(min(segment.end / duration, 1.0))
            
        if not stop_event.is_set():
            progress_bar.set(1.0)
            save_to_file(show_time_var)
            log_widget.insert("end", f"\n[+] УСПЕХ! Сохранено рядом с исходным файлом.")
    except Exception as e:
        log_widget.insert("end", f"\n[-] Системная ошибка: {str(e)}")
    finally:
        del model
        gc.collect()
        if use_cuda: torch.cuda.empty_cache()
        is_processing = False
        btn_select.configure(state="normal")
        btn_stop.configure(state="disabled")

def copy_to_clipboard(root, log_widget):
    root.clipboard_clear()
    root.clipboard_append(log_widget.get("1.0", tk.END))

def build_gui():
    root = CTkWithDnD()
    root.title("Lexora v1.1")
    root.geometry("900x650")
    
    frame = ctk.CTkFrame(root, corner_radius=10)
    frame.pack(pady=15, padx=15, fill="both", expand=True)

    top_panel = ctk.CTkFrame(frame, fg_color="transparent")
    top_panel.pack(pady=(15, 5), padx=20, fill="x")

    show_time_var = ctk.BooleanVar(value=True)
    log_area = ctk.CTkTextbox(frame, font=("Segoe UI", 14), text_color="#E0E0E0", fg_color="#181818", corner_radius=8, wrap="word")

    def start_transcription_thread(file_path):
        if is_processing: return
        btn_select.configure(state="disabled")
        btn_stop.configure(state="normal")
        threading.Thread(target=process_audio, args=(file_path, log_area, btn_select, btn_stop, show_time_var, progress), daemon=True).start()

    def run_process():
        file = filedialog.askopenfilename(title="Выберите медиафайл", filetypes=[("Media", "*.mp4 *.mp3 *.wav *.mkv *.avi")])
        if file: start_transcription_thread(file)

    def on_file_drop(event):
        clean_path = event.data.strip("{}")
        if clean_path: start_transcription_thread(clean_path)

    def on_toggle():
        if transcribed_segments:
            redraw_interface(log_area, show_time_var)
            if not is_processing: save_to_file(show_time_var)

    btn_select = ctk.CTkButton(top_panel, text="Выбрать файл", font=("Segoe UI", 14, "bold"), width=140, command=run_process)
    btn_select.pack(side="left", padx=(0, 10))

    btn_stop = ctk.CTkButton(top_panel, text="Стоп", font=("Segoe UI", 14, "bold"), fg_color="#D32F2F", hover_color="#B71C1C", width=80, state="disabled", command=lambda: stop_event.set())
    btn_stop.pack(side="left", padx=10)

    btn_copy = ctk.CTkButton(top_panel, text="Копировать", font=("Segoe UI", 14), fg_color="#455A64", hover_color="#37474F", width=120, command=lambda: copy_to_clipboard(root, log_area))
    btn_copy.pack(side="left", padx=10)

    switch = ctk.CTkSwitch(top_panel, text="Таймкоды", font=("Segoe UI", 14), variable=show_time_var, command=on_toggle)
    switch.pack(side="right", padx=10)

    progress = ctk.CTkProgressBar(frame, height=8, corner_radius=4)
    progress.pack(fill="x", padx=20, pady=(10, 15))
    progress.set(0)

    log_area.pack(pady=(0, 20), padx=20, fill="both", expand=True)

    root.drop_target_register(DND_FILES)
    root.dnd_bind('<<Drop>>', on_file_drop)

    root.mainloop()

if __name__ == "__main__": build_gui()