import os
import sys
import traceback
import types
import tempfile

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

except Exception:
    _crash_log_startup_failure()
    sys.exit(1)

# Экспорт путей для других модулей
WHISPER_MODEL_PATH = os.path.join(application_path, "model_weights", "medium")
DIARIZATION_CONFIG_PATH = os.path.join(application_path, "model_weights", "diarization", "config.yaml")
FFMPEG_PATH = os.path.join(application_path, "ffmpeg.exe")