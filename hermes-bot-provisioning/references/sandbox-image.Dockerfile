# Optional per-profile sandbox image for `hermes-bot-provisioning`.
#
# A Hermes-FREE container the bot's *commands* run in (terminal/file/execute_code)
# while its gateway and agent stay on the host. Nothing host-specific is baked
# in: the mount points come from the bind mounts the backend passes at run time.
#
# Build (no BuildKit needed; run it in the background with NO timeout on a slow
# link):
#   docker build -t hermes-sandbox:1 <dir-with-this-Dockerfile>
# then provision with: add-bot.sh <name> ... --sandbox-image hermes-sandbox:1
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LANG=C.UTF-8

RUN apt-get update -o Acquire::Retries=5 \
    && apt-get install -y --no-install-recommends -o Acquire::Retries=5 \
        git curl wget ca-certificates \
        ffmpeg \
        ripgrep jq rsync unzip zip \
        poppler-utils sqlite3 procps \
    && rm -rf /var/lib/apt/lists/*

# uid/gid 1000 == the typical host user, so files written into bind mounts are
# owned by that account (the backend passes --user uid:gid when
# docker_run_as_host_user is true). NOTE: groupadd first — Debian's useradd -g
# <gid> fails without the group, and root-owned files must be written BEFORE
# USER is switched.
RUN groupadd -g 1000 sandbox \
    && useradd -u 1000 -g 1000 -m -s /bin/bash sandbox \
    && chown -R 1000:1000 /home/sandbox \
    && printf 'sandbox (no hermes inside)\n' > /etc/sandbox-release

ENV HOME=/home/sandbox
USER 1000:1000
WORKDIR /home/sandbox

# Keep it lean. Add a package only when a bot's skill actually needs it, and
# remember a runtime `pip install` inside the sandbox is lost with the session:
# bake it here instead.
