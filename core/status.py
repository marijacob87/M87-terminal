import json
import urllib.request
from datetime import datetime

import psutil

from core.network_volumes import get_network_status

def get_porto_temp():
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            "?latitude=41.1579&longitude=-8.6291"
            "&current=temperature_2m"
            "&temperature_unit=celsius"
            "&timezone=Europe%2FLisbon"
        )

        with urllib.request.urlopen(url, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))

        temperature = round(float(data["current"]["temperature_2m"]))
        return f"{temperature}°C"

    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
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
        "ram": get_ram_usage(),
        "cpu": get_cpu_usage(),
        "networks": get_network_status(),
    }
