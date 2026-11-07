#!/usr/bin/env python3
"""Inventario conservador: no traducir un nombre inglés a ciegas para locutarlo."""
import ast
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/voices-latam"
BASE = ROOT / "tools/latam/work/pack-baseline/gcompris/data/voices-ogg/es"

MISC = {
    "welcome": "¡Hola! Bienvenida a GCompris. ¿A qué vamos a jugar hoy?",
    "about": "Acerca de GCompris", "awesome": "¡Increíble!", "by": "por",
    "check_answer": "Comprueba tu respuesta", "click_on_letter": "Toca la letra",
    "configuration": "Configuración", "congratulation": "¡Felicitaciones!",
    "equal": "igual", "fantastic": "¡Fantástico!", "good": "¡Bien!",
    "great": "¡Muy bien!", "help": "Ayuda", "level": "Nivel", "minus": "menos",
    "ok": "De acuerdo", "outof": "de", "perfect": "¡Perfecto!", "plus": "más",
    "quit": "Salir", "super": "¡Súper!", "waytogo": "¡Así se hace!",
}


def intros():
    entries = {}
    raw = (ROOT / "po/es/gcompris_voices.po").read_text()
    import re
    for block in raw.split("\n\n"):
        match = re.search(r'activity: "([^"]+)"', block)
        if not match or '#, fuzzy' in block:
            continue
        active = False
        text = ""
        for line in block.splitlines():
            if line.startswith("msgstr "):
                active = True
                text = ast.literal_eval(line[7:])
            elif active and line.startswith('"'):
                text += ast.literal_eval(line)
            elif active:
                break
        if text:
            entries[match[1] + ".ogg"] = text
    return entries


def main():
    words = json.loads((ROOT / "src/activities/lang/resource/content-es.json").read_text())
    legacy_path = ROOT / "tools/latam/work/content-es-V0.95.json"
    if not legacy_path.exists():
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(
            "https://raw.githubusercontent.com/KDE/gcompris/V0.95/src/activities/lang/resource/content-es.json",
            legacy_path)
    legacy = json.loads(legacy_path.read_text())
    extra = json.loads((DATA / "reviewed-extra.json").read_text())
    pilot = json.loads((DATA / "manifest.json").read_text())
    intro = intros()
    paths = {f.relative_to(BASE).as_posix() for f in BASE.rglob("*.ogg")}
    paths |= {c["path"] for c in pilot["clips"]}
    clips = []
    for path in sorted(paths):
        category, filename = path.split("/", 1)
        stem = Path(filename).stem
        text, source = "", ""
        if category == "misc" and stem in MISC:
            text, source = MISC[stem], "Adaptación latinoamericana del botón o feedback"
        elif category == "intro" and filename in intro:
            text, source = intro[filename], "po/es/gcompris_voices.po, V26.2"
        elif category in ("words", "colors", "alphabet") and filename in words:
            text, source = words[filename], "src/activities/lang/resource/content-es.json, V26.2"
        elif category == "words" and filename in legacy:
            text, source = legacy[filename], "src/activities/lang/resource/content-es.json, V0.95"
        if category == "colors" and stem in ("purple", "grey"):
            text, source = {"purple": "morado", "grey": "gris"}[stem], "Nombre del color"
        if stem in extra.get(category, {}):
            text, source = extra[category][stem], "data/voices-latam/reviewed-extra.json"
        status = "ready" if text else "needs_transcript"
        clips.append({"path": path, "text": text, "source": source,
                      "status": status, "voice": "jessica"})
    order = {"misc": 0, "intro": 1, "colors": 2, "alphabet": 3, "words": 4, "geography": 5}
    clips.sort(key=lambda c: (c["path"] != "misc/welcome.ogg", order[c["path"].split('/')[0]], c["path"]))
    result = {"language": "es-419", "voice_id": "cgSgspJ2msm6clMCkdW9",
              "model": "eleven_multilingual_v2", "clips": clips}
    target = DATA / "catalog-elevenlabs.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    ready = [c for c in clips if c["status"] == "ready"]
    print("Total:", len(clips), "listos:", len(ready), "pendientes:", len(clips) - len(ready))
    print("Caracteres listos:", sum(len(c["text"]) for c in ready))


if __name__ == "__main__":
    main()
