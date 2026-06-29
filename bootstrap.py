import os
import sys
import traceback
import types
import tempfile
import multiprocessing

# ==============================================================================
# ЗАЩИТА ОТ sys.stdout/stderr == None (PyInstaller --noconsole / pythonw.exe)
# ==============================================================================
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# ==============================================================================
# ИЗОЛЯЦИЯ ПУТЕЙ И КОРРЕКТИРОВКА RUNTIME ДЛЯ PYINSTALLER & PORTABLE
# ==============================================================================
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
    bundle_dir = getattr(sys, '_MEIPASS', application_path)
    _internal_path = os.path.join(bundle_dir, "_internal")
    if not os.path.exists(_internal_path):
        _internal_path = os.path.join(application_path, "_internal")
        
    if _internal_path not in sys.path:
        sys.path.insert(0, _internal_path)
    os.environ["PATH"] = _internal_path + os.pathsep + os.environ["PATH"]
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

os.chdir(application_path)

if sys.platform == "win32":
    multiprocessing.set_executable(sys.executable)

import locale
locale.getpreferredencoding = lambda *args: 'utf-8'

def _crash_log_startup_failure():
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
        if primary.startswith(r"\\") or primary.startswith("//"):
            raise OSError("UNC path detected")
        os.makedirs(primary, exist_ok=True)
        probe = os.path.join(primary, ".write_test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return primary
    except OSError:
        fallback_root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        if fallback_root.startswith(r"\\") or fallback_root.startswith("//"):
            fallback_root = os.environ.get("TEMP") or tempfile.gettempdir()
        fallback = os.path.join(fallback_root, "Lexora", "cache")
        os.makedirs(fallback, exist_ok=True)
        return fallback

try:
    _local_cache_dir = _init_cache_dir()
    os.environ["HF_HOME"] = _local_cache_dir
    os.environ["TORCH_HOME"] = _local_cache_dir
    os.environ["XDG_CACHE_HOME"] = _local_cache_dir
    os.environ["HF_HUB_CACHE"] = _local_cache_dir
    os.environ["HF_HUB_OFFLINE"] = "1"

    sys.modules["k2"] = types.ModuleType("k2")

    import torch
    import speechbrain.utils.fetching
    import speechbrain.inference.interfaces
    
    try:
        import speechbrain.pretrained.interfaces
    except ImportError:
        pass

    _original_fetch = speechbrain.utils.fetching.fetch

    def _direct_local_fetch(filename, source, *args, **kwargs):
        if isinstance(source, str) and os.path.isdir(source):
            local_file = os.path.join(source, filename)
            if os.path.exists(local_file):
                return local_file
        return _original_fetch(filename, source, *args, **kwargs)

    speechbrain.utils.fetching.fetch = _direct_local_fetch

    if hasattr(speechbrain.inference.interfaces, "pretrained_from_hparams"):
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

    def make_pretrained_patch(mod):
        if mod and hasattr(mod, "Pretrained"):
            _orig_init = mod.Pretrained.__init__
            def _patched_init(self, *args, **kwargs):
                kwargs.pop("revision", None)
                kwargs.pop("use_auth_token", None)
                _orig_init(self, *args, **kwargs)
            mod.Pretrained.__init__ = _patched_init
            
            if hasattr(mod.Pretrained, "from_hparams"):
                _orig_from_hparams = mod.Pretrained.from_hparams
                @classmethod
                def _patched_from_hparams(cls, *args, **kwargs):
                    kwargs.pop('use_auth_token', None)
                    kwargs.pop('revision', None)
                    return _orig_from_hparams.__func__(cls, *args, **kwargs)
                mod.Pretrained.from_hparams = _patched_from_hparams

    make_pretrained_patch(speechbrain.inference.interfaces)
    if hasattr(speechbrain, "pretrained") and hasattr(speechbrain.pretrained, "interfaces"):
        make_pretrained_patch(speechbrain.pretrained.interfaces)

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

except Exception:
    _crash_log_startup_failure()
    sys.exit(1)

WHISPER_MODEL_PATH = os.path.join(application_path, "model_weights", "medium")
DIARIZATION_CONFIG_PATH = os.path.join(application_path, "model_weights", "diarization", "config.yaml")
FFMPEG_PATH = os.path.join(application_path, "ffmpeg.exe")
QWEN_MODEL_PATH = os.path.join(application_path, "model_weights", "qwen2.5-1.5b.gguf")