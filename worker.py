import bootstrap  # CRITICAL: Must be the absolute first line
import os
import time
import datetime
import threading
import tempfile
import subprocess
import gc
import traceback
import torch
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline

# ==============================================================================
# WORKER ПОТОКОВ (ИЗОЛЯЦИЯ ВЫЧИСЛЕНИЙ И ТЕЛЕМЕТРИЯ)
# ==============================================================================
class WorkerDiarizationProgressHook:
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

    def __init__(self, task_queue, start_fraction=0.0, end_fraction=1.0, device="cpu"):
        self.queue = task_queue
        self.start_fraction = start_fraction
        self.end_fraction = end_fraction
        self.device = device

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
        self.queue.put(("STATUS", text))
        self.queue.put(("PROGRESS", global_fraction))
        
        # Сбор телеметрии на этапах Pyannote
        vram_used = 0.0
        if self.device == "cuda":
            try:
                vram_used = torch.cuda.memory_allocated() / (1024 ** 3)
            except Exception:
                pass
        self.queue.put(("TELEMETRY", (vram_used, self.device)))


class AudioProcessingWorker(threading.Thread):
    def __init__(self, audio_file, use_diarization, task_queue, cancel_event, vad_config=None):
        super().__init__(daemon=True)
        self.audio_file = audio_file
        self.use_diarization = use_diarization
        self.queue = task_queue
        self.cancel_event = cancel_event
        self.vad_config = vad_config  
        self.transcribed_segments = []

    def _convert_to_wav(self, input_file):
        temp_fd, temp_path = tempfile.mkstemp(suffix=".wav")
        os.close(temp_fd)
        command = [bootstrap.FFMPEG_PATH, "-y", "-i", input_file, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", temp_path]
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo, check=True)
        return temp_path

    def format_time(self, seconds, decimal_separator=","):
        total_ms = int(round(seconds * 1000))
        hours, remainder = divmod(total_ms, 3600000)
        minutes, remainder = divmod(remainder, 60000)
        secs, ms = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}{decimal_separator}{ms:03d}"

    def _send_telemetry(self, device):
        vram_used = 0.0
        if device == "cuda":
            try:
                vram_used = torch.cuda.memory_allocated() / (1024 ** 3)
            except Exception:
                pass
        self.queue.put(("TELEMETRY", (vram_used, device)))

    def run(self):
        # Предотвращение OpenMP Deadlock при инициализации PyTorch во вторичном потоке
        torch.set_num_threads(1)
        os.environ["OMP_NUM_THREADS"] = "1"
        
        session_start = time.monotonic()
        session_status = "Успешно"
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        whisper_model = None
        diarize_model = None
        temp_wav_path = None
        diarization_result = None

        try:
            self.queue.put(("STATUS", "Конвертация аудио (FFmpeg)..."))
            self.queue.put(("PROGRESS", 0.02))
            self._send_telemetry(device)
            temp_wav_path = self._convert_to_wav(self.audio_file)
            current_audio = temp_wav_path

            self.queue.put(("LOG", f"[*] Инициализация оборудования: {device.upper()}"))

            if self.cancel_event.is_set(): return

            self.queue.put(("STATUS", "Загрузка модели Whisper..."))
            self.queue.put(("PROGRESS", 0.06))
            self._send_telemetry(device)
            
            compute_type = "int8_float16" if device == "cuda" else "int8"
            whisper_model = WhisperModel(bootstrap.WHISPER_MODEL_PATH, device=device, compute_type=compute_type)

            self.queue.put(("LOG", "\n[*] Транскрибация аудио:"))
            segments, info = whisper_model.transcribe(current_audio, beam_size=5)
            duration = info.duration

            transcribe_budget = 0.35 if self.use_diarization else 0.94
            for segment in segments:
                if self.cancel_event.is_set(): break
                seg_data = (segment.start, segment.end, segment.text.strip())
                self.transcribed_segments.append(seg_data)
                self.queue.put(("SEGMENT", seg_data))
                
                local_fraction = min(segment.end / duration, 1.0) if duration else 1.0
                prog_text = f"Транскрибация ({self.format_time(segment.end, ',')} / {self.format_time(duration, ',')})"
                prog_val = 0.06 + transcribe_budget * local_fraction
                
                self.queue.put(("STATUS", prog_text))
                self.queue.put(("PROGRESS", prog_val))
                self._send_telemetry(device)

            if whisper_model is not None:
                del whisper_model
                whisper_model = None
                
            if device == "cuda":
                torch.cuda.empty_cache()
            gc.collect()

            if self.cancel_event.is_set(): return
            self.queue.put(("LOG", "\n[+] Транскрибация завершена."))

            if self.use_diarization:
                self.queue.put(("STATUS", "Загрузка модели Pyannote..."))
                self.queue.put(("PROGRESS", 0.06 + transcribe_budget))
                self._send_telemetry(device)
                try:
                    diarize_model = Pipeline.from_pretrained(bootstrap.DIARIZATION_CONFIG_PATH)
                    
                    if self.vad_config:
                        s_cfg = self.vad_config.get("segmentation", {})
                        onset = s_cfg.get("threshold", 0.50)
                        offset = s_cfg.get("offset", onset)
                        min_on = s_cfg.get("min_duration_on", 0.20)
                        min_off = s_cfg.get("min_duration_off", 0.50)
                        
                        self.queue.put(("LOG", f"[*] Калибровка VAD: threshold={onset:.2f}, min_off={min_off:.1f}s, min_on={min_on:.2f}s"))
                        
                        # Пуленепробиваемый адаптивный инжектор параметров под Pyannote 3.3.1+
                        params_applied = False
                        
                        # Попытка 1: Через стандартный binarization (совместимость с 3.3.1)
                        if not params_applied:
                            try:
                                native_33 = {
                                    "binarization": {
                                        "onset": onset,
                                        "offset": offset,
                                        "min_duration_on": min_on,
                                        "min_duration_off": min_off
                                    }
                                }
                                diarize_model.instantiate(native_33)
                                params_applied = True
                            except Exception:
                                pass

                        # Попытка 2: Через плоскую структуру сегментации
                        if not params_applied:
                            try:
                                native_31 = {
                                    "segmentation": {
                                        "onset": onset,
                                        "offset": offset,
                                        "min_duration_on": min_on,
                                        "min_duration_off": min_off
                                    }
                                }
                                diarize_model.instantiate(native_31)
                                params_applied = True
                            except Exception:
                                pass

                        if not params_applied:
                            self.queue.put(("LOG", "[!] Предупреждение: структура весов уникальна. Использованы встроенные заводские калибровки."))
                    
                    if device == "cuda":
                        diarize_model.to(torch.device("cuda"))
                    
                    self.queue.put(("LOG", "\n[*] Запуск разделения по ролям (Pyannote)..."))
                    hook = WorkerDiarizationProgressHook(self.queue, start_fraction=0.06 + transcribe_budget, end_fraction=1.0, device=device)
                    
                    with torch.inference_mode():
                        diarization_result = diarize_model(current_audio, hook=hook)
                        
                except Exception as e:
                    self.queue.put(("ERROR", f"ОШИБКА ИНИЦИАЛИЗАЦИИ PYANNOTE:\n{str(e)}"))
                    session_status = "Ошибка"
                    return
                finally:
                    if device == "cuda":
                        if diarize_model is not None:
                            try: diarize_model.to(torch.device("cpu"))
                            except Exception: pass
                        torch.cuda.empty_cache()
                    if diarize_model is not None:
                        del diarize_model
                        diarize_model = None
                    gc.collect()

                if self.cancel_event.is_set(): return

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
                self.queue.put(("LOG", "[+] Разделение ролей завершено. Обновление интерфейса...\n"))

            if not self.cancel_event.is_set():
                self.queue.put(("STATUS", "Готово"))
                self.queue.put(("PROGRESS", 1.0))
                self._send_telemetry(device)
                self.queue.put(("DONE", (self.transcribed_segments, diarization_result)))

        except Exception as e:
            session_status = "Ошибка"
            if not self.cancel_event.is_set():
                self.queue.put(("ERROR", traceback.format_exc()))
        finally:
            if self.cancel_event.is_set():
                session_status = "Прервано пользователем"
                
            session_duration = time.monotonic() - session_start
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            v_cfg = self.vad_config.get("segmentation", {}) if self.vad_config else {}
            onset = v_cfg.get("threshold", 0.50)
            min_off = v_cfg.get("min_duration_off", 0.50)
            min_on = v_cfg.get("min_duration_on", 0.20)
            
            log_line = (f"[{timestamp}] Файл: {os.path.basename(self.audio_file)} | "
                        f"Диаризация: {self.use_diarization} | "
                        f"VAD: [onset={onset:.2f}, min_off={min_off:.2f}s, min_on={min_on:.2f}s] | "
                        f"Время: {session_duration:.1f} сек | Статус: {session_status}\n")
            
            try:
                with open("lexora_runtime.log", "a", encoding="utf-8") as log_file:
                    log_file.write(log_line)
            except Exception:
                pass
            
            if device == "cuda":
                if diarize_model is not None:
                    try: diarize_model.to(torch.device("cpu"))
                    except Exception: pass
                torch.cuda.empty_cache()
            if whisper_model is not None:
                del whisper_model
            if diarize_model is not None:
                del diarize_model
            gc.collect()

            if temp_wav_path and os.path.exists(temp_wav_path):
                try: os.remove(temp_wav_path)
                except: pass