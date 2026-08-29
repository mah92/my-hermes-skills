#!/usr/bin/env python3
"""Dual-track subtitles: Chinese (upper) + Persian (lower) SRT/ASS.
segments.json (zh) + fa_cues.json (fa) -> fa.srt, zh.srt, dual.ass
Two Dialogue events per cue (same times): style ZH (Noto Sans CJK SC) at
MarginV upper, style FA (Nazli) at MarginV lower. Zero overlap enforced.
ASS times MUST be H:MM:SS.CC (2-digit centis).
Usage: python make_dual_ass.py <ws> [width height]  (default 640 360)"""
import json, sys

WS = sys.argv[1]
W = int(sys.argv[2]) if len(sys.argv) > 2 else 640
H = int(sys.argv[3]) if len(sys.argv) > 3 else 360

segs = json.load(open(f"{WS}/segments.json", encoding="utf-8"))
fa = json.load(open(f"{WS}/fa_cues.json", encoding="utf-8"))

cues = []
for i, s in enumerate(segs):
    zh = s["text"].strip()
    fap = fa.get(str(i), "").strip()
    if not zh:
        continue
    st, en = s["start"], s["end"]
    if i + 1 < len(segs):
        en = min(en, segs[i + 1]["start"])      # zero overlap FIRST
    if en - st < 0.8:
        en = min(en, segs[i + 1]["start"] if i + 1 < len(segs) else st + 0.8,
                 st + 1.6)                      # extend but NEVER past next start
    if en - st < 0.5:
        continue                                # too short even after extension
    cues.append((st, en, zh, fap))

def ts(t):
    h = int(t // 3600); m = int(t % 3600 // 60); sec = t % 60
    return f"{h:02d}:{m:02d}:{sec:06.3f}".replace(".", ",")

def ts_ass(t):
    h = int(t // 3600); m = int(t % 3600 // 60); sec = int(t % 60)
    cs = int(round((t - int(t)) * 100)) % 100
    return f"{h:d}:{m:02d}:{sec:02d}.{cs:02d}"

# --- SRTs ---
with open(f"{WS}/zh.srt", "w", encoding="utf-8") as f:
    for i, (st, en, zh, _) in enumerate(cues, 1):
        f.write(f"{i}\n{ts(st)} --> {ts(en)}\n{zh}\n\n")
with open(f"{WS}/fa.srt", "w", encoding="utf-8") as f:
    for i, (st, en, _, fap) in enumerate(cues, 1):
        if fap:
            f.write(f"{i}\n{ts(st)} --> {ts(en)}\n{fap}\n\n")

# --- ASS (dual line: ZH above, FA below) ---
FS_ZH = max(16, int(round(H * 0.055)))    # ~20 @360p
FS_FA = int(round(H * 0.047))             # ~17 @360p
MV_ZH = int(round(H * 0.15))              # upper line  (~54 @360p)
MV_FA = int(round(H * 0.062))             # lower line  (~22 @360p)

with open(f"{WS}/dual.ass", "w", encoding="utf-8") as f:
    f.write(f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ZH,Noto Sans CJK SC,{FS_ZH},&H00FFFFFF,&H000000FF,&H00141414,&H64000000,1,0,0,0,100,100,0,0,1,1.5,0.6,2,20,20,{MV_ZH},1
Style: FA,Nazli,{FS_FA},&H00FFFFFF,&H000000FF,&H00141414,&H64000000,1,0,0,0,100,100,0,0,1,1.5,0.6,2,20,20,{MV_FA},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""")
    for st, en, zh, fap in cues:
        zh = zh.replace("\n", " ").strip(); fap = fap.replace("\n", " ").strip()
        f.write(f"Dialogue: 0,{ts_ass(st)},{ts_ass(en)},ZH,,0,0,0,,{zh}\n")
        if fap:
            f.write(f"Dialogue: 0,{ts_ass(st)},{ts_ass(en)},FA,,0,0,0,,{fap}\n")

print(f"wrote {WS}/zh.srt ({len(cues)}), fa.srt, dual.ass (ZH+FA)")
