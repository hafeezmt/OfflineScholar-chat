"""Start, stop and inspect the local OfflineScholar server."""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent
PID_FILE = BASE / "server.pid"
LOG_FILE = BASE / "server.log"
SETTINGS_FILE = BASE / "settings.json"
DEFAULT_CHAT_MODEL = "gemma3:1b"
DEFAULT_EMBED_MODEL = "snowflake-arctic-embed:33m"
DEFAULT_PORT = 7860


def load_settings():
    values = {
        "chat_model": DEFAULT_CHAT_MODEL,
        "embed_model": DEFAULT_EMBED_MODEL,
        "port": DEFAULT_PORT,
    }
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    if isinstance(saved, dict):
        values.update({key: saved[key] for key in values if key in saved})
    try:
        values["port"] = int(os.environ.get("OS_PORT") or values["port"])
    except (TypeError, ValueError):
        values["port"] = DEFAULT_PORT
    values["chat_model"] = os.environ.get("OS_MODEL") or values["chat_model"]
    values["embed_model"] = os.environ.get("OS_EMBED") or values["embed_model"]
    return values


def server_url(port=None):
    return f"http://127.0.0.1:{port or load_settings()['port']}"


def fetch_status(port=None, timeout=1):
    try:
        with urllib.request.urlopen(f"{server_url(port)}/api/status", timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return None


def _read_pid():
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid):
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, check=False)
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _pid_is_ours(pid):
    if os.name == "nt":
        return True
    proc_file = Path(f"/proc/{pid}/cmdline")
    if proc_file.exists():
        try:
            command = proc_file.read_bytes().decode("utf-8", "ignore")
        except OSError:
            return False
        return "app.py" in command and str(BASE) in command
    try:
        result = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                                capture_output=True, text=True, check=False)
    except OSError:
        return False
    return "app.py" in result.stdout and str(BASE) in result.stdout


def _clear_pid():
    try:
        PID_FILE.unlink()
    except OSError:
        pass


def _log_tail(lines=20):
    try:
        return "\n".join(LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()[-lines:])
    except OSError:
        return ""


def _wait_for_status(port, timeout, running=True, process=None):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = fetch_status(port)
        if bool(status) == running:
            return status
        if process is not None and process.poll() is not None:
            break
        time.sleep(0.25)
    return fetch_status(port)


def start(port=None, open_browser=False):
    settings = load_settings()
    port = port or settings["port"]
    status = fetch_status(port)
    if status:
        if open_browser:
            webbrowser.open(server_url(port))
        return server_url(port), False, status

    pid = _read_pid()
    if pid and _pid_alive(pid) and _pid_is_ours(pid):
        status = _wait_for_status(port, 15)
        if status:
            return server_url(port), False, status
        raise RuntimeError("OfflineScholar is starting slowly. Check server.log and try again.")

    _clear_pid()
    environment = os.environ.copy()
    environment.setdefault("OS_LOW_MEMORY", "1")
    environment.setdefault("OS_MODEL", settings["chat_model"])
    environment.setdefault("OS_EMBED", settings["embed_model"])
    environment["OS_PORT"] = str(port)

    arguments = [sys.executable, str(BASE / "app.py")]
    options = {
        "cwd": str(BASE),
        "env": environment,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        options["start_new_session"] = True

    with LOG_FILE.open("w", encoding="utf-8") as log:
        options["stdout"] = log
        options["stderr"] = subprocess.STDOUT
        process = subprocess.Popen(arguments, **options)
    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    status = _wait_for_status(port, 60, process=process)
    if not status:
        _terminate(process.pid)
        _clear_pid()
        detail = _log_tail()
        raise RuntimeError(f"OfflineScholar did not start.\n{detail}".strip())
    if open_browser:
        webbrowser.open(server_url(port))
    return server_url(port), True, status


def _terminate(pid):
    if not pid:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    for _ in range(40):
        if not _pid_alive(pid):
            return
        time.sleep(0.25)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def _stop_legacy_service():
    if os.name == "nt" or not shutil.which("systemctl"):
        return False
    service = Path.home() / ".config/systemd/user/offlinescholar.service"
    if not service.exists():
        return False
    result = subprocess.run(
        ["systemctl", "--user", "stop", "offlinescholar"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return result.returncode == 0


def _ollama_executable():
    found = shutil.which("ollama")
    if found:
        return found
    candidates = [Path("/usr/local/bin/ollama"), Path("/opt/homebrew/bin/ollama")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "Programs" / "Ollama" / "ollama.exe")
    return str(next((path for path in candidates if path.exists()), "")) or None


def _http_unload(model):
    body = json.dumps({"model": model, "keep_alive": 0}).encode("utf-8")
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate", data=body,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5):
            pass
    except (OSError, urllib.error.URLError):
        pass


def unload_models(models):
    executable = _ollama_executable()
    for model in sorted({model for model in models if model}):
        if executable:
            result = subprocess.run([executable, "stop", model],
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                    check=False)
            if result.returncode == 0:
                continue
        _http_unload(model)


def stop(port=None):
    settings = load_settings()
    port = port or settings["port"]
    status = fetch_status(port)
    models = {settings["chat_model"], settings["embed_model"]}
    if status:
        models.add(status.get("model"))
        models.add(status.get("embed_model"))

    stopped = _stop_legacy_service()
    pid = _read_pid()
    if pid and _pid_alive(pid) and _pid_is_ours(pid):
        _terminate(pid)
        stopped = True
    _clear_pid()
    remaining = _wait_for_status(port, 15, running=False) if status else None
    unload_models(models)
    if remaining:
        raise RuntimeError("The server did not stop. Check offlinescholar status and server.log.")
    return stopped


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="offlinescholar",
        description="Start or stop the local OfflineScholar study app.")
    commands = parser.add_subparsers(dest="command")
    up = commands.add_parser("up", aliases=["start"], help="start the app and open it")
    up.add_argument("--no-open", action="store_true", help="do not open the browser")
    commands.add_parser("stop", aliases=["down", "quit", "kill"], help="stop the app and unload models")
    commands.add_parser("restart", help="restart the app")
    commands.add_parser("status", aliases=["ps"], help="show whether the app is running")
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0
    try:
        if args.command in {"up", "start"}:
            url, started, _ = start(open_browser=not args.no_open)
            print(f"OfflineScholar is {'running' if started else 'already running'} at {url}")
            print("Stop it with: offlinescholar stop")
        elif args.command in {"stop", "down", "quit", "kill"}:
            stopped = stop()
            print("OfflineScholar stopped and models unloaded." if stopped
                  else "OfflineScholar is already stopped.")
        elif args.command == "restart":
            stop()
            url, _, _ = start(open_browser=True)
            print(f"OfflineScholar restarted at {url}")
        elif args.command in {"status", "ps"}:
            status = fetch_status()
            if status:
                print(f"OfflineScholar is running at {server_url()}")
                print(f"Model: {status.get('model')}")
                print("Stop it with: offlinescholar stop")
            else:
                print("OfflineScholar is stopped.")
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
