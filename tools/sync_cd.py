"""Holt die Web-Bausteine des KP-CD unverändert in die App.

Das CD-Repository (kp-corporate-design) ist die einzige Quelle. Die Dateien hier sind
Kopien seiner Build-Ergebnisse und werden nie von Hand geändert. Nach einer Änderung
am CD dort bauen und dann hier ausführen:

    python3 tools/sync_cd.py                       # erwartet ../kp-corporate-design
    python3 tools/sync_cd.py --source /pfad/zum/cd

Der übernommene Stand (Git-Commit des CD) steht danach in ``static/kp/CD-VERSION``.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "src" / "judicataurus_rex" / "web" / "static" / "kp"

# Quelle (relativ zum CD-Repository) → Ziel (relativ zu static/kp). Die Ordnerstruktur
# css/ fonts/ img/ bleibt erhalten, weil kp-fonts.css auf ../fonts/ verweist.
FILES: dict[str, str] = {
    "website/css/kp-tokens.css": "css/kp-tokens.css",
    "website/css/kp-fonts.css": "css/kp-fonts.css",
    "website/js/kp-theme.js": "js/kp-theme.js",
    "website/img/kp-pattern-light.svg": "img/kp-pattern-light.svg",
    "website/img/kp-pattern-dark.svg": "img/kp-pattern-dark.svg",
    "website/favicon.svg": "img/favicon.svg",
    "website/favicon.ico": "img/favicon.ico",
    "website/apple-touch-icon.png": "img/apple-touch-icon.png",
    "website/lizenzen/ibm-plex-sans-serif-mono.txt": "licenses/ibm-plex-sans-serif-mono.txt",
    "website/lizenzen/tabler-icons.txt": "licenses/tabler-icons.txt",
}
FONTS_DIR = "website/fonts"


def _commit(source: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(source), "describe", "--tags", "--always", "--dirty"],
            check=True,
            capture_output=True,
            text=True,
        )
    except OSError, subprocess.CalledProcessError:
        return "unbekannt"
    return result.stdout.strip()


def sync(source: Path) -> list[str]:
    missing = [name for name in FILES if not (source / name).is_file()]
    if missing or not (source / FONTS_DIR).is_dir():
        raise FileNotFoundError(
            f"Im CD unter {source} fehlen: {', '.join(missing) or FONTS_DIR}. "
            "Ist das CD gebaut (tools/kpcd build)?"
        )
    copied: list[str] = []
    for name, target in FILES.items():
        destination = TARGET / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, destination)
        copied.append(target)
    fonts = TARGET / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    for font in sorted((source / FONTS_DIR).glob("*.woff2")):
        shutil.copy2(font, fonts / font.name)
        copied.append(f"fonts/{font.name}")
    (TARGET / "CD-VERSION").write_text(f"{_commit(source)}\n", encoding="utf-8")
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description="Holt die Web-Bausteine des KP-CD in die App.")
    parser.add_argument("--source", type=Path, default=ROOT.parent / "kp-corporate-design")
    args = parser.parse_args()
    source: Path = args.source.resolve()
    try:
        copied = sync(source)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"{len(copied)} Dateien aus {source} nach {TARGET.relative_to(ROOT)} übernommen.")
    print(f"CD-Stand: {(TARGET / 'CD-VERSION').read_text(encoding='utf-8').strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
