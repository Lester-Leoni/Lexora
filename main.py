import bootstrap  # CRITICAL: Must be the absolute first line
import os
import time
import queue
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox
from tkinterdnd2 import TkinterDnD

import ui_components as ui
from ui_components import SpeakerCard, DropZone, DotMatrixProgressBar, THEME_NEURAL_OBSIDIAN, VadSettingsWindow
from worker import AudioProcessingWorker

# ==============================================================================
# ГЛАВНОЕ ПРИЛОЖЕНИЕ (UI)
# ==============================================================================
class DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)

class LexoraApp(DnDCTk):
    def __init__(self):
        super().__init__()
        ui.init_fonts()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        self.title("Lexora")
        self.geometry("960x680")
        self.minsize(820, 600)
        self.resizable(True, True)
        self.configure(fg_color=ui.THEME_NEURAL_OBSIDIAN["window_bg"])

        self.transcribed_segments = []
        self.speaker_cards = {}
        self.current_audio_path = None
        self.is_running = False

        self.speaker_names_map = {}
        self.speaker_entries = {}

        self.show_time_var = ctk.BooleanVar(value=True)
        self.use_roles_var = ctk.BooleanVar(value=False)

        # Начальная конфигурация ИИ-фильтров VAD по умолчанию (Паритет с пресетом "Стандарт")
        self.vad_config = {
            "segmentation": {
                "threshold": 0.50,
                "min_duration_off": 0.50,
                "min_duration_on": 0.20
            }
        }
        self.settings_window = None

        # Панель управления
        self.top_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.top_frame.pack(pady=(14, 8), padx=14, fill="x")

        self.btn_select = ctk.CTkButton(
            self.top_frame, text="Выбрать файл", font=ui.FONT_BODY_MED,
            fg_color=ui.THEME_NEURAL_OBSIDIAN["cyan_neon"], text_color="#000000",
            hover_color=ui.THEME_NEURAL_OBSIDIAN["cyan_dim"], corner_radius=ui.CORNER_RADIUS_DEFAULT,
            command=self.start_processing,
        )
        self.btn_select.pack(side="left", padx=5)

        self.btn_stop = ctk.CTkButton(
            self.top_frame, text="Стоп", font=ui.FONT_BODY_MED,
            fg_color="#c93434", hover_color="#a32a2a", corner_radius=ui.CORNER_RADIUS_DEFAULT,
            state="disabled", command=self.stop_processing,
        )
        self.btn_stop.pack(side="left", padx=5)

        self.btn_copy = ctk.CTkButton(
            self.top_frame, text="Копировать", font=ui.FONT_BODY,
            fg_color=ui.THEME_NEURAL_OBSIDIAN["frame_bg"], text_color=ui.THEME_NEURAL_OBSIDIAN["text_main"],
            hover_color=ui.THEME_NEURAL_OBSIDIAN["card_bg"], corner_radius=ui.CORNER_RADIUS_DEFAULT,
            command=self.copy_text,
        )
        self.btn_copy.pack(side="left", padx=5)

        self.btn_save = ctk.CTkOptionMenu(
            self.top_frame,
            values=["Текст (.txt)", "Субтитры (.srt)", "Субтитры (.vtt)"],
            font=ui.FONT_BODY,
            fg_color=ui.THEME_NEURAL_OBSIDIAN["frame_bg"],
            button_color=ui.THEME_NEURAL_OBSIDIAN["cyan_dim"],
            button_hover_color=ui.THEME_NEURAL_OBSIDIAN["cyan_neon"],
            text_color=ui.THEME_NEURAL_OBSIDIAN["text_main"],
            dropdown_fg_color=ui.THEME_NEURAL_OBSIDIAN["card_bg"],
            dropdown_text_color=ui.THEME_NEURAL_OBSIDIAN["text_main"],
            dropdown_hover_color=ui.THEME_NEURAL_OBSIDIAN["frame_bg"],
            corner_radius=ui.CORNER_RADIUS_DEFAULT,
            state="disabled",
            command=self._on_save_dropdown_click
        )
        self.btn_save.set("Сохранить как...")
        self.btn_save.pack(side="left", padx=5)

        # Неоновая кнопка тонкой калибровки VAD
        self.btn_settings = ctk.CTkButton(
            self.top_frame, text="⚙ Настройки VAD", font=ui.FONT_SMALL,
            fg_color=ui.THEME_NEURAL_OBSIDIAN["frame_bg"], text_color=ui.THEME_NEURAL_OBSIDIAN["text_main"],
            hover_color=ui.THEME_NEURAL_OBSIDIAN["card_bg"], border_width=1, border_color=ui.THEME_NEURAL_OBSIDIAN["cyan_dim"],
            corner_radius=ui.CORNER_RADIUS_DEFAULT, command=self.open_vad_settings
        )
        self.btn_settings.pack(side="left", padx=5)

        self.switch_timecodes = ctk.CTkSwitch(
            self.top_frame, text="Таймкоды", font=ui.FONT_SMALL,
            progress_color=ui.THEME_NEURAL_OBSIDIAN["cyan_neon"],
            variable=self.show_time_var, command=self.redraw_interface,
        )
        self.switch_timecodes.pack(side="right", padx=10)

        self.switch_diarization = ctk.CTkSwitch(
            self.top_frame, text="Диалог (Роли)", font=ui.FONT_SMALL,
            progress_color=ui.THEME_NEURAL_OBSIDIAN["cyan_neon"],
            variable=self.use_roles_var,
        )
        self.switch_diarization.pack(side="right", padx=10)

        self.drop_zone = ui.DropZone(self, on_file_dropped=self.start_processing, height=120)
        self.drop_zone.pack(padx=14, pady=(0, 10), fill="x")

        status_frame = ctk.CTkFrame(self, fg_color="transparent")
        status_frame.pack(padx=14, pady=(0, 10), fill="x")

        self.status_label = ctk.CTkLabel(
            status_frame, text="Ожидание файла", font=ui.FONT_SMALL, anchor="w",
            text_color=ui.THEME_NEURAL_OBSIDIAN["text_dim"],
        )
        self.status_label.pack(fill="x")

        self.progressbar = ctk.CTkProgressBar(
            status_frame, mode="determinate",
            progress_color=ui.THEME_NEURAL_OBSIDIAN["cyan_neon"],
            fg_color=ui.THEME_NEURAL_OBSIDIAN["frame_bg"],
            corner_radius=ui.CORNER_RADIUS_DEFAULT // 2,
        )
        self.progressbar.pack(pady=(4, 0), fill="x")
        self.progressbar.set(0)

        body_frame = ctk.CTkFrame(self, fg_color="transparent")
        body_frame.pack(padx=14, pady=(0, 14), fill="both", expand=True)
        body_frame.grid_columnconfigure(0, weight=3)
        body_frame.grid_columnconfigure(1, weight=1)
        body_frame.grid_rowconfigure(0, weight=1)

        self.textbox = ctk.CTkTextbox(
            body_frame, state="disabled", font=ui.FONT_MONO,
            fg_color=ui.THEME_NEURAL_OBSIDIAN["window_bg"],
            text_color=ui.THEME_NEURAL_OBSIDIAN["text_main"],
            corner_radius=ui.CORNER_RADIUS_DEFAULT,
        )
        self.textbox.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        self._raw_textbox = self.textbox._textbox
        self._raw_textbox.tag_config("ts", foreground=self._fg("text_dim"))
        self._raw_textbox.tag_config("spk", foreground=self._fg("cyan_neon"), font=("Consolas", 13, "bold"))
        self._raw_textbox.tag_config("seg_hover", background=self._fg("frame_bg"))

        cards_outer = ctk.CTkFrame(body_frame, fg_color=ui.THEME_NEURAL_OBSIDIAN["frame_bg"],
                                    corner_radius=ui.CORNER_RADIUS_DEFAULT)
        cards_outer.grid(row=0, column=1, sticky="nsew")
        ctk.CTkLabel(cards_outer, text="СПИКЕРЫ", font=ui.FONT_SMALL,
                     text_color=ui.THEME_NEURAL_OBSIDIAN["text_dim"]).pack(anchor="w", padx=14, pady=(12, 4))

        self.cards_panel = ctk.CTkScrollableFrame(cards_outer, fg_color="transparent")
        self.cards_panel.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.cards_empty_label = ctk.CTkLabel(
            self.cards_panel, text="Появятся после диаризации", font=ui.FONT_SMALL,
            text_color=ui.THEME_NEURAL_OBSIDIAN["text_dim"], wraplength=160,
        )
        self.cards_empty_label.pack(pady=20)

    def _fg(self, theme_key: str) -> str:
        light, dark = ui.THEME_NEURAL_OBSIDIAN[theme_key]
        return dark if ctk.get_appearance_mode() == "Dark" else light

    def format_time(self, seconds, decimal_separator=","):
        total_ms = int(round(seconds * 1000))
        hours, remainder = divmod(total_ms, 3600000)
        minutes, remainder = divmod(remainder, 60000)
        secs, ms = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}{decimal_separator}{ms:03d}"

    def redraw_interface(self):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        for idx, (start, end, text) in enumerate(self.transcribed_segments):
            self._insert_segment_line(idx, start, end, text)
        self.textbox.see("end")
        self.textbox.configure(state="disabled")

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

    def _clear_speaker_cards(self):
        for card in self.speaker_cards.values():
            card.destroy()
        self.speaker_cards.clear()
        self.speaker_entries.clear()
        self.speaker_names_map.clear()
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

            card = ui.SpeakerCard(
                self.cards_panel, speaker, durations[speaker], total, 
                current_display_name, self._on_speaker_renamed
            )
            card.pack(fill="x", padx=4, pady=4)
            self.speaker_cards[speaker] = card
            self.speaker_entries[speaker] = card.name_entry

    def _on_speaker_renamed(self, speaker_id: str):
        entry = self.speaker_entries.get(speaker_id)
        if not entry: return

        new_name = entry.get().strip()
        if not new_name:
            new_name = speaker_id
            entry.delete(0, "end")
            entry.insert(0, speaker_id)

        if self.speaker_names_map.get(speaker_id) == new_name: return

        self.speaker_names_map[speaker_id] = new_name
        entry.configure(border_width=1, border_color=self._fg("cyan_neon"))
        self.after(400, lambda: entry.configure(border_width=0))

        current_scroll = self.textbox.yview()
        self.redraw_interface()
        self.textbox.yview_moveto(current_scroll[0])

    def open_vad_settings(self):
        """Модальный вызов панели калибровки VAD"""
        if self.settings_window is None or not self.settings_window.winfo_exists():
            self.settings_window = VadSettingsWindow(self, self.vad_config, self.save_vad_settings)
        else:
            self.settings_window.focus()

    def save_vad_settings(self, updated_config):
        self.vad_config = updated_config
        self.system_log_ui(f"\n[+] Новая калибровка VAD применена в рантайме.")

    def start_processing(self, filepath=None):
        if self.is_running:
            messagebox.showwarning("Внимание", "Дождитесь окончания текущей транскрибации!")
            return

        if not filepath:
            filepath = filedialog.askopenfilename(
                title="Выберите аудио/видео файл",
                filetypes=[("Media Files", "*.mp3 *.wav *.m4a *.mp4 *.mkv"), ("All Files", "*.*")]
            )
        if not filepath: return

        self.current_audio_path = filepath
        self.transcribed_segments.clear()
        self.is_running = True

        self.btn_select.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_settings.configure(state="disabled")  # Блокировка калибровки VAD во время инференса
        self.switch_diarization.configure(state="disabled")
        self.btn_save.configure(state="disabled")
        self._clear_speaker_cards()

        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")
        self.progressbar.set(0)
        self.status_label.configure(text=f"Выбран файл: {os.path.basename(filepath)}")

        self.task_queue = queue.Queue()
        self.cancel_event = threading.Event()
        
        # Передаем словарь vad_config в воркер для инъекции в ИИ-ядро
        self.worker = AudioProcessingWorker(
            audio_file=filepath, use_diarization=self.use_roles_var.get(), 
            task_queue=self.task_queue, cancel_event=self.cancel_event,
            vad_config=self.vad_config
        )
        self.worker.start()
        self._poll_queue()

    def stop_processing(self):
        if getattr(self, 'is_running', False):
            self.system_log_ui("\n[!] Остановка процесса по команде пользователя. Ожидание завершения потока...")
            self.btn_stop.configure(state="disabled")
            if hasattr(self, 'cancel_event'):
                self.cancel_event.set()
            self._shutdown_start_time = time.monotonic()
            self._await_worker_shutdown()

    def _await_worker_shutdown(self):
        if hasattr(self, 'worker') and self.worker.is_alive():
            if time.monotonic() - self._shutdown_start_time > 15.0:
                self.system_log_ui("\n[!] Превышено время ожидания завершения потока. Возврат в рабочий режим.")
                self._reset_ui_state()
            else:
                self.after(150, self._await_worker_shutdown)
        else:
            self._reset_ui_state()

    def _poll_queue(self):
        # FIX: Лимит обработки сообщений за один тик для предотвращения зависания GUI (Event Loop Starvation)
        messages_processed = 0
        while not self.task_queue.empty() and messages_processed < 30:
            try:
                msg_type, data = self.task_queue.get_nowait()
            except queue.Empty: break
            
            messages_processed += 1
                
            if msg_type == "STATUS": self.status_label.configure(text=data)
            elif msg_type == "PROGRESS": self.progressbar.set(data)
            elif msg_type == "LOG": self.system_log_ui(data)
            elif msg_type == "SEGMENT":
                start, end, text = data
                self.append_segment_ui(start, end, text)
            elif msg_type == "DONE":
                final_segments, diarization_result = data
                self.transcribed_segments = final_segments
                self.redraw_interface()
                if diarization_result is not None:
                    self._populate_speaker_cards(diarization_result)
                self.btn_save.configure(state="normal")
                self._reset_ui_state()
                return 
            elif msg_type == "ERROR":
                self.system_log_ui(f"\n[-] КРИТИЧЕСКАЯ ОШИБКА:\n{data}")
                self._reset_ui_state()
                return
                
        if getattr(self, 'is_running', False):
            # FIX: Ускорен цикл опроса для большей отзывчивости интерфейса
            self.after(50, self._poll_queue)

    def _reset_ui_state(self):
        self.is_running = False
        self.btn_select.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.btn_settings.configure(state="normal")  # Разблокировка калибровки VAD
        self.switch_diarization.configure(state="normal")

    def _on_save_dropdown_click(self, choice: str):
        if not self.current_audio_path or not self.transcribed_segments:
            messagebox.showwarning("Внимание", "Нет данных для сохранения!")
            self.btn_save.set("Сохранить как...")
            return

        base_name = os.path.splitext(os.path.basename(self.current_audio_path))[0]

        if choice == "Текст (.txt)":
            target_path = filedialog.asksaveasfilename(
                title="Сохранить транскрипт", initialfile=f"{base_name}_transcript",
                defaultextension=".txt", filetypes=[("Text Files", "*.txt")]
            )
            if target_path: self._export_txt(target_path)

        elif choice == "Субтитры (.srt)":
            target_path = filedialog.asksaveasfilename(
                title="Сохранить субтитры SRT", initialfile=base_name,
                defaultextension=".srt", filetypes=[("SubRip Subtitles", "*.srt")]
            )
            if target_path: self._export_srt(target_path)

        elif choice == "Субтитры (.vtt)":
            target_path = filedialog.asksaveasfilename(
                title="Сохранить субтитры VTT", initialfile=base_name,
                defaultextension=".vtt", filetypes=[("WebVTT Subtitles", "*.vtt")]
            )
            if target_path: self._export_vtt(target_path)

        self.btn_save.set("Сохранить как...")

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
                    else:
                        f.write(f"{processed_text}\n")
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


if __name__ == "__main__":
    app = LexoraApp()
    app.mainloop()