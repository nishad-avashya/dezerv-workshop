#!/usr/bin/env bash
# go_prebuild.sh           (maintainers) build prebuilt/: the Go Lambda (linux/arm64 zip) and the forwarder (linux amd64+arm64, darwin arm64)
# go_prebuild.sh --install (attendees without Go) put the forwarder matching this machine at bin/alert-forwarder
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "${1:-}" = "--install" ]; then
  arch=$(uname -m); [ "$arch" = x86_64 ] && arch=amd64; [ "$arch" = aarch64 ] && arch=arm64
  os=$(uname -s | tr 'A-Z' 'a-z'); mkdir -p bin
  gunzip -c "prebuilt/alert-forwarder-$os-$arch.gz" > bin/alert-forwarder && chmod +x bin/alert-forwarder
  echo "installed bin/alert-forwarder ($os/$arch). Run: RUNTIME_ARN=... ./bin/alert-forwarder -addr :8080"
  exit 0
fi
mkdir -p prebuilt
tmp=$(mktemp -d)
# -trimpath keeps the builder's home directory and username out of the committed binaries
( cd tools/mandates-go && GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build -trimpath -ldflags "-s -w" -tags lambda.norpc -o "$tmp/bootstrap" . )
python3 - "$tmp/bootstrap" <<'PY'
import sys, zipfile
z = zipfile.ZipFile("prebuilt/mandates-go-arm64.zip", "w", zipfile.ZIP_DEFLATED)   # "w" overwrites an old zip
zi = zipfile.ZipInfo("bootstrap"); zi.external_attr = 0o755 << 16
z.writestr(zi, open(sys.argv[1], "rb").read(), zipfile.ZIP_DEFLATED); z.close()
PY
for t in linux/amd64 linux/arm64 darwin/arm64; do
  os=${t%/*}; arch=${t#*/}
  ( cd go/alert-forwarder && GOOS=$os GOARCH=$arch CGO_ENABLED=0 go build -trimpath -ldflags "-s -w" -o "$tmp/af-$os-$arch" . )
  gzip -9 -c "$tmp/af-$os-$arch" > "prebuilt/alert-forwarder-$os-$arch.gz"
done
ls -la prebuilt
