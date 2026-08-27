# Derived Hermes image with passwordless sudo for the in-container hermes user.
# Base is pinned by digest so every rebuild is byte-identical.
#
# Why sudo is safe here: no docker socket, host mounts are read-only, default
# Docker seccomp/capabilities apply, PID namespace is isolated -> container-root
# cannot touch the host. Residual: with network_mode=host, container-root holds
# NET_RAW (raw sockets on the host LAN) — accepted for the trusted family setup.
#
# Rebuild: docker build -t nousresearch/hermes-agent-sudo:<TAG> <dir-with-Dockerfile>
# (the live copy lives at /home/oem/profiles-containers/sudo-image/Dockerfile)
FROM nousresearch/hermes-agent@sha256:44733d69163211c82c3c6f7ab0ba4bb82e6995870014fc0308b6863fb2246b50

# hermes user may sudo without a password; keep the rest of sudoers intact.
RUN apt-get update \
 && apt-get install -y --no-install-recommends sudo \
 && rm -rf /var/lib/apt/lists/* \
 && printf 'hermes ALL=(ALL) NOPASSWD: ALL\n' > /etc/sudoers.d/hermes \
 && chmod 440 /etc/sudoers.d/hermes
