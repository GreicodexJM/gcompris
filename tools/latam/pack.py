#!/usr/bin/env python3
"""Construye un paquete español conservando todo salvo los clips del manifiesto.

Dependencias: Python 3, compilador C++, Qt6Core, pkg-config y rcc (Qt 6).
No instala nada ni cambia el contenido de la tableta.
"""
import hashlib
import json
import pathlib
import shutil
import subprocess
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools/latam"
DATA = ROOT / "data/voices-latam"
WORK = TOOLS / "work"
BUILD = TOOLS / "build"


def md5(file):
    return hashlib.md5(file.read_bytes()).hexdigest()


def run(*args):
    subprocess.run([str(a) for a in args], check=True)


def main():
    manifest = json.loads((DATA / "manifest.json").read_text())
    WORK.mkdir(exist_ok=True)
    BUILD.mkdir(exist_ok=True)
    original = WORK / "original.rcc"
    if not original.exists():
        urllib.request.urlretrieve(manifest["original"]["url"], original)
    if md5(original) != manifest["original"]["md5"]:
        raise SystemExit("El paquete original no coincide con el catálogo. No se continúa.")

    flags = subprocess.check_output(
        ["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True).split()
    run("c++", "-std=c++17", TOOLS / "extract_rcc.cpp",
        "-o", BUILD / "extract_rcc", *flags)

    # Directorios exclusivos de esta herramienta; nunca borrar trabajo ajeno.
    baseline = WORK / "pack-baseline"
    overlay = WORK / "pack-overlay"
    verify = WORK / "pack-verify"
    for directory in (baseline, overlay, verify):
        if directory.exists():
            shutil.rmtree(directory)
    run(BUILD / "extract_rcc", original, baseline)
    shutil.copytree(baseline, overlay)

    prefix = "gcompris/data/voices-ogg/es"
    replaced = set()
    added = set()
    for clip in manifest["clips"]:
        relative = pathlib.PurePosixPath(clip["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Ruta de clip inválida")
        source = DATA / "es" / relative
        destination = overlay / prefix / relative
        if not source.read_bytes().startswith(b"OggS"):
            raise ValueError(f"No es OGG: {source}")
        if not destination.is_file():
            if not clip.get("new_file", False):
                raise ValueError(f"No existe en el paquete original: {relative}")
            added.add(f"{prefix}/{relative}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        replaced.add(f"{prefix}/{relative}")

    qrc = ET.Element("RCC", version="1.0")
    resources = ET.SubElement(qrc, "qresource", prefix="/")
    files = sorted(f for f in overlay.rglob("*") if f.is_file())
    for source in files:
        relative = source.relative_to(overlay).as_posix()
        ET.SubElement(resources, "file", alias=relative).text = str(source)
    qrc_path = BUILD / "voices-es.qrc"
    ET.ElementTree(qrc).write(qrc_path, encoding="utf-8", xml_declaration=True)
    target = BUILD / manifest["original"]["filename"]
    rcc = "/usr/lib/qt6/rcc" if pathlib.Path("/usr/lib/qt6/rcc").exists() else "rcc"
    run(rcc, "--binary", "--format-version", "2", "--compress-algo", "zlib",
        "-o", target, qrc_path)
    run(BUILD / "extract_rcc", target, verify)
    old = {f.relative_to(baseline).as_posix() for f in baseline.rglob("*") if f.is_file()}
    new = {f.relative_to(verify).as_posix() for f in verify.rglob("*") if f.is_file()}
    assert old | added == new, "Se han perdido rutas o añadido archivos imprevistos"
    for path in new:
        expected = DATA / "es" / path.removeprefix(prefix + "/") if path in replaced else baseline / path
        assert (verify / path).read_bytes() == expected.read_bytes(), path
    (BUILD / "Contents").write_text(f"{md5(target)}  {target.name}\n")
    report = {"total_files": len(new), "replaced": sorted(replaced - added),
              "added": sorted(added),
              "unchanged": len(new) - len(replaced),
              "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
              "device_verified": False}
    (BUILD / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    print("Paquete:", target)


if __name__ == "__main__":
    main()
