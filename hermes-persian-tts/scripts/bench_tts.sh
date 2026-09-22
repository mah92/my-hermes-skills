#!/usr/bin/env bash
# Memory/latency benchmark for MatchaTTSInfer daemon.
# Usage: bench_tts.sh <label>
# Tests: short text, medium (~1800 chars), long (~11k chars -> auto-split), repetition.
# Records per-step daemon RSS (VmRSS) and wall time into /tmp/tts_bench_<label>.txt
LABEL=${1:-run}
OUT=/tmp/tts_bench_${LABEL}.txt
SOCK=/tmp/tts_infer.sock
SCRIPT=/home/oem/.agents/skills/hermes-persian-tts/scripts/tts.py
echo "== bench $LABEL $(date +%T) ==" >> "$OUT"

daemon_rss() {
  local pid=$(pgrep -x MatchaTTSInfer | head -1)
  [ -n "$pid" ] && awk '/VmRSS/{print $2}' /proc/$pid/status || echo 0
}

kill_daemon() { pkill -x MatchaTTSInfer; sleep 1; rm -f "$SOCK"; }

start_daemon() {
  # Daemon must run from NormalizeText/ so ./assets/ resolves (ezafe_spiece.model).
  NORMDIR=/home/oem/Basir/TTS/match_tts_infer/NormalizeText
  ( cd "$NORMDIR" && nohup /home/oem/Basir/TTS/match_tts_infer/build/MatchaTTSInfer --daemon \
    --matcha-model /home/oem/.hermes/skills/hermes-persian-tts/models/matcha-fa_en-zahra-22050-5.onnx \
    --vocoder-model /home/oem/.hermes/skills/hermes-persian-tts/models/vocos22.onnx \
    --tokens /home/oem/.hermes/skills/hermes-persian-tts/models/tokens_sherpa_with_fa.txt \
    --espeak-data /home/oem/Basir/TTS/Piper/piper_linux_x86_64/piper/espeak-ng-data \
    > /tmp/tts_daemon_${LABEL}.log 2>&1 ) &
  local dpid=$!
  echo "daemon_pid=$dpid cwd=$NORMDIR" >> "$OUT"
  for i in $(seq 1 100); do [ -S "$SOCK" ] && break; sleep 0.1; done
}

run_case() {
  local name=$1 txt=$2
  echo "$txt" > /tmp/bench_in.txt
  local t0=$(date +%s.%N)
  python3 "$SCRIPT" /tmp/bench_in.txt /tmp/bench_out.ogg >/dev/null 2>&1
  local rc=$?
  local t1=$(date +%s.%N)
  printf "%-12s rc=%s  wall=%.1fs  rss_after=%s kB\n" "$name" "$rc" \
    "$(echo "$t1 - $t0" | bc)" "$(daemon_rss)" >> "$OUT"
}

# --- cases ---
kill_daemon
start_daemon
echo "rss_after_load=$(daemon_rss) kB" >> "$OUT"

run_case short "سلام، این یک آزمایش است."
run_case med "$(python3 -c "print('علی به بازار رفت و میوه خرید. زینب کتاب خواند، حسین بازی کرد! ' * 29)")"
run_case long "$(python3 -c "print(('مسافر در جاده خاکستری قدم میزد و آواز میخواند. ' * 220))")"
run_case rep1 "$(python3 -c "print('سلام ' * 50)")"
run_case rep2 "$(python3 -c "print('سلام ' * 50)")"
run_case rep3 "$(python3 -c "print('سلام ' * 50)")"

echo "rss_final=$(daemon_rss) kB" >> "$OUT"
echo "== end $LABEL ==" >> "$OUT"
