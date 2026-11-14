#!/usr/bin/env bash
# bootstrap.sh: install what the labs need BEFORE you can run `make` (make itself is not on the Workshop Studio editor).
# Idempotent: re-running does nothing if everything is already there. Installs make, curl and uv; checks python3, git, go.
# It does NOT touch AWS. Next steps after this:  export EXPECT_ACCOUNT=<id>  &&  make preflight  &&  make bootstrap
#
#   bash bootstrap.sh
set -euo pipefail

say()  { printf '[bootstrap.sh] %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  if have sudo && sudo -n true 2>/dev/null; then SUDO="sudo"; else SUDO=""; fi
fi

# ---- 1. make, curl (system packages) -------------------------------------------------------------------------------
need=()
for t in make curl; do have "$t" || need+=("$t"); done
if [ "${#need[@]}" -gt 0 ]; then
  say "missing: ${need[*]}"
  if [ "$(id -u)" -ne 0 ] && [ -z "$SUDO" ]; then
    say "no root and no passwordless sudo: cannot install ${need[*]}. Ask the instructor, or install them another way."; exit 1
  fi
  if   have dnf;     then $SUDO dnf install -y "${need[@]}"
  elif have yum;     then $SUDO yum install -y "${need[@]}"
  elif have apt-get; then $SUDO apt-get update -y && $SUDO apt-get install -y "${need[@]}"
  elif have brew;    then brew install "${need[@]}"
  else say "no supported package manager (dnf, yum, apt-get, brew) found: install ${need[*]} by hand"; exit 1
  fi
fi

# ---- 2. uv (every make target runs through it) ----------------------------------------------------------------------
export PATH="$HOME/.local/bin:$PATH"
if ! have uv; then
  say "installing uv"
  if have python3 && python3 -m pip --version >/dev/null 2>&1 && python3 -m pip install --user --quiet uv 2>/dev/null; then :
  else curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
fi
export PATH="$HOME/.local/bin:$PATH"
# make ~/.local/bin permanent for new shells (uv and Go prebuilts live there)
if [ -f "$HOME/.bashrc" ] && ! grep -q 'HOME/.local/bin' "$HOME/.bashrc"; then
  printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$HOME/.bashrc"
  say "added ~/.local/bin to PATH in ~/.bashrc (open a new shell, or: export PATH=\$HOME/.local/bin:\$PATH)"
fi

# ---- 3. report ------------------------------------------------------------------------------------------------------------
fail=0
for t in make curl uv python3 git; do
  if have "$t"; then say "ok      $t -> $(command -v "$t")"; else say "MISSING $t"; fail=1; fi
done
if have go; then say "ok      go -> $(command -v go)"; else say "note    go not installed: only Lab B Parts 2-3 need it (make go-setup, or make go-prebuilt)"; fi
[ "$fail" -eq 0 ] || { say "something above is still missing"; exit 1; }

cat <<'EOF'

Ready. Next:
  export EXPECT_ACCOUNT=<12-digit account id>
  make preflight
  make bootstrap && make verify-bootstrap
EOF
