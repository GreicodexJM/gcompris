#!/usr/bin/env python3
"""Empaqueta un piloto independiente usando el APK original y las voces locales.

No es una compilación completa de Qt: reutiliza el binario de F-Droid sin cambiar
su código ejecutable. El identificador nuevo evita borrar el progreso original.
"""
import argparse
import pathlib
import struct
import subprocess
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
BUILD = ROOT / "tools/latam/build"


def length(data, pos, utf8):
    if utf8:
        value = data[pos]
        return (((value & 127) << 8) | data[pos + 1], pos + 2) if value & 128 else (value, pos + 1)
    value = struct.unpack_from("<H", data, pos)[0]
    return (((value & 32767) << 16) | struct.unpack_from("<H", data, pos + 2)[0], pos + 4) if value & 32768 else (value, pos + 2)


def encode_length(n, utf8):
    if utf8:
        return bytes((128 | (n >> 8), n & 255)) if n >= 128 else bytes((n,))
    return struct.pack("<HH", 32768 | (n >> 16), n & 65535) if n >= 32768 else struct.pack("<H", n)


def replace_pool(chunk, replacements):
    header, size, count, styles, flags, start, style_start = struct.unpack_from("<H6I", chunk, 2)
    utf8 = bool(flags & 256)
    offsets = []
    content = bytearray()
    for i in range(count):
        offset = struct.unpack_from("<I", chunk, header + i * 4)[0]
        n, pos = length(chunk, start + offset, utf8)
        if utf8:
            byte_count, pos = length(chunk, pos, True)
            text = chunk[pos:pos + byte_count].decode("utf-8")
        else:
            text = chunk[pos:pos + n * 2].decode("utf-16le")
        text = replacements.get(text, text)
        offsets.append(len(content))
        encoded = text.encode("utf-8" if utf8 else "utf-16le")
        units = len(text.encode("utf-16le")) // 2
        content.extend(encode_length(units, utf8))
        if utf8:
            content.extend(encode_length(len(encoded), True))
        content.extend(encoded)
        content.extend(b"\0" if utf8 else b"\0\0")
    content.extend(b"\0" * (-len(content) % 4))
    result = bytearray(chunk[:start])
    for i, offset in enumerate(offsets):
        struct.pack_into("<I", result, header + i * 4, offset)
    new_style_start = start + len(content) if style_start else 0
    result.extend(content)
    if style_start:
        result.extend(chunk[style_start:])
    struct.pack_into("<I", result, 4, len(result))
    struct.pack_into("<I", result, 24, new_style_start)
    return bytes(result)


def patch_container(data, replacements):
    header = struct.unpack_from("<H", data, 2)[0]
    result = bytearray(data[:header])
    pos = header
    pools = 0
    while pos < len(data):
        kind, _, size = struct.unpack_from("<HHI", data, pos)
        if size < 8 or pos + size > len(data):
            raise ValueError("Contenedor Android inválido")
        chunk = data[pos:pos + size]
        if kind == 1:  # RES_STRING_POOL_TYPE
            chunk = replace_pool(chunk, replacements)
            pools += 1
        elif kind == 0x200:  # RES_TABLE_PACKAGE_TYPE: nombre UTF-16 de tamaño fijo
            chunk = bytearray(chunk)
            old_name = bytes(chunk[12:268]).decode("utf-16le").rstrip("\0")
            new_name = replacements.get(old_name, old_name).encode("utf-16le")
            if len(new_name) >= 256:
                raise ValueError("Identificador Android demasiado largo")
            chunk[12:268] = new_name.ljust(256, b"\0")
        result.extend(chunk)
        pos += size
    if not pools:
        raise ValueError("No hay tabla de cadenas")
    struct.pack_into("<I", result, 4, len(result))
    return bytes(result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("apk", type=pathlib.Path)
    args = parser.parse_args()
    sdk = pathlib.Path.home() / "Android/Sdk/build-tools/34.0.0"
    package = "net.gcompris.latn"
    name = "GCompris Latino"
    replacements = {"net.gcompris.full": package, "GCompris": name}
    unsigned = BUILD / "latam-unsigned.apk"
    aligned = BUILD / "latam-aligned.apk"
    output = BUILD / "gcompris-latino.apk"
    voice = BUILD / "voices-es-2018-12-20-21-49-05.rcc"
    if not voice.exists():
        raise SystemExit("Ejecutar pack.py primero")
    with zipfile.ZipFile(args.apk) as src, zipfile.ZipFile(unsigned, "w") as dst:
        for info in src.infolist():
            if info.filename.startswith("META-INF/"):
                continue
            data = src.read(info)
            if info.filename == "AndroidManifest.xml":
                # GCompris es también android.app.lib_name: no renombrar la
                # biblioteca nativa al cambiar la etiqueta visible de la app.
                data = patch_container(data, {"net.gcompris.full": package})
            elif info.filename == "resources.arsc":
                data = patch_container(data, replacements)
            dst.writestr(info, data)
        dst.write(voice, "assets/data3/voices-ogg/" + voice.name, compress_type=zipfile.ZIP_STORED)
        dst.write(BUILD / "Contents", "assets/data3/voices-ogg/Contents", compress_type=zipfile.ZIP_STORED)
    subprocess.run([str(sdk / "zipalign"), "-f", "-p", "4", str(unsigned), str(aligned)], check=True)
    subprocess.run([str(sdk / "apksigner"), "sign", "--ks", str(pathlib.Path.home() / ".android/debug.keystore"),
                    "--ks-pass", "pass:android", "--ks-key-alias", "androiddebugkey",
                    "--out", str(output), str(aligned)], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([str(sdk / "apksigner"), "verify", str(output)], check=True)
    print("Piloto independiente:", output)
    print("Paquete:", package)


if __name__ == "__main__":
    main()
