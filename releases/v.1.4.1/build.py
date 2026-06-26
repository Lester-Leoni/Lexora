import os
import sys
import shutil
import subprocess
import importlib.util

def find_package_path(package_name):
    spec = importlib.util.find_spec(package_name)
    if spec is None or spec.origin is None:
        return None
    return os.path.dirname(spec.origin)

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

    # Аудит локальных ассетов перед долгой компиляцией
    required_local_assets = ["icon-whishper.ico", "ffmpeg.exe"]
    for asset in required_local_assets:
        if not os.path.exists(asset):
            print(f"[-] ОШИБКА: Обязательный файл '{asset}' не найден в текущей рабочей директории ({os.getcwd()}).")
            sys.exit(1)
        print(f"[+] Найден обязательный файл: {asset}")

    # Проверка источника весов ИИ-моделей
    model_weights_source = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model_weights")
    if not os.path.isdir(model_weights_source):
        print(f"[-] ОШИБКА: Исходная папка model_weights не найдена по пути: {model_weights_source}")
        print("[-] Проверь и поправь переменную model_weights_source в build.py.")
        sys.exit(1)
    print(f"[+] Найдена исходная папка model_weights: {model_weights_source}")

    separator = ";" if os.name == "nt" else ":"
    add_data_arg = f"{version_file_path}{separator}lightning_fabric"

    # Сборка аргументов PyInstaller
    command = [
        "pyinstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--icon=icon-whishper.ico",
        "--name=Lexora",
        f"--add-data={add_data_arg}",                 # Внедрение патча lightning_fabric
        # Флаг --add-data для ffmpeg удален. Копирование выполняется силами Python напрямую в dist,
        # чтобы избежать случайного попадания файла внутрь папки _internal.
        "--collect-all=pyannote.audio",               # Полный сбор пакета со всеми модулями [cite: 40]
        "--collect-all=speechbrain",                  # Полный сбор пакета (исправляет WinError 3) [cite: 40]
        "app.py"
    ]

    cmd_string = " ".join(command)
    print("\n[*] Запуск PyInstaller с внедренными патчами безопасности...")

    process = subprocess.Popen(cmd_string, shell=True)
    process.wait()

    if process.returncode == 0:
        print("\n[+] СБОРКА PYINSTALLER УСПЕШНО ЗАВЕРШЕНА.")

        dist_root = os.path.join("dist", "Lexora")

        # ======================================================================
        # АВТОМАТИЗАЦИЯ СБОРКИ РЕСУРСОВ ДЛЯ ВЕРСИИ 1.3
        # ======================================================================
        
        # 1. Копирование ffmpeg.exe в корень сборки (Рядом с Lexora.exe) [cite: 52, 54]
        print(f"[*] Копирование ffmpeg.exe -> {dist_root} ...")
        try:
            shutil.copy("ffmpeg.exe", os.path.join(dist_root, "ffmpeg.exe"))
            print("[+] Файл ffmpeg.exe успешно интегрирован.")
        except Exception as e:
            print(f"[-] ОШИБКА копирования ffmpeg.exe: {e}")
            sys.exit(1)

        # 2. Создание папки шрифтов и интеграция consola.ttf для дизайн-системы [cite: 52, 55]
        dist_fonts = os.path.join(dist_root, "fonts")
        print(f"[*] Инициализация директории шрифтов -> {dist_fonts} ...")
        try:
            os.makedirs(dist_fonts, exist_ok=True)
            # Извлекаем стандартный моноширинный шрифт Windows для терминального окна
            win_fonts_source = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "consola.ttf")
            if os.path.exists(win_fonts_source):
                shutil.copy(win_fonts_source, os.path.join(dist_fonts, "consola.ttf"))
                print("[+] Шрифты интерфейса успешно подготовлены.")
            else:
                print("[!] ПРЕДУПРЕЖДЕНИЕ: Системный шрифт consola.ttf не найден. Интерфейс может использовать fallback.")
        except Exception as e:
            print(f"[-] ОШИБКА подготовки шрифтов: {e}")
            sys.exit(1)

        # 3. Автоматизированное копирование model_weights [cite: 51, 56]
        dist_model_weights = os.path.join(dist_root, "model_weights")
        print(f"[*] Копирование model_weights -> {dist_model_weights} ...")
        try:
            if os.path.exists(dist_model_weights):
                shutil.rmtree(dist_model_weights)
            shutil.copytree(model_weights_source, dist_model_weights)
            copied_size = sum(
                os.path.getsize(os.path.join(root, f))
                for root, _, files in os.walk(dist_model_weights)
                for f in files
            )
            print(f"[+] model_weights скопированы успешно. Объём: {copied_size / (1024 ** 3):.2f} GB [cite: 49]")
        except Exception as e:
            print(f"[-] ОШИБКА копирования model_weights: {e}")
            print("[-] Сборка PyInstaller прошла успешно, но dist/Lexora НЕ готов к запуску/упаковке.")
            sys.exit(1)

        print("\n[+] СБОРКА ПОЛНОСТЬЮ ЗАВЕРШЕНА.")
        print("[!] Проверь исполняемый файл в директории 'dist/Lexora/Lexora.exe' [cite: 45]")
    else:
        print("\n[-] ОШИБКА СБОРКИ PYINSTALLER.")

if __name__ == "__main__":
    main()