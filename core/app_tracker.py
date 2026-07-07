import subprocess
import time


IGNORED_APPS = {
    "Python",
    "Python Launcher",
    "Terminal",
    "iTerm2",
    "Visual Studio Code",
    "M87 TERM",
}


def run_applescript(script):
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=3,
        )

        if result.returncode != 0:
            return None

        return result.stdout.strip()

    except Exception:
        return None


def get_frontmost_app():
    script = '''
    tell application "System Events"
        set appName to name of first application process whose frontmost is true
        return appName
    end tell
    '''

    return run_applescript(script)


def is_valid_app(app_name):
    if not app_name:
        return False

    return app_name not in IGNORED_APPS


def restart_app(app_name):
    if not is_valid_app(app_name):
        return False

    quit_script = f'''
    tell application "{app_name}"
        quit
    end tell
    '''

    run_applescript(quit_script)

    time.sleep(1)

    subprocess.Popen(
        ["open", "-a", app_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return True