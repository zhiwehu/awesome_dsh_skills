#!/usr/bin/env bash
# Install skills from this repository into a DSH skill directory.
#
#   ./install.sh                      list available skills
#   ./install.sh <skill> [<skill>...] install the named skills
#   ./install.sh --all                install every skill
#
# Target (default: user-wide ~/.dsh/skills):
#   --user      -> ${DSH_HOME:-$HOME/.dsh}/skills
#   --agents    -> ${DSH_AGENTS_HOME:-$HOME/.agents}/skills
#   --project   -> ./.dsh/skills
#   --dest DIR  -> an explicit directory
#
# Options:
#   -f, --force   overwrite a skill directory that already exists
#
# Compatible with bash 3.2 (the version macOS ships).

set -eu

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_SRC="$REPO_DIR/skills"

target="user"
dest=""
force=0
all=0
want_list=0
names=""

usage() {
    sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --user)    target="user" ;;
        --agents)  target="agents" ;;
        --project) target="project" ;;
        --dest)    shift; [ $# -gt 0 ] || { echo "error: --dest needs a directory" >&2; exit 2; }; dest="$1"; target="explicit" ;;
        -f|--force) force=1 ;;
        --all)     all=1 ;;
        -h|--help) usage 0 ;;
        -*)        echo "error: unknown option: $1" >&2; usage 2 ;;
        *)         if [ -z "$names" ]; then names="$1"; else names="$names $1"; fi ;;
    esac
    shift
done

# --- available skills --------------------------------------------------------
list_skills() {
    for d in "$SKILLS_SRC"/*/; do
        [ -f "$d/SKILL.md" ] || continue
        basename "$d"
    done
}

# --- resolve destination -----------------------------------------------------
case "$target" in
    agents)   dest="${DSH_AGENTS_HOME:-$HOME/.agents}/skills" ;;
    project)  dest=".dsh/skills" ;;
    explicit) : ;;
    *)        dest="${DSH_HOME:-$HOME/.dsh}/skills" ;;
esac
case "$dest" in
    "~/"*) dest="$HOME/${dest#\~/}" ;;
esac

if [ "$all" -eq 0 ] && [ -z "$names" ]; then
    echo "Available skills in $SKILLS_SRC:"
    list_skills | sed 's/^/  - /'
    echo
    echo "Install with: $0 <skill-name> [--user|--agents|--project|--dest DIR]"
    exit 0
fi

[ "$all" -eq 1 ] && names="$(list_skills | tr '\n' ' ')"

# --- install -----------------------------------------------------------------
mkdir -p "$dest"
installed=0
failed=0

for skill in $names; do
    src="$SKILLS_SRC/$skill"
    if [ ! -f "$src/SKILL.md" ]; then
        echo "error: no such skill: $skill (no $src/SKILL.md)" >&2
        failed=1
        continue
    fi
    dst="$dest/$skill"
    if [ -e "$dst" ] && [ "$force" -ne 1 ]; then
        echo "skip  $skill — already installed at $dst (use --force to overwrite)"
        continue
    fi
    rm -rf "$dst"
    cp -R "$src" "$dst"
    # never copy build caches into a user's skills directory
    find "$dst" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
    find "$dst" -name '.DS_Store' -type f -delete 2>/dev/null || true
    echo "ok    $skill -> $dst"
    installed=$((installed + 1))
done

echo
echo "Installed $installed skill(s) into $dest"
echo "Reload your DSH session to pick them up."
[ "$failed" -eq 0 ] || exit 1
