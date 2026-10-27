#!/usr/bin/env python3
"""Собирает урезанные geosite.dat / geoip.dat из релиза runetfreedom/russia-v2ray-rules-dat.

Оставляет только нужные теги. Результат кладёт в $GEO_WORK/out атомарно (tmp + replace).
"""
import hashlib
import os
import sys
import urllib.request

BASE = "https://github.com/runetfreedom/russia-v2ray-rules-dat/releases/latest/download/"
WORK = os.environ.get("GEO_WORK", "/root/geo-slim")
SRC = os.path.join(WORK, "src")
OUT = os.path.join(WORK, "out")
KEEP = {
    "geosite.dat": {"RU-BLOCKED"},
    "geoip.dat": {"RU-BLOCKED", "RU"},
}


def fetch(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "geo-slim/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)


def varint_read(b, i):
    r = s = 0
    while True:
        x = b[i]
        i += 1
        r |= (x & 0x7F) << s
        if not x & 0x80:
            return r, i
        s += 7


def varint_write(n):
    out = bytearray()
    while True:
        x = n & 0x7F
        n >>= 7
        if n:
            out.append(x | 0x80)
        else:
            out.append(x)
            return bytes(out)


def entry_code(ent):
    """Код страны/тега: поле 1 внутри записи."""
    j = 0
    while j < len(ent):
        t, j = varint_read(ent, j)
        wt, fn = t & 7, t >> 3
        if wt == 2:
            ln, j = varint_read(ent, j)
            if fn == 1:
                return ent[j:j + ln].decode(errors="replace")
            j += ln
        elif wt == 0:
            _, j = varint_read(ent, j)
        else:
            break
    return None


def slim(src, dst, keep):
    data = open(src, "rb").read()
    i = 0
    kept = []
    while i < len(data):
        tag, i = varint_read(data, i)
        if tag != 0x0A:
            sys.exit("неожиданный формат файла " + src)
        ln, i = varint_read(data, i)
        ent = data[i:i + ln]
        i += ln
        code = entry_code(ent)
        if code and code.upper() in keep:
            kept.append((code, ent))
    found = {c.upper() for c, _ in kept}
    if found != keep:
        sys.exit("в %s не нашлись теги: %s" % (src, sorted(keep - found)))
    tmp = dst + ".tmp"
    with open(tmp, "wb") as f:
        for _, ent in kept:
            f.write(b"\x0a" + varint_write(len(ent)) + ent)
    os.replace(tmp, dst)
    return [(c, len(e)) for c, e in kept]


def main():
    os.makedirs(SRC, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    for name, keep in KEEP.items():
        p = os.path.join(SRC, name)
        fetch(BASE + name, p)
        fetch(BASE + name + ".sha256sum", p + ".sha256sum")
        want = open(p + ".sha256sum").read().split()[0].lower()
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != want:
            sys.exit("контрольная сумма %s не совпала" % name)
        res = slim(p, os.path.join(OUT, name), keep)
        print("%s: исходник %d КБ -> %d КБ, теги: %s" % (
            name, os.path.getsize(p) // 1024,
            os.path.getsize(os.path.join(OUT, name)) // 1024,
            ", ".join("%s(%d КБ)" % (c, n // 1024) for c, n in res)))
        os.remove(p)  # исходник 70 МБ держать незачем
        os.remove(p + ".sha256sum")


if __name__ == "__main__":
    main()
