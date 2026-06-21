import os
import sys
import subprocess

def main():
    print("[*] Lexora v1.1 — сборка PyInstaller...")

    # Сборка аргументов PyInstaller
    command = [
        "pyinstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--icon=icon-whishper.ico",
        "--name=Lexora",
        "--add-data=model_weights;model_weights",
        "--add-data=ffmpeg.exe;.",
        "app.py"
    ]

    cmd_string = " ".join(command)
    print("\n[*] Запуск PyInstaller...")

    process = subprocess.Popen(cmd_string, shell=True)
    process.wait()

    if process.returncode == 0:
        print("\n[+] СБОРКА УСПЕШНО ЗАВЕРШЕНА.")
        print("[!] Проверь исполняемый файл в директории 'dist/Lexora/Lexora.exe'")
    else:
        print("\n[-] ОШИБКА СБОРКИ.")

if __name__ == "__main__":
    main()
