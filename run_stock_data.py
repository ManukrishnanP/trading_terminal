import subprocess
import sys
import time

script = "stock_data_to_sqlite.py"

while True:
    print(f"[watchdog] starting {script}")
    proc = subprocess.run([sys.executable, script])
    print(f"[watchdog] exited with code {proc.returncode}, restarting immediately...")
