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
import sys
import json

# Базовые STT импорты
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline

SUMMARY_TIMEOUT_SECONDS = 180   
SUMMARY_N_CTX = 4096            
SUMMARY_MAX_TOKENS = 512

class WorkerDiarizationProgressHook:
    def __init__(self, task_queue, start_fraction=0.0, end_fraction=1.0, device="cpu"):
        self.queue = task_queue
        self.start_fraction = start_fraction
        self.end_fraction = end_fraction
        self.device = device

    def __call__(self, step_name, step_artifact, file=None, total=None, completed=None):
        lo, hi = (0.00, 0.15) if step_name == "segmentation" else (0.15, 0.20) if step_name == "speaker_counting" else (0.20, 0.85) if step_name == "embeddings" else (0.85, 1.00)
        
        if total and completed is not None and total > 0:
            local_fraction = completed / total
        else:
            local_fraction = 1.0
            
        phase_fraction = lo + (hi - lo) * local_fraction
        span = self.end_fraction - self.start_fraction
        global_fraction = self.start_fraction + span * phase_fraction
        
        self.queue.put(("STATUS", step_name))
        self.queue.put(("PROGRESS", global_fraction))
        
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
        
        self.ffmpeg_proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo)
        
        while self.ffmpeg_proc.poll() is None:
            if self.cancel_event and self.cancel_event.is_set():
                self.ffmpeg_proc.kill()
                self.ffmpeg_proc.wait()  # ИСПРАВЛЕНИЕ: Чистое завершение процесса
                return None
            time.sleep(0.1)
            
        if self.ffmpeg_proc.returncode != 0:
            raise RuntimeError("FFmpeg завершился с ошибкой при конвертации файла.")
            
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
            self.queue.put(("STATUS", "WORKER_CONVERT"))
            self.queue.put(("PROGRESS", 0.02))
            self._send_telemetry(device)
            temp_wav_path = self._convert_to_wav(self.audio_file)
            
            if not temp_wav_path or self.cancel_event.is_set(): return
            current_audio = temp_wav_path

            self.queue.put(("LOG", f"[*] Инициализация оборудования: {device.upper()}"))

            self.queue.put(("STATUS", "WORKER_WHISPER"))
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
                prog_text = f"WORKER_TRANSCRIBE ({self.format_time(segment.end, ',')} / {self.format_time(duration, ',')})"
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
                self.queue.put(("STATUS", "WORKER_PYANNOTE"))
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
                        
                        params_applied = False
                        if not params_applied:
                            try:
                                native_33 = {"binarization": {"onset": onset, "offset": offset, "min_duration_on": min_on, "min_duration_off": min_off}}
                                diarize_model.instantiate(native_33)
                                params_applied = True
                            except Exception: pass

                        if not params_applied:
                            try:
                                native_31 = {"segmentation": {"onset": onset, "offset": offset, "min_duration_on": min_on, "min_duration_off": min_off}}
                                diarize_model.instantiate(native_31)
                                params_applied = True
                            except Exception: pass

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
                self.queue.put(("STATUS", "WORKER_DONE"))
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
                        f"Время: {session_duration:.1f} сек | Status: {session_status}\n")
            
            log_root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            log_path = os.path.join(log_root, "Lexora", "lexora_runtime.log")
            try:
                os.makedirs(os.path.dirname(log_path), exist_ok=True)
                with open(log_path, "a", encoding="utf-8") as log_file:
                    log_file.write(log_line)
            except Exception: pass
            
            if device == "cuda":
                if diarize_model is not None:
                    try: diarize_model.to(torch.device("cpu"))
                    except Exception: pass
                torch.cuda.empty_cache()
            if whisper_model is not None: del whisper_model
            if diarize_model is not None: del diarize_model
            gc.collect()

            if temp_wav_path and os.path.exists(temp_wav_path):
                try: os.remove(temp_wav_path)
                except Exception: pass


class SummaryWorker(threading.Thread):
    def __init__(self, text_content, current_lang, task_queue, cancel_event):
        super().__init__(daemon=True)
        self.text_content = text_content
        self.current_lang = current_lang
        self.queue = task_queue
        self.cancel_event = cancel_event
        self.proc = None 

    def run(self):
        self.queue.put(("SUMMARY_STATUS", "STATUS_SUMMARY"))

        if not os.path.exists(bootstrap.QWEN_MODEL_PATH):
            self.queue.put(("SUMMARY_ERROR", f"Файл модели не найден по пути:\n{bootstrap.QWEN_MODEL_PATH}"))
            return

        if self.current_lang == "UK":
            system_prompt = "Ти — професійний аналітик. Зроби стислий, структурований та інформативний підсумок (Summary) наступного тексту українською мовою. Використовуй марковані списки та виділяй головне."
        elif self.current_lang == "EN":
            system_prompt = "You are a professional analyst. Provide a concise, structured, and informative summary of the following transcript in English. Use bullet points and highlight key insights."
        else:
            system_prompt = "Ты — профессиональный аналитик. Сделай краткий, структурированный и информативный итог (Summary) следующего текста на русском языке. Используй маркированные списки и выделяй главное."

        cpu_count = os.cpu_count() or 2
        n_threads = max(1, min(cpu_count - 1, 4))

        params = {
            "model_path": bootstrap.QWEN_MODEL_PATH,
            "system_prompt": system_prompt,
            "user_text": self.text_content,
            "n_threads": n_threads,
            "n_ctx": SUMMARY_N_CTX,
            "max_tokens": SUMMARY_MAX_TOKENS
        }
        input_payload = json.dumps(params, ensure_ascii=False)

        # ВОТ ЭТА СТРОКА БЫЛА УТЕРЯНА (Возвращаем её на место):
        engine_script = os.path.join(bootstrap.application_path, "summary_engine.py")

        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            self.proc = subprocess.Popen(
                [sys.executable, engine_script],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                env=env
            )
        except Exception:
            self.queue.put(("SUMMARY_ERROR", f"Не удалось инициализировать изолированный процесс:\n{traceback.format_exc()}"))
            return

        try:
            outs, errs = None, None
            try:
                outs, errs = self.proc.communicate(input=input_payload.encode('utf-8'), timeout=0.5)
            except subprocess.TimeoutExpired:
                while self.proc.poll() is None:
                    if self.cancel_event and self.cancel_event.is_set():
                        self.proc.kill()
                        self.proc.wait()
                        self.queue.put(("SUMMARY_ERROR", "Процесс ИИ-суммаризации был принудительно остановлен пользователем."))
                        return
                    try:
                        outs, errs = self.proc.communicate(timeout=0.5)
                        break
                    except subprocess.TimeoutExpired:
                        continue

            if outs is None: outs = b""
            if errs is None: errs = b""

            stdout_data = outs.decode('utf-8', errors='replace')
            stderr_data = errs.decode('utf-8', errors='replace')

        except Exception as e:
            self.proc.kill()
            self.proc.wait()
            self.queue.put(("SUMMARY_ERROR", f"Критический сбой IPC: {str(e)}"))
            return

        if self.proc.returncode != 0:
            self.queue.put((
                "SUMMARY_ERROR",
                f"ИИ-процесс завершился критическим сбоем системы (Exit Code: {self.proc.returncode}).\nСистемная ошибка:\n{stderr_data}"
            ))
            return

        try:
            valid_json_str = None
            for line in reversed(stdout_data.strip().split('\n')):
                line = line.strip()
                if line.startswith('{') and line.endswith('}'):
                    valid_json_str = line
                    break
                    
            if not valid_json_str:
                raise ValueError("JSON не найден в ответе процесса")
                
            result = json.loads(valid_json_str)
            if result["status"] == "DONE":
                self.queue.put(("SUMMARY_DONE", result["payload"]))
            else:
                self.queue.put(("SUMMARY_ERROR", result["payload"]))
        except Exception:
            self.queue.put((
                "SUMMARY_ERROR",
                f"Не удалось десериализовать ответ ИИ-процесса.\nСырой вывод stdout:\n{stdout_data}\nStderr:\n{stderr_data}"
            ))