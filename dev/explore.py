"""Explore the RSC chunks to find where the model array lives."""
import json
import re
from pathlib import Path

html = Path("artifacts/models.html").read_text(encoding="utf-8")
print(f"HTML size: {len(html):,} chars")

# Find all self.__next_f.push([N, "..."]) chunk strings.
# The string is a JS double-quoted literal with \" \\ \n etc. escapes.
chunks: list[tuple[int, str]] = []
pattern = re.compile(r'self\.__next_f\.push\(\[(\d+),\s*"((?:[^"\\]|\\.)*)"\]\)', re.DOTALL)
for m in pattern.finditer(html):
    kind = int(m.group(1))
    raw = m.group(2)
    # Decode JS string escapes. JSON loader handles \" \\ \n \t \uXXXX correctly.
    decoded = json.loads('"' + raw + '"')
    chunks.append((kind, decoded))

print(f"Found {len(chunks)} __next_f.push chunks")
kinds = {}
for k, _ in chunks:
    kinds[k] = kinds.get(k, 0) + 1
print(f"Chunk kinds: {kinds}")

# Concatenate all kind=1 chunks — these form the RSC payload stream.
rsc_stream = "".join(s for k, s in chunks if k == 1)
print(f"RSC stream size: {len(rsc_stream):,} chars")

# The stream is a sequence of lines like '<hexId>:<jsondata>\n'.
# Split on newlines and find the line containing the model array.
lines = rsc_stream.split("\n")
print(f"Stream has {len(lines)} lines")

best = None
for i, line in enumerate(lines):
    if '"intelligence_index"' in line:
        if best is None or len(line) > len(lines[best]):
            best = i

print(f"Longest line containing intelligence_index: idx={best}, len={len(lines[best]):,}")
prefix_match = re.match(r"^([0-9a-f]+):", lines[best])
print(f"  Prefix: {prefix_match.group(1) if prefix_match else '(none)'}")
print(f"  First 200 chars after prefix: {lines[best][:200]!r}")
