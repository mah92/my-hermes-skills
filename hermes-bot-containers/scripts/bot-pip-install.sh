#!/bin/bash
# bot-pip-install.sh <bot> <package> — have a bot install a package into its
# own in-container hermes venv (/opt/hermes/.venv) by ASKING THE BOT through
# its CLI. This is the ONLY reliable method: the bot hits the same security
# gates itself and remembers the working path in its session (a host-side
# `docker exec pip install` teaches the bot nothing and often breaks the
# container's security posture). Verified 2026-08-30 on all three live bots.
#
# Usage:  bash bot-pip-install.sh <bot-name> <package> [extra-pip-pins]
#   <bot-name>      : profile/container name, e.g. marziye
#   <package>       : package to install, e.g. humanize
#   [extra-pip-pins]: optional, passed in the prompt as constraints,
#                     e.g. "websockets==15.0.1" (keep quoted)
#
# The prompt covers every live pitfall: root-owned venv + sudo -n, NEVER
# --break-system-packages, python -c blocked -> script file in the WORKSPACE
# (not /tmp), Tirith threat-intel timeouts blocking bare `pip install`, and
# the accepted workarounds (python -m pip, or wheel download + --no-index /
# direct unzip for pure-py no-dep packages), plus a host-side verification
# afterwards that does not trust the bot's self-report.
set -euo pipefail

NAME="${1:?usage: bot-pip-install.sh <bot> <package> [pip-pins...]}"
PKG="${2:?usage: bot-pip-install.sh <bot> <package> [pip-pins...]}"
PINS="${3:-}"
H="${HOME:-/home/oem}"
WS="$H/workspaces/$NAME"
CONTAINER="hermes-$NAME"
PY="/opt/hermes/.venv/bin/python"
HERMES_BIN="/opt/hermes/.venv/bin/hermes"

# container must exist and the bot venv python must be the baked one
docker inspect "$CONTAINER" >/dev/null 2>&1 || { echo "ERROR: no container $CONTAINER" >&2; exit 1; }
docker exec -u hermes "$CONTAINER" bash -lc "test -x $PY" >/dev/null 2>&1 \
  || { echo "ERROR: $PY not found in $CONTAINER (not a baked image?)" >&2; exit 1; }

PROMPT=$(cat <<PROMPT_EOF
لطفاً پکیج پایتونی «$PKG»${PINS:+ (با قید ${PINS})} را در venv هرمس خودت نصب کن. نکات الزامی:
1) مسیر نصب: /opt/hermes/.venv (venv هرمس داخل تصویر). این پوشه root-owned است و تصویر تو sudo دارد؛ پس با sudo -n نصب کن (اول sudo -n true را تست کن که بدون پسورد کار می‌کند). هرگز از --break-system-packages استفاده نکن.
2) اجرای inline پایتون (python -c) معمولاً توسط اسکنر امنیتی بلاک می‌شود؛ از فایل اسکریپت استفاده کن و آن را در workspace خودت بنویس (HERMES_WRITE_SAFE_ROOT)، نه در /tmp.
3) دستور form دار pip (مثلاً python -m pip install) را اول امتحان کن؛ اگر بلاک شد (Tirith به‌خاطر timeout سرویس‌های threat-intel)، ویل را از PyPI دانلود کن و با pip install --no-index نصب کن؛ برای پکیج‌های pure-py بدون وابستگی می‌توانی ویل را مستقیماً در /opt/hermes/.venv/lib/python3.13/site-packages/ استخراج کنی.
4) حواست باشد نام فایل ویل کامل باشد (مثلاً $PKG-<version>-py3-none-any.whl) وگرنه pip آن را رد می‌کند.
5) آخرین نسخه را نصب کن (نسخه‌های قدیمی ممکن است روی پایتون 3.13 بشکنند).
6) بعد از نصب، تست واقعی بده: import پکیج را با فایل اسکریپت اجرا کن و نسخه دقیق نصب‌شده و خروجی تست را گزارش بده.
PROMPT_EOF
)

echo "==> asking $CONTAINER to install $PKG${PINS:+ ($PINS)} into its hermes venv..."
docker exec -u hermes "$CONTAINER" bash -lc "cd $WS && $HERMES_BIN chat -q \"\$1\" --source cli-install" -- "$PROMPT" 2>&1 | tail -30
RC=${PIPESTATUS[0]}

echo
echo "==> host-side verification (independent of the bot's report):"
docker exec -u hermes "$CONTAINER" bash -lc "$PY -c 'import importlib.metadata as md; import $PKG; v = getattr($PKG, \"__version__\", md.version(\"$PKG\")); print(\"OK\", v)'" \
  && echo "VERIFIED: $PKG importable from $PY in $CONTAINER" \
  || { echo "VERIFICATION FAILED" >&2; exit 1; }

echo "DONE. $PKG installed into $CONTAINER's hermes venv by the bot itself."
exit "$RC"
