---
name: reordenar-memorias
description: Reconecta las memorias de Claude Code cuando el usuario mueve, renombra o reorganiza carpetas de proyecto. Usar cuando diga cosas como "moví carpetas", "reordená las memorias", "reorganicé proyectos", "cambié una carpeta de lugar y se desconectó la memoria", o cuando cree/quiera registrar un proyecto nuevo en el sistema de DNI. También para revisar el estado del registro o agregar una carpeta raíz a vigilar.
---

# Reordenar memorias de proyectos (sistema de DNI)

Claude Code indexa memoria e historial por la **ruta absoluta** de la carpeta
(`~/.claude/projects/<clave>/`), así que mover/renombrar una carpeta **desconecta** su memoria.
Este sistema lo resuelve dándole a cada proyecto un DNI estable que viaja dentro de la carpeta
(`.claude-project-id`) y un registro central que recuerda dónde estaba cada uno.

## Herramienta
Motor: `~/.claude/scripts/claude_projects.py` (Python 3, sin dependencias).
Registro: `~/.claude/project-registry.json`. Backups: `~/.claude/projects-archive/`.

## Qué hacer según lo que pida el usuario

**"Moví carpetas / reordená / reorganicé"** → correr:
```bash
python3 ~/.claude/scripts/claude_projects.py reconcile
```
Escanea las raíces vigiladas, enrola proyectos nuevos y reconecta los movidos. Después
mostrar al usuario el resumen (qué se enroló, qué se reconectó) tal cual lo imprime el script.

**"Mostrame el estado / qué proyectos hay"** → correr:
```bash
python3 ~/.claude/scripts/claude_projects.py status
```

**"Registrá este proyecto / enrolá esta carpeta"** (una sola) →
```bash
python3 ~/.claude/scripts/claude_projects.py enroll "/ruta/al/proyecto"
```

**"Sumá esta carpeta raíz a vigilar"** → editar `_config.roots` en
`~/.claude/project-registry.json` (agregar la ruta absoluta) y después correr `reconcile`.

## Reglas y detalles importantes
- **Encoding de clave (macOS):** el script normaliza a NFC y reemplaza todo lo no-ASCII-alfanumérico por `-` (los acentos incluidos: `Estadística` → `Estad-stica`). Esto ya está resuelto dentro del script; no recalcular claves a mano con otra lógica.
- **El hook `SessionStart`** ya estampa el DNI automáticamente al abrir cualquier proyecto, así que los proyectos nuevos se enrolan solos. `reconcile` es para reconectar movimientos en lote.
- **Nunca borrar** claves de `~/.claude/projects/` a mano; el script archiva en `projects-archive/`.
- Raíces vigiladas: las que estén en `_config.roots` del registro (por defecto `~/Developer`, `~/Projects`; editables).
- Si después de reconectar el usuario abre Claude en la carpeta y no recuerda, la clave real difiere: mirar el nombre creado en `~/.claude/projects/` y ajustar.
- Documentación de fondo: memoria `reference-sistema-dni-proyectos`.
