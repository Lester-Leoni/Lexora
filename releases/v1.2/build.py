import os
import sys
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
        "--add-data=model_weights;model_weights",
        "--add-data=ffmpeg.exe;.",
        "--collect-all=pyannote.audio",               # Полный сбор пакета со всеми модулями
        "--collect-all=speechbrain",                  # Полный сбор пакета (исправляет WinError 3)
        "app.py"
    ]

    cmd_string = " ".join(command)
    print("\n[*] Запуск PyInstaller с внедренными патчами безопасности...")
    
    process = subprocess.Popen(cmd_string, shell=True)
    process.wait()
    
    if process.returncode == 0:
        print("\n[+] СБОРКА УСПЕШНО ЗАВЕРШЕНА.")
        print("[!] Проверь исполняемый файл в директории 'dist/Lexora/Lexora.exe'")
    else:
        print("\n[-] ОШИБКА СБОРКИ.")

if __name__ == "__main__":
    main()