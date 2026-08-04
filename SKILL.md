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
Escanea las raíces vigiladas, enrola proyectos nuevos y reconecta los movidos. Reconecta
memoria + transcripts (reescribiendo el `cwd` interno de los `.jsonl`) y además migra la
config por-proyecto de `~/.claude.json` (servidores MCP, permisos, confianza). Después
mostrar al usuario el resumen tal cual lo imprime el script. Los cambios de `~/.claude.json`
**toman efecto al reiniciar Claude Code**.

**"Se desconectó un conector/MCP/permiso al mover"** → es config de `~/.claude.json`. Correr:
```bash
python3 ~/.claude/scripts/claude_projects.py sync-config     # migra MCP/permisos/confianza a la ruta nueva (no destructivo)
python3 ~/.claude/scripts/claude_projects.py prune-config    # limpia entradas huérfanas ya migradas o sin config
```

**"Dejó de funcionar un plugin / desaparecieron comandos o skills de un plugin al mover"** →
el marketplace del plugin estaba registrado como `directory` (ruta local) y apunta a la ruta
vieja (ver `~/.claude/plugins/known_marketplaces.json`). `reconcile` YA lo detecta y avisa;
también podés correr:
```bash
python3 ~/.claude/scripts/claude_projects.py check-plugins
```
El arreglo **no es automático** (repuntar un marketplace requiere el CLI). Con la ruta nueva que
sugiere el detector:
```bash
claude plugin marketplace remove <nombre-marketplace>
claude plugin marketplace add "<ruta-nueva>"
claude plugin install <plugin>@<nombre-marketplace> --scope user
```
Más robusto (recomendarlo): apuntar el marketplace al **git URL** del repo en vez de a la ruta
local — así no se rompe nunca al mover. Requiere que el plugin esté commiteado y pusheado. Todo
esto **toma efecto al reiniciar Claude Code**. Solo aplica a los pocos repos que hostean un plugin.

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
