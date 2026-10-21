#!/usr/bin/env bash
# One-command installer for OfflineScholar on Linux and macOS.
set -euo pipefail

REPO_URL="${OS_REPO_URL:-https://github.com/hafeezmt/OfflineScholar-chat.git}"
ARCHIVE_URL="${OS_ARCHIVE_URL:-https://github.com/hafeezmt/OfflineScholar-chat/archive/refs/heads/main.tar.gz}"
INSTALL_DIR="${OS_INSTALL_DIR:-$HOME/OfflineScholar}"
CHAT_MODEL="${OS_CHAT_MODEL:-gemma3:1b}"
EMBED_MODEL="${OS_EMBED_MODEL:-snowflake-arctic-embed:33m}"
PORT="${OS_PORT:-7860}"
SKIP_DEPS="${OS_SKIP_DEPS:-0}"
SKIP_MODELS="${OS_SKIP_MODELS:-0}"
NO_START="${OS_NO_START:-0}"
URL="http://127.0.0.1:$PORT"

info() {
  printf '\n==> %s\n' "$*"
}

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

have() {
  command -v "$1" >/dev/null 2>&1
}

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  elif have sudo; then
    sudo "$@"
  else
    fail "Administrator access is required to install: $*"
  fi
}

install_system_packages() {
  if [ "$SKIP_DEPS" = "1" ]; then
    return 0
  fi
  if have dnf; then
    as_root dnf install -y "$@"
  elif have apt-get; then
    as_root apt-get update
    as_root apt-get install -y "$@"
  elif have pacman; then
    as_root pacman -Sy --needed --noconfirm "$@"
  else
    fail "Install these packages first: $*"
  fi
}

ensure_base_tools() {
  local missing=()
  have curl || missing+=(curl)
  have tar || missing+=(tar)
  have python3 || missing+=(python3)
  if [ "${#missing[@]}" -gt 0 ]; then
    info "Installing required tools: ${missing[*]}"
    if have dnf; then
      install_system_packages "${missing[@]}"
      have python3 || install_system_packages python3-pip
    elif have apt-get; then
      local apt_missing=()
      for item in "${missing[@]}"; do
        if [ "$item" = "python3" ]; then
          apt_missing+=(python3 python3-venv python3-pip)
        else
          apt_missing+=("$item")
        fi
      done
      install_system_packages "${apt_missing[@]}"
    elif [ "$(uname -s)" = "Darwin" ] && have brew; then
      for item in "${missing[@]}"; do
        [ "$item" = "python3" ] && brew install python || brew install "$item"
      done
    else
      install_system_packages "${missing[@]}"
    fi
  fi
  have curl || fail "curl is required"
  have tar || fail "tar is required"
  have python3 || fail "Python 3 is required"
  if ! python3 -m venv --help >/dev/null 2>&1; then
    info "Installing Python virtual-environment support"
    if have apt-get; then
      install_system_packages python3-venv
    elif have dnf; then
      install_system_packages python3-pip
    elif [ "$(uname -s)" = "Darwin" ] && have brew; then
      brew install python
    else
      fail "Install Python's venv module first"
    fi
  fi
  python3 -m venv --help >/dev/null 2>&1 || fail "Python's venv module is required"
}

verify_python() {
  python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
    || fail "Python 3.10 or newer is required"
}

install_code() {
  mkdir -p "$INSTALL_DIR"
  if [ -d "$INSTALL_DIR/.git" ] && have git; then
    info "Updating OfflineScholar in $INSTALL_DIR"
    git -C "$INSTALL_DIR" pull --ff-only
    return
  fi
  if [ -f "$INSTALL_DIR/app.py" ]; then
    info "Updating OfflineScholar files in $INSTALL_DIR"
    local tmp
    tmp="$(mktemp -d)"
    curl -fsSL "$ARCHIVE_URL" | tar -xz -C "$tmp" --strip-components=1
    cp -a "$tmp/." "$INSTALL_DIR/"
    rm -rf "$tmp"
    return
  fi
  if [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null || true)" ]; then
    fail "$INSTALL_DIR is not empty. Move it away or set OS_INSTALL_DIR to another folder."
  fi
  if have git; then
    info "Downloading OfflineScholar"
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
  else
    info "Downloading OfflineScholar"
    curl -fsSL "$ARCHIVE_URL" | tar -xz -C "$INSTALL_DIR" --strip-components=1
  fi
}

ensure_ollama() {
  if have ollama; then
    return
  fi
  info "Installing Ollama"
  case "$(uname -s)" in
    Linux)
      curl -fsSL https://ollama.com/install.sh | sh
      ;;
    Darwin)
      if have brew; then
        brew install ollama
      else
        fail "Install Ollama from https://ollama.com/download, then run this installer again."
      fi
      ;;
    *)
      fail "Unsupported operating system. Install Ollama from https://ollama.com/download."
      ;;
  esac
  have ollama || fail "Ollama was installed but is not on PATH. Open a new terminal and try again."
}

start_ollama() {
  if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    return
  fi
  if [ "$(uname -s)" = "Linux" ] && have systemctl && { [ "$(id -u)" -eq 0 ] || have sudo; }; then
    as_root systemctl start ollama >/dev/null 2>&1 || true
  elif [ "$(uname -s)" = "Darwin" ] && have brew; then
    brew services start ollama >/dev/null 2>&1 || true
  fi
  if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    info "Starting Ollama"
    nohup ollama serve > "$INSTALL_DIR/ollama.log" 2>&1 &
  fi
  for _ in {1..30}; do
    if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
      return
    fi
    sleep 1
  done
  fail "Ollama did not start. Open a terminal and run: ollama serve"
}

install_python_packages() {
  info "Setting up the Python environment"
  python3 -m venv "$INSTALL_DIR/venv"
  "$INSTALL_DIR/venv/bin/python" -m pip install --disable-pip-version-check -r "$INSTALL_DIR/requirements.txt"
}

write_start_script() {
  cat > "$INSTALL_DIR/start.sh" <<START_EOF
#!/usr/bin/env bash
set -e
cd "\$(dirname "\$0")"
export OS_LOW_MEMORY=1
export OS_MODEL="$CHAT_MODEL"
export OS_PORT="$PORT"
exec venv/bin/python app.py
START_EOF
  chmod +x "$INSTALL_DIR/start.sh"
}

start_app() {
  if [ "$NO_START" = "1" ]; then
    info "Skipping app startup because OS_NO_START=1"
    return
  fi
  if have systemctl && systemctl --user show-environment >/dev/null 2>&1; then
    local service_dir="$HOME/.config/systemd/user"
    mkdir -p "$service_dir"
    cat > "$service_dir/offlinescholar.service" <<SERVICE_EOF
[Unit]
Description=OfflineScholar local study assistant
After=network.target

[Service]
Type=simple
WorkingDirectory="$INSTALL_DIR"
ExecStart="$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/app.py"
Environment=OS_LOW_MEMORY=1
Environment=OS_MODEL=$CHAT_MODEL
Environment=OS_PORT=$PORT
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
SERVICE_EOF
    systemctl --user daemon-reload
    systemctl --user enable --now offlinescholar
    systemctl --user restart offlinescholar
  else
    if [ -f "$INSTALL_DIR/server.pid" ]; then
      kill "$(cat "$INSTALL_DIR/server.pid")" >/dev/null 2>&1 || true
    fi
    info "Starting OfflineScholar in the background"
    nohup env OS_LOW_MEMORY=1 OS_MODEL="$CHAT_MODEL" OS_PORT="$PORT" \
      "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/app.py" \
      > "$INSTALL_DIR/server.log" 2>&1 &
    echo "$!" > "$INSTALL_DIR/server.pid"
  fi

  info "Waiting for OfflineScholar"
  for _ in {1..60}; do
    if curl -fsS "$URL/api/status" >/dev/null 2>&1; then
      if [ "$(uname -s)" = "Darwin" ] && have open; then
        open "$URL" >/dev/null 2>&1 || true
      elif have xdg-open && { [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; }; then
        xdg-open "$URL" >/dev/null 2>&1 || true
      fi
      info "OfflineScholar is ready"
      printf 'Open: %s\n' "$URL"
      return
    fi
    sleep 1
  done
  if have systemctl; then
    systemctl --user status offlinescholar --no-pager >&2 || true
  fi
  fail "The app did not start. Check $INSTALL_DIR/server.log or run: systemctl --user status offlinescholar"
}

main() {
  case "$(uname -s)" in
    Linux|Darwin) ;;
    *) fail "This installer supports Linux and macOS. On Windows use install.ps1." ;;
  esac
  info "Installing OfflineScholar in $INSTALL_DIR"
  ensure_base_tools
  verify_python
  install_code
  ensure_ollama
  if [ "$SKIP_MODELS" != "1" ]; then
    start_ollama
    info "Downloading the chat model ($CHAT_MODEL)"
    ollama pull "$CHAT_MODEL"
    info "Downloading the notes model ($EMBED_MODEL)"
    ollama pull "$EMBED_MODEL"
  fi
  install_python_packages
  write_start_script
  start_app
  printf '\nInstalled in: %s\n' "$INSTALL_DIR"
  printf 'Start again later: %s/start.sh\n' "$INSTALL_DIR"
}

main "$@"
