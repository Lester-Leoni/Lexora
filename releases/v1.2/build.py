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

    # ФИКС (аудит, M4): раньше пре-сборочный аудит проверял ТОЛЬКО
    # lightning_fabric. icon-whishper.ico и ffmpeg.exe передаются в
    # PyInstaller как простые относительные имена (резолвятся относительно
    # текущей рабочей директории процесса — как и в исходном скрипте) и до
    # этого изменения никак не проверялись: их отсутствие приводило бы к
    # ошибке PyInstaller посередине долгой сборки, а не к быстрому,
    # понятному отказу до её начала.
    required_local_assets = ["icon-whishper.ico", "ffmpeg.exe"]
    for asset in required_local_assets:
        if not os.path.exists(asset):
            print(f"[-] ОШИБКА: Обязательный файл '{asset}' не найден в текущей рабочей директории ({os.getcwd()}).")
            sys.exit(1)
        print(f"[+] Найден обязательный файл: {asset}")

    # ФИКС (аудит, M4): источник model_weights раньше нигде не проверялся
    # кодом — копирование в dist/Lexora/model_weights было полностью ручным
    # шагом, зависящим от памяти разработчика между сессиями сборки.
    #
    # ВНИМАНИЕ — ПРОВЕРЬ ЭТОТ ПУТЬ: ниже предполагается, что исходная папка
    # model_weights лежит рядом с этим build.py (в корне проекта). Это
    # ПРЕДПОЛОЖЕНИЕ о структуре каталогов, а не подтверждённый факт — данных
    # о том, где у тебя физически лежат исходные веса модели до сборки, у
    # меня нет. Если реальный путь другой — поправь model_weights_source
    # ниже на актуальный.
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
        "--add-data=ffmpeg.exe;.",
        # --add-data=model_weights;model_weights УБРАН осознанно: app.py читает веса
        # по пути application_path/model_weights (рядом с exe), а не из
        # _internal. Этот флаг только дублировал ~1.5GB весов внутрь
        # _internal без всякой пользы, что и было основной причиной
        # превышения лимита Inno Setup (~3.91GB) на единый Setup.exe.
        # Папка model_weights копируется в dist/Lexora автоматически НИЖЕ,
        # сразу после успешной сборки PyInstaller (см. шаг копирования в
        # конце main()) — без ручного шага, ранее опирающегося на память
        # разработчика между сессиями сборки.
        "--collect-all=pyannote.audio",               # Полный сбор пакета со всеми модулями
        "--collect-all=speechbrain",                  # Полный сбор пакета (исправляет WinError 3)
        "app.py"
    ]

    cmd_string = " ".join(command)
    print("\n[*] Запуск PyInstaller с внедренными патчами безопасности...")

    process = subprocess.Popen(cmd_string, shell=True)
    process.wait()

    if process.returncode == 0:
        print("\n[+] СБОРКА PYINSTALLER УСПЕШНО ЗАВЕРШЕНА.")

        # ФИКС (аудит, M4): автоматизированное копирование model_weights
        # вместо ручного шага. Проверяет реальный итоговый размер
        # скопированных данных, чтобы несостоявшееся/частичное копирование
        # не прошло незамеченным.
        dist_model_weights = os.path.join("dist", "Lexora", "model_weights")
        print(f"\n[*] Копирование model_weights -> {dist_model_weights} ...")
        try:
            if os.path.exists(dist_model_weights):
                shutil.rmtree(dist_model_weights)
            shutil.copytree(model_weights_source, dist_model_weights)
            copied_size = sum(
                os.path.getsize(os.path.join(root, f))
                for root, _, files in os.walk(dist_model_weights)
                for f in files
            )
            print(f"[+] model_weights скопированы успешно. Объём: {copied_size / (1024 ** 3):.2f} GB")
        except Exception as e:
            print(f"[-] ОШИБКА копирования model_weights: {e}")
            print("[-] Сборка PyInstaller прошла успешно, но dist/Lexora НЕ готов к запуску/упаковке.")
            sys.exit(1)

        print("\n[+] СБОРКА ПОЛНОСТЬЮ ЗАВЕРШЕНА.")
        print("[!] Проверь исполняемый файл в директории 'dist/Lexora/Lexora.exe'")
    else:
        print("\n[-] ОШИБКА СБОРКИ PYINSTALLER.")

if __name__ == "__main__":
    main()