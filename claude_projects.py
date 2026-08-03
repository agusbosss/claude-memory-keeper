#!/usr/bin/env python3
"""
claude_projects.py — Sistema de "DNI" para proyectos de Claude Code.

Problema: Claude Code guarda memoria e historial indexados por la RUTA ABSOLUTA
de la carpeta (~/.claude/projects/<clave>/). Si movés/renombrás la carpeta, la
clave cambia y la memoria queda "huérfana".

Solución: cada proyecto lleva un archivo oculto `.claude-project-id` (su DNI, un
id estable que viaja DENTRO de la carpeta) y hay un registro central
(~/.claude/project-registry.json) que recuerda dónde estaba cada DNI. Comparando
"dónde está el DNI ahora" vs "dónde decía el registro" se detecta el movimiento y
se reconecta la memoria a la clave nueva, en forma automática.

Subcomandos:
  enroll <ruta>   Estampa el DNI en esa carpeta (si falta), la registra y —si se
                  movió— reconecta su memoria. Rápido, para el hook SessionStart.
  reconcile       Escanea las carpetas raíz, enrola proyectos nuevos y reconecta
                  todos los que se hayan movido (memoria + .jsonl con cwd reescrito
                  + config de ~/.claude.json). Para "moví varias cosas, ordená".
  sync-config     Migra la config por-proyecto de ~/.claude.json (MCP, permisos,
                  confianza) a la ruta nueva. No destructivo. Efecto al reiniciar.
  prune-config    Limpia entradas huérfanas de ~/.claude.json ya migradas o sin config.
  status          Muestra el registro (qué proyecto vive dónde + historial).

Config (dentro del registro, editable): _config.roots = carpetas a vigilar.
"""
import sys, os, json, time, uuid, shutil, unicodedata
from datetime import datetime
from pathlib import Path

HOME = Path.home()
PROJECTS = HOME / ".claude" / "projects"
ARCHIVE  = HOME / ".claude" / "projects-archive"
REGISTRY = HOME / ".claude" / "project-registry.json"
CLAUDE_JSON = HOME / ".claude.json"   # config global por-proyecto (indexada por ruta): MCP, permisos, confianza
MARKER   = ".claude-project-id"
# Claves de config por-proyecto que hay que migrar cuando una carpeta se mueve.
CONFIG_KEYS = ("mcpServers", "enabledMcpjsonServers", "disabledMcpjsonServers",
               "allowedTools", "hasTrustDialogAccepted")
DEFAULT_ROOTS = [str(HOME / "Developer"), str(HOME / "Projects")]  # editá según tus carpetas madre
PRUNE = {"node_modules", ".git", ".venv", "venv", "__pycache__", ".next",
         "dist", "build", ".cache", "Library", ".Trash"}
MAX_DEPTH = 3  # profundidad de escaneo bajo cada raíz


def enc(path: str) -> str:
    """Ruta -> clave, EXACTAMENTE como Claude Code en macOS: normaliza a NFC y
    reemplaza por '-' todo lo que no sea ASCII alfanumérico (los acentos también:
    'Estadística' -> 'Estad-stica'). macOS guarda nombres en NFD, por eso el
    normalize('NFC') es imprescindible para que la clave coincida."""
    path = unicodedata.normalize("NFC", path)
    return "".join(c if (c.isascii() and c.isalnum()) else "-" for c in path)

def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def load_registry() -> dict:
    if REGISTRY.exists():
        try:
            data = json.loads(REGISTRY.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = {}
    data.setdefault("_config", {"roots": DEFAULT_ROOTS, "version": 1})
    data.setdefault("projects", {})
    return data

def save_registry(reg: dict):
    REGISTRY.write_text(json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")

def read_marker(folder: Path):
    m = folder / MARKER
    if not m.exists():
        return None
    try:
        return json.loads(m.read_text(encoding="utf-8")).get("id")
    except Exception:
        return None

def write_marker(folder: Path, pid: str):
    (folder / MARKER).write_text(
        json.dumps({"id": pid, "nombre": folder.name}, ensure_ascii=False, indent=2),
        encoding="utf-8")

def has_claude_data(key: str) -> bool:
    d = PROJECTS / key
    return d.is_dir()

def has_memory(key: str) -> bool:
    mem = PROJECTS / key / "memory"
    return mem.is_dir() and any(mem.glob("*.md"))


def relink(old_key: str, new_key: str, old_path: str = "", new_path: str = "") -> int:
    """Copia memoria + transcripts de la clave vieja a la nueva (sin pisar lo más nuevo)
    y archiva la clave vieja. En los .jsonl reescribe la ruta vieja por la nueva (el
    campo 'cwd' y cualquier ruta absoluta embebida quedan hardcodeados adentro, así que
    hay que reescribirlos para poder reanudar sesiones con --resume). Devuelve cuántos
    archivos de memoria copió."""
    old_dir, new_dir = PROJECTS / old_key, PROJECTS / new_key
    if not old_dir.is_dir():
        return 0
    (new_dir / "memory").mkdir(parents=True, exist_ok=True)
    copied = 0
    om = old_dir / "memory"
    if om.is_dir():
        for f in om.iterdir():
            dst = new_dir / "memory" / f.name
            if f.is_file() and not dst.exists():
                shutil.copy2(f, dst); copied += 1
    for f in old_dir.glob("*.jsonl"):
        dst = new_dir / f.name
        if not dst.exists():
            if old_path and new_path:
                # reescribir la ruta vieja embebida (cwd, etc.) por la nueva
                dst.write_text(f.read_text(encoding="utf-8").replace(old_path, new_path),
                               encoding="utf-8")
            else:
                shutil.copy2(f, dst)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    shutil.move(str(old_dir), str(ARCHIVE / f"{old_key}.{int(time.time())}"))
    return copied


def sync_claude_json(reg: dict):
    """Migra la config por-proyecto de ~/.claude.json (MCP, permisos, confianza) desde
    rutas viejas (huérfanas) a la ruta ACTUAL de cada proyecto. NO destructivo: solo
    rellena claves que falten en el destino, nunca pisa lo que ya está. Devuelve la
    lista de (ruta_vieja, ruta_nueva, claves_migradas)."""
    if not CLAUDE_JSON.exists():
        return []
    data = json.loads(CLAUDE_JSON.read_text(encoding="utf-8"))
    projects = data.get("projects", {})
    if not isinstance(projects, dict):
        return []
    # índice: basename -> ruta(s) actuales de proyectos que existen en disco
    cur = {}
    for e in reg["projects"].values():
        p = e["path"]
        if os.path.isdir(p):
            cur.setdefault(os.path.basename(p), []).append(p)
    changes = []
    for opath, ocfg in list(projects.items()):
        if os.path.isdir(opath) or not isinstance(ocfg, dict):
            continue  # solo entradas huérfanas (carpeta ya no existe)
        payload = {k: ocfg[k] for k in CONFIG_KEYS if ocfg.get(k)}
        if not payload:
            continue  # nada que valga la pena migrar
        targets = cur.get(os.path.basename(opath), [])
        if len(targets) != 1:
            continue  # sin match único → no arriesgar
        dest = projects.setdefault(targets[0], {})
        added = [k for k, v in payload.items() if not dest.get(k) and dest.__setitem__(k, v) is None]
        if added:
            changes.append((opath, targets[0], added))
    if changes:
        shutil.copy2(CLAUDE_JSON, CLAUDE_JSON.with_suffix(f".json.bak-{int(time.time())}"))
        CLAUDE_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return changes


def prune_claude_json(reg: dict):
    """Elimina de ~/.claude.json las entradas huérfanas (carpeta inexistente) que son
    seguras de borrar: las que no tienen config, o las que SÍ tienen pero ya fue migrada
    a un proyecto vivo con el mismo basename. Nunca borra config sin respaldo. Backup
    previo. Devuelve la lista de rutas eliminadas."""
    if not CLAUDE_JSON.exists():
        return []
    data = json.loads(CLAUDE_JSON.read_text(encoding="utf-8"))
    projects = data.get("projects", {})
    if not isinstance(projects, dict):
        return []
    live = {}  # basename -> config del proyecto vivo (para chequear si ya se migró)
    for p, c in projects.items():
        if os.path.isdir(p) and isinstance(c, dict):
            live.setdefault(os.path.basename(p), c)
    removed = []
    for p in list(projects.keys()):
        c = projects[p]
        if os.path.isdir(p):
            continue  # existe → no tocar
        payload = {k for k in CONFIG_KEYS if isinstance(c, dict) and c.get(k)}
        if not payload:
            del projects[p]; removed.append(p); continue      # nada que perder
        tgt = live.get(os.path.basename(p))                    # ¿ya migrada a un vivo?
        if tgt is not None and all(tgt.get(k) for k in payload):
            del projects[p]; removed.append(p)
    if removed:
        shutil.copy2(CLAUDE_JSON, CLAUDE_JSON.with_suffix(f".json.bak-{int(time.time())}"))
        CLAUDE_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return removed


def process_folder(path: str, reg: dict, force_mint: bool):
    """Procesa UNA carpeta: enrola si falta DNI y reconecta si se movió.
    force_mint=True (hook): estampa DNI aunque todavía no haya data de Claude.
    Devuelve (accion, detalle) o None si no aplica."""
    path = os.path.abspath(path).rstrip("/")
    folder = Path(path)
    if not folder.is_dir():
        return None
    key = enc(path)
    pid = read_marker(folder)

    if pid is None:
        if not force_mint and not has_claude_data(key):
            return None  # no es un proyecto de Claude: no tocar
        pid = uuid.uuid4().hex[:8]
        write_marker(folder, pid)

    entry = reg["projects"].get(pid)
    if entry is None:
        reg["projects"][pid] = {
            "nombre": folder.name, "path": path, "key": key,
            "historial": [f"{now()} · enrolado en {path}"],
        }
        return ("enrolado", path)

    if entry["key"] != key:                      # se movió o renombró
        n = relink(entry["key"], key, entry["path"], path)
        entry["historial"].append(f"{now()} · {entry['path']} → {path}")
        entry["nombre"], entry["path"], entry["key"] = folder.name, path, key
        return ("movido", f"{path}  ({n} memorias reconectadas)")

    if entry["path"] != path:                    # ruta cosmética distinta
        entry["path"] = path
    return ("ok", path)


def iter_project_folders(roots):
    """Recorre las raíces (acotado) y devuelve carpetas candidatas a proyecto:
    las que tienen DNI o las que tienen data de Claude para su clave."""
    seen = set()
    for root in roots:
        root = os.path.abspath(os.path.expanduser(root))
        if not os.path.isdir(root):
            continue
        base_depth = root.rstrip("/").count(os.sep)
        for dirpath, dirnames, filenames in os.walk(root):
            depth = dirpath.rstrip("/").count(os.sep) - base_depth
            dirnames[:] = [] if depth >= MAX_DEPTH else [d for d in dirnames
                           if d not in PRUNE and not d.startswith(".")]
            if dirpath == root:
                continue
            has_dni = MARKER in filenames
            is_proj = has_claude_data(enc(os.path.abspath(dirpath)))
            if (has_dni or is_proj) and dirpath not in seen:
                seen.add(dirpath)
                yield dirpath
                # seguimos descendiendo: puede haber proyectos ANIDADOS
                # (ej. ~/Projects/course/final-project dentro de ~/Projects/course). PRUNE + MAX_DEPTH acotan el costo.


def cmd_enroll(path):
    reg = load_registry()
    res = process_folder(path, reg, force_mint=True)
    save_registry(reg)
    if res and res[0] in ("enrolado", "movido"):
        print(f"[claude-dni] {res[0]}: {res[1]}")

def cmd_reconcile():
    reg = load_registry()
    roots = reg["_config"].get("roots", DEFAULT_ROOTS)
    counts = {"enrolado": 0, "movido": 0, "ok": 0}
    moved, enrolled = [], []
    for folder in iter_project_folders(roots):
        res = process_folder(folder, reg, force_mint=False)
        if not res:
            continue
        counts[res[0]] = counts.get(res[0], 0) + 1
        if res[0] == "movido":   moved.append(res[1])
        if res[0] == "enrolado": enrolled.append(res[1])
    save_registry(reg)
    cfg_changes = sync_claude_json(reg)
    print(f"Raíces vigiladas: {', '.join(roots)}")
    print(f"Proyectos: {counts['ok']} sin cambios · {counts['enrolado']} enrolados · {counts['movido']} movidos\n")
    if enrolled:
        print("Enrolados (DNI nuevo):")
        for e in enrolled: print(f"  + {e}")
    if moved:
        print("Reconectados (se movieron):")
        for m in moved: print(f"  ↪ {m}")
    if cfg_changes:
        print("Config de ~/.claude.json migrada (MCP/permisos/confianza):")
        for old, new, keys in cfg_changes:
            print(f"  ⚙ {new}  ←  [{', '.join(keys)}]")
    if not enrolled and not moved and not cfg_changes:
        print("Todo ya estaba en orden. Nada que reconectar.")

def cmd_status():
    reg = load_registry()
    print(f"Registro: {REGISTRY}")
    print(f"Raíces: {', '.join(reg['_config'].get('roots', []))}")
    print(f"Proyectos registrados: {len(reg['projects'])}\n")
    for pid, e in sorted(reg["projects"].items(), key=lambda x: x[1]["nombre"].lower()):
        print(f"  [{pid}] {e['nombre']}")
        print(f"        {e['path']}")
        if len(e.get("historial", [])) > 1:
            print(f"        movimientos: {len(e['historial'])-1}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__); sys.exit(1)
    cmd = args[0]
    if cmd == "enroll" and len(args) >= 2:
        cmd_enroll(args[1])
    elif cmd == "reconcile":
        cmd_reconcile()
    elif cmd == "sync-config":
        reg = load_registry()
        changes = sync_claude_json(reg)
        if changes:
            print("Config de ~/.claude.json migrada:")
            for old, new, keys in changes:
                print(f"  ⚙ {new}  ←  [{', '.join(keys)}]  (venía de {old})")
        else:
            print("Nada que migrar en ~/.claude.json.")
    elif cmd == "prune-config":
        reg = load_registry()
        removed = prune_claude_json(reg)
        if removed:
            print(f"Entradas huérfanas eliminadas de ~/.claude.json: {len(removed)}")
            for p in removed: print(f"  − {p}")
        else:
            print("No hay entradas huérfanas seguras de eliminar.")
    elif cmd == "status":
        cmd_status()
    else:
        print(__doc__); sys.exit(1)
