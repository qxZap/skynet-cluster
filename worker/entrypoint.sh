#!/bin/sh
# Write a minimal opencode auth.json from the single token we were given.
# ponytail: one provider, written at boot — no host config baked into the image.
set -e
mkdir -p "$HOME/.local/share/opencode"
cat > "$HOME/.local/share/opencode/auth.json" <<EOF
{"minimax-coding-plan":{"type":"api","key":"${MINIMAX_API_KEY}"}}
EOF
exec python3 runtime.py
