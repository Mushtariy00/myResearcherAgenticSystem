#!/usr/bin/env bash
# One-time developer setup for WSL2 Ubuntu 24.04 (run it yourself; it asks for your sudo password).
# Installs: Docker Engine + Compose, NVIDIA Container Toolkit (>= 1.20.1), uv, Node 24 (fnm), pnpm.
# Do NOT install an NVIDIA Linux driver inside WSL: the Windows driver provides the GPU.
set -euo pipefail

PNPM_VERSION="12.16.1"
MIN_NVIDIA_CTK="1.20.1"

step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }

. /etc/os-release
[[ "${VERSION_ID:-}" == "24.04" ]] || echo "Warning: tested on Ubuntu 24.04, found ${PRETTY_NAME:-unknown}"
[[ "$(ps -p 1 -o comm=)" == "systemd" ]] || { echo "systemd is not PID 1. Add [boot] systemd=true to /etc/wsl.conf, then run 'wsl --shutdown' in Windows."; exit 1; }

step "Base packages"
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg unzip make

step "Docker Engine (official apt repository)"
if ! command -v docker >/dev/null; then
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
# Dev convenience: the docker group is root-equivalent. Production uses a dedicated host (docs/PLAN.md).
sudo usermod -aG docker "$USER"

step "NVIDIA Container Toolkit (>= $MIN_NVIDIA_CTK)"
if [[ ! -f /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg ]]; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null
  sudo apt-get update
fi
sudo apt-get install -y nvidia-container-toolkit
installed="$(nvidia-ctk --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
if [[ "$(printf '%s\n%s\n' "$MIN_NVIDIA_CTK" "$installed" | sort -V | head -1)" != "$MIN_NVIDIA_CTK" ]]; then
  echo "nvidia-container-toolkit $installed is older than $MIN_NVIDIA_CTK (container-escape CVEs). Upgrade before continuing."
  exit 1
fi
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

step "uv (Python toolchain)"
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
elif [[ "$(printf '%s\n%s\n' 0.13 "$(uv --version | grep -oE '[0-9]+\.[0-9]+' | head -1)" | sort -V | head -1)" != "0.13" ]]; then
  uv self update  # an older standalone uv is already installed
fi

step "Node 24 LTS (fnm) and pnpm $PNPM_VERSION"
if ! command -v fnm >/dev/null && [[ ! -x "$HOME/.local/share/fnm/fnm" ]]; then
  curl -fsSL https://fnm.vercel.app/install | bash -s -- --skip-shell
fi
export PATH="$HOME/.local/share/fnm:$PATH"
eval "$(fnm env --shell bash)"
fnm install 24
fnm default 24
grep -q 'fnm env' "$HOME/.bashrc" || echo 'eval "$(fnm env --use-on-cd --shell bash)"' >> "$HOME/.bashrc"
grep -q 'share/fnm' "$HOME/.bashrc" || sed -i '1i export PATH="$HOME/.local/share/fnm:$PATH"' "$HOME/.bashrc"
npm install -g "pnpm@$PNPM_VERSION"

cat <<'EOF'

Done. Next:
  1. Close this terminal and open a new one (picks up the docker group, uv, node and pnpm).
  2. Optional, recommended: give WSL more memory. In Windows, create %UserProfile%\.wslconfig with
         [wsl2]
         memory=10GB
     then run `wsl --shutdown` in PowerShell and reopen Ubuntu.
  3. In the repo:  make doctor  →  make setup  →  make up  →  make sandbox-smoke
EOF
