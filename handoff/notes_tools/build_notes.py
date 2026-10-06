"""docs/BUILD_NOTES.md after the fifth check, built from the notes of commit c8c8448 (the last whole version), the logs
of the tools and the hand-written texts beside this script.

    python handoff/notes_tools/build_notes.py EARTH_LOGS VALUES.json > docs/BUILD_NOTES.md

Sections 4 (head), 4.2 to 4.5, 5.4 and 11 are written anew. In the other sections single statements are replaced, each
by an exact match of the old words, so that a statement that is not found stops the build."""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sec4            # noqa: E402
import sec4_text       # noqa: E402
import sec5_text       # noqa: E402
import other_text      # noqa: E402
import sec49_text      # noqa: E402

ROOT = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
OLD = subprocess.check_output(["git", "show", "c8c8448:docs/BUILD_NOTES.md"], text=True, cwd=ROOT)


def cut(text, start, end=None):
    i = text.index("\n" + start) + 1
    j = len(text) if end is None else text.index("\n" + end, i) + 1
    return text[i:j]


def main(logs, values):
    x = json.loads(Path(values).read_text(encoding="utf-8"))
    d = sec4.read(logs)
    o = sec4.sec44_tables(d)
    parts = [other_text.head(x), other_text.sec1(x, o)]
    s2 = cut(OLD, "## 2. Step 0", "## 3. Step 1")
    s3 = cut(OLD, "## 3. Step 1", "## 4. Step 2")
    s41 = cut(OLD, "### 4.1 What was built", "### 4.2 The design's")
    s46 = cut(OLD, "### 4.6 The Earth twin", "### 4.7 Run times")
    s48 = cut(OLD, "### 4.8 What step 2 changed", "## 5. Rounds of checking")
    s5 = cut(OLD, "## 5. Rounds of checking", "### 5.4 What the fifth check")
    s6 = cut(OLD, "## 6. What is not done", "## 7. Departures")
    s7 = cut(OLD, "## 7. Departures", "## 8. What the world looks like")
    s8 = cut(OLD, "## 8. What the world looks like", "## 9. What a replacement")
    s9 = cut(OLD, "## 9. What a replacement", "## 10. Sources")
    s10 = cut(OLD, "## 10. Sources", "## 11. Next")
    for name, text in (("2", s2), ("3", s3), ("4.1", s41), ("4.6", s46), ("4.8", s48), ("5", s5), ("6", s6), ("7", s7), ("8", s8), ("9", s9), ("10", s10)):
        for old, new in other_text.REPLACE[name](x, o, d):
            assert text.count(old) == 1, (name, text.count(old), old[:90])
            text = text.replace(old, new)
        if name == "4.1":
            parts += [sec4_text.head(d, o)]
        parts.append(text)
        if name == "4.1":
            parts += [sec4.sec42(d) + "\n", sec4_text.sec43(d, o, x["biomes"]) + "\n", sec4_text.sec44(d, o) + "\n", sec4_text.sec45(d, o) + "\n"]
        if name == "4.6":
            parts.append(other_text.sec47(x) + "\n")
        if name == "4.8":
            parts.append(sec49_text.SEC49 + "\n")
        if name == "5":
            parts.append(sec5_text.sec54(x["fifth"]) + "\n" + sec5_text.sec55(x) + "\n")
    parts.append(other_text.sec11(x, o))
    out = "".join(parts)
    assert "⟦" not in out, out[out.index("⟦") - 80:out.index("⟦") + 80]
    sys.stdout.write(out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
