import os
import sys
import shutil
import subprocess
import importlib.util
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def find_package_path(package_name):
    spec = importlib.util.find_spec(package_name)
    if spec is None or spec.origin is None:
        return None
    return os.path.dirname(spec.origin)

def safe_copy(src: str, dst: str, max_retries: int = 5, delay: float = 0.5):
    """Обертка над I/O операциями Windows с механизмом Exponential Backoff против блокировок AV."""
    for attempt in range(max_retries):
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
            logging.info(f"[+] Успешно скопировано/обновлено: {dst}")
            return
        except PermissionError as e:
            logging.warning(f"[-] Файл заблокирован антивирусом/индексатором ({src}). Попытка {attempt + 1}/{max_retries} через {delay}с...")
            time.sleep(delay)
            delay *= 2  # Экспоненциальное увеличение задержки
        except Exception as e:
            logging.error(f"[-] Критическая ошибка I/O при копировании {src}: {e}")
            raise
            
    raise PermissionError(f"[-] Не удалось скопировать {src} после {max_retries} попыток. Файл заблокирован сторонним системным процессом Windows.")

def main():
    print("[*] Аудит зависимостей перед компиляцией...")

    fabric_path = find_package_path("lightning_fabric")
    if not fabric_path:
        print("[-] ОШИБКА: Библиотека lightning_fabric не найдена.")
        sys.exit(1)

    version_file_path = os.path.join(fabric_path, "version.info")
    if not os.path.exists(version_file_path):
        print(f"[-] ОШИБКА: Файл {version_file_path} не существует.")
        sys.exit(1)

    print(f"[+] Найден критический файл: {version_file_path}")

    required_local_assets = ["icon-whishper.ico", "ffmpeg.exe"]
    for asset in required_local_assets:
        if not os.path.exists(asset):
            print(f"[-] ОШИБКА: Обязательный файл '{asset}' не найден в рабочей директории ({os.getcwd()}).")
            sys.exit(1)
        print(f"[+] Найден обязательный файл: {asset}")

    model_weights_source = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model_weights")
    if not os.path.isdir(model_weights_source):
        print(f"[-] ОШИБКА: Исходная папка model_weights не найдена: {model_weights_source}")
        sys.exit(1)
    print(f"[+] Найдена исходная папка model_weights: {model_weights_source}")

    separator = ";" if os.name == "nt" else ":"
    add_data_arg = f"{version_file_path}{separator}lightning_fabric"

    # Изоляция PyInstaller внутри активного venv
    venv_bin_dir = os.path.dirname(sys.executable)
    pyinstaller_bin = os.path.join(venv_bin_dir, "pyinstaller.exe")
    
    if not os.path.exists(pyinstaller_bin):
        pyinstaller_bin = "pyinstaller"

    # Изоляция временных путей сборки для предотвращения Race Condition в CI/CD
    work_path = "build_temp_isolated"

    command = [
        f'"{pyinstaller_bin}"',
        "--clean",
        "--noconfirm",
        "--onedir",
        "--windowed",
        f"--workpath={work_path}",
        "--icon=icon-whishper.ico",
        "--name=Lexora",
        f"--add-data={add_data_arg}",
        "--collect-all=pyannote.audio",
        "--collect-all=speechbrain",
        "--hidden-import=bootstrap",
        "main.py"
    ]

    cmd_string = " ".join(command)
    print("\n[*] Запуск изолированной сборки PyInstaller...")

    # Переход на безопасный subprocess.run вместо устаревшего Popen
    result = subprocess.run(cmd_string, shell=True, capture_output=False)

    if result.returncode == 0:
        print("\n[+] СБОРКА PYINSTALLER УСПЕШНО ЗАВЕРШЕНА.")
        dist_root = os.path.join("dist", "Lexora")

        # Интеграция ресурсов через отказоустойчивый safe_copy (Exponential Backoff)
        print(f"[*] Копирование ffmpeg.exe -> {dist_root} ...")
        safe_copy("ffmpeg.exe", os.path.join(dist_root, "ffmpeg.exe"))

        dist_fonts = os.path.join(dist_root, "fonts")
        print(f"[*] Инициализация директории шрифтов -> {dist_fonts} ...")
        os.makedirs(dist_fonts, exist_ok=True)
        win_fonts_source = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "consola.ttf")
        if os.path.exists(win_fonts_source):
            safe_copy(win_fonts_source, os.path.join(dist_fonts, "consola.ttf"))

        dist_model_weights = os.path.join(dist_root, "model_weights")
        print(f"[*] Копирование model_weights -> {dist_model_weights} ...")
        if os.path.exists(dist_model_weights):
            max_retries_rm = 5
            delay_rm = 0.5
            for attempt in range(max_retries_rm):
                try:
                    shutil.rmtree(dist_model_weights)
                    break
                except Exception as e:
                    if attempt < max_retries_rm - 1:
                        logging.warning(f"[!] Предупреждение при очистке старых весов: {e}. Попытка {attempt + 1}/{max_retries_rm} через {delay_rm}с...")
                        time.sleep(delay_rm)
                        delay_rm *= 2
                    else:
                        logging.warning(f"[!] Не удалось очистить старые веса после {max_retries_rm} попыток: {e}")
        
        safe_copy(model_weights_source, dist_model_weights)

        print("\n[+] СБОРКА ПОЛНОСТЬЮ ЗАВЕРШЕНА И ЗАЩИЩЕНА ОТ ПРОЦЕССОВ LOCK-ИРОВАНИЯ Windows.")
    else:
        print("\n[-] ОШИБКА СБОРКИ PYINSTALLER.")
        sys.exit(1)

if __name__ == "__main__":
    main()