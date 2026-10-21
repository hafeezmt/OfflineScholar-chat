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
MODELS_REQUESTED="${OS_MODELS:-}"
MODEL_SELECTION=()

MODEL_NAMES=("gemma3:1b" "qwen2.5:1.5b" "gemma4:e2b-it-qat")
MODEL_LABELS=("Gemma 3 1B" "Qwen 2.5 1.5B" "Gemma 4 E2B QAT")
MODEL_SIZES_MB=(806 986 4403)
MODEL_NOTES=(
  "recommended for 8 GB laptops"
  "better reasoning, still light"
  "best answers, needs more free RAM"
)
EMBED_SIZE_MB=67
DISK_MARGIN_MB=1024

TTY_FD=0
if { exec 3<>/dev/tty; } 2>/dev/null; then
  TTY_FD=3
fi

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

human_size() {
  local mb="${1:-0}"
  if [ "$mb" -ge 1024 ] 2>/dev/null; then
    awk -v n="$mb" 'BEGIN { printf "%.1f GB", n / 1024 }'
  else
    printf '%s MB' "$mb"
  fi
}

model_size_mb() {
  local name="$1" i
  for i in "${!MODEL_NAMES[@]}"; do
    if [ "${MODEL_NAMES[$i]}" = "$name" ]; then
      printf '%s' "${MODEL_SIZES_MB[$i]}"
      return
    fi
  done
  printf '0'
}

disk_free_mb() {
  local kb
  kb="$(df -Pk "$INSTALL_DIR" 2>/dev/null | awk 'NR==2 { print $4 }')"
  printf '%s' "$(( ${kb:-0} / 1024 ))"
}

ram_total_mb() {
  if [ -r /proc/meminfo ]; then
    awk '/^MemTotal:/ { printf "%d", $2 / 1024 }' /proc/meminfo
  elif [ "$(uname -s)" = "Darwin" ]; then
    local bytes
    bytes="$(sysctl -n hw.memsize 2>/dev/null || printf 0)"
    printf '%s' "$(( bytes / 1048576 ))"
  else
    printf '0'
  fi
}

ram_available_mb() {
  if [ -r /proc/meminfo ]; then
    awk '/^MemAvailable:/ { printf "%d", $2 / 1024 }' /proc/meminfo
  else
    printf '0'
  fi
}

print_model_menu() {
  local free_mb="$1" total_mb="$2" available_mb="$3" i
  printf '\n'
  if [ "$free_mb" -gt 0 ]; then
    printf 'Disk: %s free in %s\n' "$(human_size "$free_mb")" "$INSTALL_DIR"
  else
    printf 'Disk: could not determine free space in %s\n' "$INSTALL_DIR"
  fi
  if [ "$available_mb" -gt 0 ]; then
    printf 'RAM: %s total, %s available\n' "$(human_size "$total_mb")" "$(human_size "$available_mb")"
  else
    printf 'RAM: %s total\n' "$(human_size "$total_mb")"
  fi
  printf '\nAvailable chat models (select one or more):\n'
  for i in "${!MODEL_NAMES[@]}"; do
    printf '  %d) %-18s %8s  %s\n' "$((i + 1))" "${MODEL_LABELS[$i]}" \
      "$(human_size "${MODEL_SIZES_MB[$i]}")" "${MODEL_NOTES[$i]}"
  done
  printf '\nThe notes search model (%s) will also be installed.\n' "$(human_size "$EMBED_SIZE_MB")"
}

read_model_menu() {
  local answer token name invalid i
  local -a picked
  while :; do
    printf 'Select model numbers separated by spaces, or q to cancel [1]: ' >&3
    if ! IFS= read -r answer <&3; then
      fail "Could not read your model choice. Set OS_MODELS=\"gemma3:1b\" and try again."
    fi
    answer="${answer:-1}"
    case "$answer" in
      q|Q|quit|QUIT) fail "Installation cancelled. No models were downloaded." ;;
    esac
    invalid=0
    picked=()
    answer="${answer//,/ }"
    for token in $answer; do
      case "$token" in
        ''|*[!0-9]*) invalid=1; break ;;
      esac
      if [ "$token" -lt 1 ] || [ "$token" -gt "${#MODEL_NAMES[@]}" ]; then
        invalid=1
        break
      fi
      i=$((token - 1))
      name="${MODEL_NAMES[$i]}"
      case " ${picked[*]} " in
        *" $name "*) ;;
        *) picked+=("$name") ;;
      esac
    done
    if [ "$invalid" -eq 0 ] && [ "${#picked[@]}" -gt 0 ]; then
      MODEL_SELECTION=("${picked[@]}")
      return
    fi
    printf 'Enter numbers from 1 to %d.\n' "${#MODEL_NAMES[@]}" >&2
  done
}

parse_model_list() {
  local raw="$1" item
  local -a requested
  requested=()
  raw="${raw//,/ }"
  for item in $raw; do
    [ -z "$item" ] && continue
    if [ "$(model_size_mb "$item")" -eq 0 ]; then
      printf 'Warning: no download-size estimate for %s; disk check is approximate.\n' "$item" >&2
    fi
    case " ${requested[*]} " in
      *" $item "*) ;;
      *) requested+=("$item") ;;
    esac
  done
  if [ "${#requested[@]}" -eq 0 ]; then
    fail "OS_MODELS or OS_CHAT_MODEL did not contain a model name."
  fi
  MODEL_SELECTION=("${requested[@]}")
}

choose_models() {
  if [ -n "$MODELS_REQUESTED" ]; then
    info "Using the chat model selection from OS_MODELS"
    parse_model_list "$MODELS_REQUESTED"
  elif [ -n "${OS_CHAT_MODEL:-}" ]; then
    info "Using the chat model from OS_CHAT_MODEL"
    parse_model_list "$OS_CHAT_MODEL"
  elif [ "$SKIP_MODELS" = "1" ]; then
    MODEL_SELECTION=("$CHAT_MODEL")
  elif [ "$TTY_FD" -eq 3 ]; then
    info "Choose the chat model(s) to download"
    print_model_menu "$(disk_free_mb)" "$(ram_total_mb)" "$(ram_available_mb)"
    read_model_menu
    printf 'Selected: %s\n' "${MODEL_SELECTION[*]}"
  else
    fail "No terminal is available to choose a model. Set OS_MODELS=\"gemma3:1b\" (or OS_SKIP_MODELS=1) and run again."
  fi
  CHAT_MODEL="${MODEL_SELECTION[0]}"
}

check_model_requirements() {
  local model size free_mb total_mb available_mb download_mb=0 required_mb
  local gemma4=0 warned=0 answer
  for model in "${MODEL_SELECTION[@]}"; do
    size="$(model_size_mb "$model")"
    download_mb=$((download_mb + size))
    if [ "$model" = "gemma4:e2b-it-qat" ]; then
      gemma4=1
    fi
  done
  download_mb=$((download_mb + EMBED_SIZE_MB))
  required_mb=$((download_mb + DISK_MARGIN_MB))
  free_mb="$(disk_free_mb)"
  total_mb="$(ram_total_mb)"
  available_mb="$(ram_available_mb)"

  printf '\nDownload size: %s for the selected models plus notes search\n' "$(human_size "$download_mb")"
  printf 'Disk needed: %s including a %s safety margin\n' \
    "$(human_size "$required_mb")" "$(human_size "$DISK_MARGIN_MB")"
  if [ "$free_mb" -gt 0 ]; then
    printf 'Disk available: %s\n' "$(human_size "$free_mb")"
    if [ "$free_mb" -lt "$required_mb" ]; then
      printf 'Warning: not enough free disk space; you are short by %s.\n' \
        "$(human_size "$((required_mb - free_mb))")" >&2
      warned=1
    fi
  else
    printf 'Warning: could not determine free disk space; check it manually.\n' >&2
    warned=1
  fi

  if [ "$gemma4" -eq 1 ]; then
    if [ "$available_mb" -gt 0 ] && [ "$available_mb" -lt 5120 ]; then
      printf 'Warning: Gemma 4 needs about 5 GB of free RAM; only %s is available.\n' \
        "$(human_size "$available_mb")" >&2
      warned=1
    fi
    if [ "$total_mb" -gt 0 ] && [ "$total_mb" -lt 8192 ]; then
      printf 'Warning: this computer has %s RAM; Gemma 4 is happiest with 8 GB or more.\n' \
        "$(human_size "$total_mb")" >&2
      warned=1
    fi
  fi

  if [ "$warned" -eq 1 ]; then
    if [ "$TTY_FD" -eq 3 ]; then
      printf 'Continue with the download anyway? [y/N]: ' >&3
      if ! IFS= read -r answer <&3; then
        answer=""
      fi
      case "$answer" in
        y|Y|yes|YES) ;;
        *) fail "Installation cancelled. No models were downloaded." ;;
      esac
    else
      printf 'Continuing because the model selection was provided non-interactively.\n'
    fi
  fi
}

install_models() {
  local model
  start_ollama
  for model in "${MODEL_SELECTION[@]}"; do
    info "Downloading chat model ($model)"
    ollama pull "$model"
  done
  info "Downloading the notes model ($EMBED_MODEL)"
  ollama pull "$EMBED_MODEL"
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
  local model models_json=""
  for model in "${MODEL_SELECTION[@]}"; do
    models_json="${models_json:+$models_json, }\"$model\""
  done
  cat > "$INSTALL_DIR/settings.json" <<SETTINGS_EOF
{
  "chat_model": "$CHAT_MODEL",
  "chat_models": [$models_json],
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
  install_code
  ensure_ollama
  choose_models
  if [ "$SKIP_MODELS" != "1" ]; then
    check_model_requirements
    install_models
  else
    info "Skipping model downloads because OS_SKIP_MODELS=1"
  fi
  ensure_desktop_toolkit
  install_python_packages
  write_settings
  install_cli
  write_start_script
  install_desktop
  remove_old_service
  stop_previous
  printf '\nInstalled in: %s\n' "$INSTALL_DIR"
  printf 'Chat model(s): %s\n' "${MODEL_SELECTION[*]}"
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
