"""Common egress allow-list presets.

Each preset name expands to a tuple of host patterns. Pool config can mix
presets with custom hosts. Unknown preset names are dropped silently — the
caller is responsible for surfacing them (so a typo doesn't open holes).
"""

from __future__ import annotations

from typing import Iterable

PRESETS: dict[str, tuple[str, ...]] = {
    "npm": (
        "registry.npmjs.org",
        "*.npmjs.org",
        "*.npmjs.com",
    ),
    "pypi": (
        "pypi.org",
        "files.pythonhosted.org",
        "*.pythonhosted.org",
    ),
    "crates": (
        "crates.io",
        "static.crates.io",
        "*.crates.io",
    ),
    "rubygems": (
        "rubygems.org",
        "*.rubygems.org",
    ),
    "gomod": (
        "proxy.golang.org",
        "sum.golang.org",
        "*.golang.org",
    ),
    "github": (
        "github.com",
        "api.github.com",
        "codeload.github.com",
        "*.githubusercontent.com",
    ),
    "gitlab": (
        "gitlab.com",
        "*.gitlab.com",
    ),
    "docker": (
        "registry-1.docker.io",
        "auth.docker.io",
        "*.docker.io",
    ),
    "ghcr": ("ghcr.io", "*.ghcr.io"),
    "ubuntu": (
        "archive.ubuntu.com",
        "security.ubuntu.com",
        "*.ubuntu.com",
    ),
    "debian": ("deb.debian.org", "*.debian.org"),
    "alpine": ("dl-cdn.alpinelinux.org", "*.alpinelinux.org"),
}


def expand_presets(
    names: Iterable[str], extra: Iterable[str] = ()
) -> tuple[str, ...]:
    """Resolve preset names + extras into a flat tuple of host patterns.

    Order is preserved; duplicates are removed.
    """
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        for pat in PRESETS.get(name, ()):
            if pat in seen:
                continue
            seen.add(pat)
            out.append(pat)
    for pat in extra:
        p = pat.strip()
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(p)
    return tuple(out)
