import subprocess
import urllib.request
from datetime import datetime

import psutil

from core.network_volumes import get_network_status

def get_battery():
    try:
        result = subprocess.run(
            ["pmset", "-g", "batt"],
            capture_output=True,
            text=True,
            timeout=2,
        )

        output = result.stdout

        for part in output.split():
            if "%" in part:
                return part.replace(";", "")

        return "100%"

    except Exception:
        return "100%"


def get_porto_temp():
    try:
        url = "https://wttr.in/Porto?format=%t"

        with urllib.request.urlopen(url, timeout=3) as response:
            temp = response.read().decode("utf-8").strip()

        return temp.replace("+", "")

    except Exception:
        return "--°C"


def get_ram_usage():
    return f"{int(psutil.virtual_memory().percent)}%"


def get_cpu_usage():
    return f"{int(psutil.cpu_percent(interval=0.3))}%"


def get_status_data(weather_temp):
    now = datetime.now()

    dias = [
        "Seg.",
        "Ter.",
        "Qua.",
        "Qui.",
        "Sex.",
        "Sáb.",
        "Dom.",
    ]

    return {
        "data": f"{dias[now.weekday()]} {now.strftime('%d/%m/%Y')}",
        "hora": now.strftime("%H:%M"),
        "temp": weather_temp,
        "battery": get_battery(),
        "ram": get_ram_usage(),
        "cpu": get_cpu_usage(),
        "networks": get_network_status(),
    }
