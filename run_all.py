import os
import sys
import subprocess
import signal
import time
from pathlib import Path

def find_env_files():
    # Agar argument berilgan bo'lsa, ularni olamiz
    if len(sys.argv) > 1:
        return sys.argv[1:]

    # Aks holda mavjud .env.bot* yoki .env fayllarni qidiramiz
    cwd = Path(__file__).resolve().parent
    env_files = sorted([f.name for f in cwd.glob(".env.bot*") if not f.name.endswith(".example")])
    if not env_files:
        if (cwd / ".env").exists():
            env_files = [".env"]
    return env_files


def main():
    env_files = find_env_files()
    if not env_files:
        print("❌ Hech qanday .env yoki .env.bot* fayllar topilmadi!")
        print("Masalan: .env.bot1.example dan nusxa oling: cp .env.bot1.example .env.bot1")
        sys.exit(1)

    python_executable = sys.executable
    processes = []

    print("=" * 60)
    print(f"🚀 SuperTaxi Botlar ishga tushirilmoqda: {len(env_files)} ta bot")
    for f in env_files:
        print(f"  • {f}")
    print("=" * 60)
    print("💡 To'xtatish uchun Ctrl + C bosing.\n")

    for env_file in env_files:
        cmd = [python_executable, "main.py", env_file]
        p = subprocess.Popen(cmd)
        processes.append((env_file, p))
        time.sleep(1)

    def signal_handler(sig, frame):
        print("\n\n🛑 Barcha botlar to'xtatilmoqda...")
        for env_file, p in processes:
            if p.poll() is None:
                p.terminate()
        for env_file, p in processes:
            p.wait()
        print("✅ Barcha botlar muvaffaqiyatli to'xtatildi.")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        while True:
            # Jarayonlar holatini monitoring qilish
            for env_file, p in processes:
                ret = p.poll()
                if ret is not None:
                    print(f"⚠️ Bot ({env_file}) to'xtadi! Chiqish kodi: {ret}")
            time.sleep(2)
    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == "__main__":
    main()
