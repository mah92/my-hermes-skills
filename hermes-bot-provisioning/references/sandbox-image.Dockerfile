# Optional per-profile sandbox image for `hermes-bot-provisioning`.
#
# A Hermes-FREE container the bot's *commands* run in (terminal/file/execute_code)
# while its gateway and agent stay on the host. Nothing host-specific is baked in
# besides the uid/gid, which you pass as build args:
#
#   docker build -t hermes-sandbox:1 \
#       --build-arg UID=$(id -u) --build-arg GID=$(id -g) <dir-with-this-file>
#
# then provision with: add-bot.sh <name> ... --sandbox-image hermes-sandbox:1
#
# Why the uid/gid matters: with docker_run_as_host_user the backend runs the
# container as the HOST uid:gid, so the image must have that same numeric user or
# HOME is not writable and files in bind mounts come back with an unexpected
# owner. The default 1000 matches most single-user Linux boxes.
FROM python:3.11-slim

ARG UID=1000
ARG GID=1000

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

# groupadd must come first: Debian's useradd -g <gid> fails without the group, and
# anything root-owned must be written BEFORE USER is switched.
RUN groupadd -g "$GID" sandbox \
    && useradd -u "$UID" -g "$GID" -m -s /bin/bash sandbox \
    && chown -R "$UID:$GID" /home/sandbox \
    && printf 'sandbox (no hermes inside)\n' > /etc/sandbox-release

ENV HOME=/home/sandbox
USER $UID:$GID
WORKDIR /home/sandbox

# Keep it lean. Add a package only when a bot's skill actually needs it, and
# remember that a runtime `pip install` inside the sandbox is lost with the
# session: bake it here instead.
