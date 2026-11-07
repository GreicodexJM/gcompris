#!/usr/bin/env python3
"""Generación reanudable, sin voces de biblioteca de pago ni reintentos ciegos.

La clave se lee de ~/.keys o ELEVENLABS_API_KEY. No se escribe en el repo ni log.
Los MP3 se guardan en work/elevenlabs; la conversión y la instalación son fases
separadas. Nunca sustituye un audio sin texto validado ni borra el original.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/voices-latam"
WORK = ROOT / "tools/latam/work/elevenlabs"
# Solo las voces predefinidas devueltas por la cuenta como category=premade.
VOICES = {"jessica": "cgSgspJ2msm6clMCkdW9", "george": "JBFqnCBsd6RMkjVDRZzb"}


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def key():
    value = os.environ.get("ELEVENLABS_API_KEY")
    if value:
        return value
    for line in (Path.home() / ".keys").read_text().splitlines():
        line = line.strip().removeprefix("export ")
        if line.startswith("ELEVENLABS_API_KEY="):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit("Falta ELEVENLABS_API_KEY")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="Sin esta opción solo calcula el lote")
    parser.add_argument("--max-characters", type=int, default=9000,
                        help="Tope persistente para este proyecto; no se reinicia entre ejecuciones")
    parser.add_argument("--max-clips", type=int, default=1000)
    args = parser.parse_args()
    catalog = json.loads((DATA / "catalog-elevenlabs.json").read_text())
    WORK.mkdir(parents=True, exist_ok=True)
    lock = (WORK / "generator.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise SystemExit("Ya existe otro generador activo")
    try:
        return run_locked(args)
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def run_locked(args):
    catalog = json.loads((DATA / "catalog-elevenlabs.json").read_text())
    ledger = WORK / "state.json"
    state = json.loads(ledger.read_text()) if ledger.exists() else {"reserved_characters": 0, "clips": {}}
    pending = [c for c in catalog["clips"] if c["status"] == "ready" and c["path"] not in state["clips"]]
    print("Pendientes listos:", len(pending), "caracteres:", sum(len(c["text"]) for c in pending), flush=True)
    print("Reservados históricamente:", state["reserved_characters"], "tope:", args.max_characters, flush=True)
    print("Sin transcripción o revisión fonética:", sum(c["status"] != "ready" for c in catalog["clips"]), flush=True)
    if not args.run:
        return
    api_key = key()
    # Confirmar que siguen siendo voces predefinidas; no cambiar a biblioteca.
    req = urllib.request.Request("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": api_key})
    with urllib.request.urlopen(req, timeout=30) as response:
        voice_data = json.load(response)
    categories = {v["voice_id"]: v.get("category") for v in voice_data["voices"]}
    for clip in pending[:args.max_clips]:
        voice_id = VOICES[clip["voice"]]
        if categories.get(voice_id) != "premade":
            raise SystemExit("Voz no incluida como premade. No se genera.")
        path = clip["path"]
        payload = {"text": clip["text"], "model_id": catalog["model"], "language_code": "es",
                   "voice_settings": {"stability": 0.5, "similarity_boost": 0.75,
                                      "style": 0.2, "use_speaker_boost": True}}
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        cost = len(clip["text"])
        if state["reserved_characters"] + cost > args.max_characters:
            print("PARADA: tope local de caracteres; no se envía otra petición", flush=True)
            break
        state["reserved_characters"] += cost
        record = {"status": "submitting", "text": clip["text"], "voice_id": voice_id,
                  "fingerprint": fingerprint, "reserved_characters": cost,
                  "at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        state["clips"][path] = record
        atomic(ledger, (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode())
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"
        request = urllib.request.Request(url, data=json.dumps(payload).encode(),
                    headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
        print("GENERANDO", path, flush=True)
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                content_type = response.headers.get("Content-Type", "")
                data = response.read()
                record["charged_characters"] = response.headers.get("character-cost")
                record["request_id"] = response.headers.get("request-id")
            if "audio" not in content_type or len(data) < 128:
                raise ValueError("Respuesta no reconocida como audio")
            target = WORK / "mp3" / Path(path).with_suffix(".mp3")
            atomic(target, data)
            record.update(status="completed", bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            print("LISTO", path, len(data), "bytes", flush=True)
        except urllib.error.HTTPError as error:
            # No imprimir cuerpos que puedan contener identificadores o claves.
            detail = error.read()
            error.close()
            try:
                parsed = json.loads(detail).get("detail", {})
                reason = parsed.get("status", parsed.get("code", "")) if isinstance(parsed, dict) else ""
            except ValueError:
                reason = ""
            record.update(status="rejected", http_status=error.code, reason=reason)
            print("PARADA: HTTP", error.code, reason, "sin fallback ni reintento", flush=True)
        except Exception as error:
            record.update(status="unknown_outcome", error_type=type(error).__name__)
            print("PARADA: resultado incierto; revisar antes de reenviar", flush=True)
        atomic(ledger, (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode())
        if record["status"] != "completed":
            break
    print("Completados:", sum(c["status"] == "completed" for c in state["clips"].values()), flush=True)


if __name__ == "__main__":
    main()
