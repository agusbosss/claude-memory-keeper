#!/usr/bin/env bash
#
# claude-mv-project.sh — mueve un proyecto y RECONECTA su memoria/historial de Claude Code.
#
# Claude Code indexa memoria e historial por la RUTA ABSOLUTA de la carpeta
# (~/.claude/projects/<clave>/), así que al mover/renombrar la carpeta se
# "desconecta". Este script recoloca esa data a la clave de la ruta nueva.
#
# USO:
#   claude-mv-project.sh "<ruta_vieja>" "<ruta_nueva>"            # (dry-run: solo muestra qué haría)
#   claude-mv-project.sh "<ruta_vieja>" "<ruta_nueva>" --apply    # ejecuta
#   claude-mv-project.sh "<ruta_vieja>" "<ruta_nueva>" --apply --move-files
#         ^ además MUEVE la carpeta en disco (si todavía no la moviste)
#
# EJEMPLOS:
#   claude-mv-project.sh ~/Downloads/mi-app ~/Developer/mi-app --apply --move-files
#   claude-mv-project.sh "~/Projects/old-name" "~/Projects/new-name" --apply
#
set -euo pipefail

OLD_RAW="${1:-}"; NEW_RAW="${2:-}"
APPLY=0; MOVEFILES=0
for a in "${@:3}"; do
  case "$a" in
    --apply) APPLY=1 ;;
    --move-files) MOVEFILES=1 ;;
    *) echo "flag desconocido: $a"; exit 2 ;;
  esac
done
if [ -z "$OLD_RAW" ] || [ -z "$NEW_RAW" ]; then
  grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 1
fi

# Expandir ~ y normalizar a ruta absoluta (sin exigir que exista todavía).
expand() { eval echo "$1"; }
OLD="$(expand "$OLD_RAW")"; NEW="$(expand "$NEW_RAW")"

# Codificación de ruta -> clave, igual que Claude Code:
# cada carácter que NO es letra/dígito (Unicode: acentos cuentan como letra) -> '-'
enc() { python3 -c "import sys; p=sys.argv[1]; print(''.join(c if c.isalnum() else '-' for c in p))" "$1"; }

PROJ="$HOME/.claude/projects"
OLD_KEY="$(enc "$OLD")"; NEW_KEY="$(enc "$NEW")"
OLD_DIR="$PROJ/$OLD_KEY"; NEW_DIR="$PROJ/$NEW_KEY"

echo "──────────────────────────────────────────────────────────"
echo "Ruta vieja : $OLD"
echo "Ruta nueva : $NEW"
echo "Clave vieja: $OLD_KEY"
echo "Clave nueva: $NEW_KEY"
echo "──────────────────────────────────────────────────────────"

# ¿Existe la data vieja? Si no, buscar candidatos parecidos.
if [ ! -d "$OLD_DIR" ]; then
  echo "⚠ No encontré data de Claude en la clave vieja calculada."
  base="$(basename "$OLD")"; hint="$(enc "$base")"
  echo "  Candidatos que contienen '$hint':"
  ls -1 "$PROJ" | grep -F "$hint" | sed 's/^/    /' || echo "    (ninguno)"
  echo "  → Si ves la clave correcta arriba, corré el script con esa ruta exacta,"
  echo "    o pedile a Claude que la reconecte."
  exit 1
fi

nmem=$(ls -1 "$OLD_DIR/memory"/*.md 2>/dev/null | wc -l | tr -d ' ')
nses=$(ls -1 "$OLD_DIR"/*.jsonl 2>/dev/null | wc -l | tr -d ' ')
echo "Data a reconectar: ${nmem} archivos de memoria, ${nses} transcripts de sesión."

if [ "$APPLY" -eq 0 ]; then
  echo ""
  echo "DRY-RUN (no cambié nada). Para ejecutar, agregá  --apply"
  [ "$MOVEFILES" -eq 1 ] && echo "(y con --move-files además movería la carpeta en disco)"
  exit 0
fi

# Mover la carpeta en disco (opcional)
if [ "$MOVEFILES" -eq 1 ]; then
  if [ ! -d "$OLD" ]; then echo "✗ La carpeta en disco no existe: $OLD"; exit 1; fi
  mkdir -p "$(dirname "$NEW")"
  mv "$OLD" "$NEW"
  echo "✓ Carpeta movida en disco: $NEW"
fi

# Reconectar la data de Claude (merge si el destino ya existe)
mkdir -p "$NEW_DIR/memory"
[ -d "$OLD_DIR/memory" ] && cp -R "$OLD_DIR/memory/." "$NEW_DIR/memory/" 2>/dev/null || true
for j in "$OLD_DIR"/*.jsonl; do [ -e "$j" ] && cp -n "$j" "$NEW_DIR/" || true; done
echo "✓ Memoria e historial copiados a la clave nueva."

# Dejar la clave vieja como respaldo renombrada (no la borro por las dudas)
mv "$OLD_DIR" "${OLD_DIR}__movido-$(python3 -c 'import time;print(int(time.time()))')" 2>/dev/null || true
echo "✓ Clave vieja archivada como respaldo (borrala cuando confirmes que anda)."
echo ""
echo "VERIFICACIÓN: abrí Claude Code en  $NEW  y preguntale algo del proyecto."
echo "Si recuerda → listo. Si no → el nombre real de la clave difiere; mirá en"
echo "  ~/.claude/projects/  la carpeta que se creó al abrir, y avisá para ajustar."
