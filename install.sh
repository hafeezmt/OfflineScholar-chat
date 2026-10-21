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
SKIP_DESKTOP="${OS_SKIP_DESKTOP:-0}"

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
        if [ "$item" = "python3" ]; then
          brew install python
        else
          brew install "$item"
        fi
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
    git -C "$INSTALL_DIR" fetch --depth 1 "$REPO_URL" main
    git -C "$INSTALL_DIR" reset --hard FETCH_HEAD
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

ensure_desktop_toolkit() {
  [ "$SKIP_DESKTOP" = "1" ] && return
  python3 -c 'import tkinter' >/dev/null 2>&1 && return
  if [ "$(uname -s)" = "Darwin" ]; then
    if have brew; then
      info "Installing desktop app support"
      brew install python-tk >/dev/null 2>&1 || true
    fi
  elif [ "$(uname -s)" = "Linux" ]; then
    if [ "$(id -u)" -ne 0 ] && ! have sudo; then
      info "Desktop app support needs Tk; using the command-line version only"
      SKIP_DESKTOP=1
      return
    fi
    info "Installing desktop app support"
    if have dnf; then
      install_system_packages python3-tkinter
    elif have apt-get; then
      install_system_packages python3-tk
    elif have pacman; then
      install_system_packages tk
    else
      info "Could not install Tk; using the command-line version only"
      SKIP_DESKTOP=1
      return
    fi
  fi
  python3 -c 'import tkinter' >/dev/null 2>&1 || {
    info "Desktop app support is unavailable; the command-line version will still work"
    SKIP_DESKTOP=1
  }
}

write_settings() {
  cat > "$INSTALL_DIR/settings.json" <<SETTINGS_EOF
{
  "chat_model": "$CHAT_MODEL",
  "embed_model": "$EMBED_MODEL",
  "port": $PORT
}
SETTINGS_EOF
}

install_cli() {
  local bin_dir="$HOME/.local/bin"
  mkdir -p "$bin_dir"
  chmod +x "$INSTALL_DIR/offlinescholar"
  ln -sf "$INSTALL_DIR/offlinescholar" "$bin_dir/offlinescholar"
  ln -sf "$INSTALL_DIR/offlinescholar" "$bin_dir/offlinescolar"
  case ":$PATH:" in
    *":$bin_dir:"*) ;;
    *)
      local rc="$HOME/.profile"
      case "${SHELL:-}" in
        *zsh) rc="$HOME/.zshrc" ;;
        *bash) rc="$HOME/.bashrc" ;;
      esac
      touch "$rc"
      if ! grep -q 'OfflineScholar command' "$rc" 2>/dev/null; then
        printf "\n# OfflineScholar command\nexport PATH=\"%s:\$PATH\"\n" "$bin_dir" >> "$rc"
      fi
      ;;
  esac
}

write_start_script() {
  cat > "$INSTALL_DIR/start.sh" <<START_EOF
#!/usr/bin/env bash
exec "$INSTALL_DIR/offlinescholar" up "\$@"
START_EOF
  chmod +x "$INSTALL_DIR/start.sh"
}

install_desktop_linux() {
  local apps="$HOME/.local/share/applications"
  mkdir -p "$apps"
  cat > "$apps/offlinescholar.desktop" <<DESKTOP_EOF
[Desktop Entry]
Type=Application
Name=OfflineScholar
Comment=Private offline study assistant
Exec="$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/desktop.py"
Icon=$INSTALL_DIR/web/favicon.svg
Terminal=false
Categories=Education;Utility;
StartupNotify=true
DESKTOP_EOF
  chmod +x "$apps/offlinescholar.desktop"
  if have update-desktop-database; then
    update-desktop-database "$apps" >/dev/null 2>&1 || true
  fi
}

install_desktop_macos() {
  local app="$HOME/Applications/OfflineScholar.app"
  mkdir -p "$app/Contents/MacOS"
  cat > "$app/Contents/Info.plist" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>OfflineScholar</string>
  <key>CFBundleIdentifier</key><string>com.offlinescholar.app</string>
  <key>CFBundleName</key><string>OfflineScholar</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST_EOF
  cat > "$app/Contents/MacOS/OfflineScholar" <<MAC_EOF
#!/bin/bash
exec "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/desktop.py"
MAC_EOF
  chmod +x "$app/Contents/MacOS/OfflineScholar"
}

install_desktop() {
  if [ "$SKIP_DESKTOP" = "1" ]; then
    info "Skipping the desktop app because OS_SKIP_DESKTOP=1"
    return
  fi
  case "$(uname -s)" in
    Linux) install_desktop_linux ;;
    Darwin) install_desktop_macos ;;
  esac
}

remove_old_service() {
  local service="$HOME/.config/systemd/user/offlinescholar.service"
  [ "$(uname -s)" = "Linux" ] && have systemctl || return 0
  [ -f "$service" ] || return 0
  info "Turning off the old always-on service"
  systemctl --user disable --now offlinescholar >/dev/null 2>&1 || true
  rm -f "$service"
  systemctl --user daemon-reload >/dev/null 2>&1 || true
}

stop_previous() {
  if [ -x "$INSTALL_DIR/venv/bin/python" ] && [ -f "$INSTALL_DIR/manage.py" ]; then
    "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/manage.py" stop >/dev/null 2>&1 || true
  fi
}

main() {
  case "$(uname -s)" in
    Linux|Darwin) ;;
    *) fail "This installer supports Linux and macOS. On Windows use install.ps1." ;;
  esac
  case "$PORT" in
    ''|*[!0-9]*) fail "OS_PORT must be a number" ;;
  esac
  info "Installing OfflineScholar in $INSTALL_DIR"
  ensure_base_tools
  verify_python
  ensure_desktop_toolkit
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
  write_settings
  install_cli
  write_start_script
  install_desktop
  remove_old_service
  stop_previous
  printf '\nInstalled in: %s\n' "$INSTALL_DIR"
  printf '\nStart OfflineScholar from any terminal:\n'
  printf '  offlinescholar up\n'
  printf '\nStop it and release RAM:\n'
  printf '  offlinescholar stop\n'
  if ! command -v offlinescholar >/dev/null 2>&1; then
    printf '\nOpen a new terminal before using the offlinescholar command.\n'
  fi
  if [ "$SKIP_DESKTOP" != "1" ]; then
    printf '\nOr open the OfflineScholar app from your applications menu.\n'
  fi
}

main "$@"
