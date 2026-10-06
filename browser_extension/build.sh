#!/usr/bin/env bash
# Re-package the extension into the app's public assets so it can be downloaded from the site.
set -e
cd "$(dirname "$0")"
OUT="../accounting_firms/public/extension/accounting-firms-auto-login.zip"
mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"
zip -qr "$OUT" . -x "build.sh" "*.DS_Store" 2>/dev/null || python3 - "$OUT" <<'PY'
import sys, zipfile, os
out = sys.argv[1]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for root, _, files in os.walk("."):
        for f in files:
            if f == "build.sh": continue
            p = os.path.join(root, f); z.write(p, os.path.relpath(p, "."))
PY
echo "built $OUT"
