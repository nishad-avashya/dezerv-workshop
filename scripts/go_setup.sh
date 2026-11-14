#!/usr/bin/env bash
# go_setup.sh: make sure a Go toolchain exists (spike V-11). Order: already installed, Homebrew, official tarball (checksum-verified),
# otherwise tell the user to use the prebuilt binaries (`make go-prebuilt`). The tarball path is UNTESTED on a Workshop Studio editor.
set -euo pipefail
if command -v go >/dev/null 2>&1; then go version; exit 0; fi
if command -v brew >/dev/null 2>&1; then brew install go && go version && exit 0; fi
os=$(uname -s | tr A-Z a-z); arch=$(uname -m); [ "$arch" = x86_64 ] && arch=amd64; [ "$arch" = aarch64 ] && arch=arm64
dl="$HOME/.local/go-dl"; mkdir -p "$dl"; cd "$dl"      # downloads go in their own directory
json=$(curl -fsSL "https://go.dev/dl/?mode=json") || { echo "no internet access: use the prebuilt binaries: make go-prebuilt"; exit 1; }
read -r file sha < <(printf '%s' "$json" | python3 -c "
import json,sys
for rel in json.load(sys.stdin):
    for f in rel['files']:
        if f['os']=='$os' and f['arch']=='$arch' and f['kind']=='archive':
            print(f['filename'], f['sha256']); raise SystemExit
")
curl -fsSLO "https://go.dev/dl/$file"
if command -v sha256sum >/dev/null 2>&1; then check="sha256sum -c -"; else check="shasum -a 256 -c -"; fi   # Linux has sha256sum, macOS shasum
echo "$sha  $file" | $check >/dev/null || { echo "checksum mismatch, refusing to install"; exit 1; }
mkdir -p "$HOME/.local" && rm -rf "$HOME/.local/go" && tar -C "$HOME/.local" -xzf "$file"
echo "installed to $HOME/.local/go: add  export PATH=\$HOME/.local/go/bin:\$PATH  to your shell"
"$HOME/.local/go/bin/go" version
