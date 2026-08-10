import csv
import datetime
import os
import shutil
import subprocess
import time
from pathlib import Path

OUT = Path(__file__).parent
STOP = OUT / "resource-monitor.stop"
CSV = OUT / "resource-monitor.csv"

def cpu_stat():
    with open("/proc/stat", encoding="utf-8") as f:
        p = f.readline().split()
    values = list(map(int, p[1:]))
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values), idle

def memory():
    vals = {}
    with open("/proc/meminfo", encoding="utf-8") as f:
        for line in f:
            k, v = line.split(":", 1)
            vals[k] = int(v.strip().split()[0]) * 1024
    total = vals["MemTotal"]
    available = vals.get("MemAvailable", vals.get("MemFree", 0))
    return total, total - available

def gpu():
    try:
        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total,"
                "power.draw,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        row = r.stdout.strip().splitlines()[0]
        return [x.strip() for x in row.split(",")]
    except Exception:
        return ["", "", "", "", ""]

header = [
    "timestamp_utc",
    "cpu_pct",
    "load1",
    "memory_used_bytes",
    "memory_total_bytes",
    "disk_used_bytes",
    "disk_total_bytes",
    "gpu_util_pct",
    "gpu_mem_used_mib",
    "gpu_mem_total_mib",
    "gpu_power_w",
    "gpu_temp_c",
]

last_total, last_idle = cpu_stat()

with CSV.open("w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(header)
    f.flush()

    while not STOP.exists():
        time.sleep(2)

        total, idle = cpu_stat()
        dt = total - last_total
        di = idle - last_idle

        cpu_pct = 0.0 if dt <= 0 else 100.0 * (dt - di) / dt
        last_total, last_idle = total, idle

        mem_total, mem_used = memory()
        disk = shutil.disk_usage(".")
        g = gpu()

        try:
            load1 = os.getloadavg()[0]
        except Exception:
            load1 = 0.0

        writer.writerow(
            [
                datetime.datetime.now(datetime.timezone.utc).isoformat(),
                round(cpu_pct, 3),
                load1,
                mem_used,
                mem_total,
                disk.used,
                disk.total,
                *g,
            ]
        )
        f.flush()
