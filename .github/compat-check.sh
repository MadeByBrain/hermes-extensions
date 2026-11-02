#!/usr/bin/env bash
# Compatibility check for MadeByBrain Hermes extensions. Same file in every repo.
# Needs $PY = a Python with Hermes Agent installed (set by .github/workflows/compat.yml).
# Plugins: every folder with plugin.yaml (repo root or plugins/<name>): tests/test_*.py, then
#          `hermes plugins validate --json` with no warnings and no failed check.
# Skills:  every skills/<name>/SKILL.md: Hermes security scan must be "safe", linter without findings.
set -uo pipefail
: "${PY:?set PY to a Python with Hermes Agent installed}"
fail=0
work=$(mktemp -d)
export HERMES_HOME="$work"

plugins=()
[ -f plugin.yaml ] && plugins+=(".")
for d in plugins/*/; do [ -f "$d/plugin.yaml" ] && plugins+=("${d%/}"); done

for p in "${plugins[@]}"; do
  echo "::group::plugin $p"
  for t in "$p"/tests/test_*.py; do
    [ -f "$t" ] || continue
    if (cd "$p" && HERMES_HOME="$(mktemp -d)" "$PY" "tests/$(basename "$t")"); then
      echo "tests ok: $t"
    else
      echo "::error::tests failed: $t"; fail=1
    fi
  done
  if "$PY" -m hermes_cli.main plugins validate "$p" --json > "$work/validate.json" 2> "$work/validate.err"; then :; fi
  if "$PY" - "$work/validate.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
bad = [c["name"] for c in d.get("checks", []) if not c.get("ok")]
print("validate:", "ok" if not bad and not d.get("warnings") else "FAILED", "| warnings:", d.get("warnings"), "| failed:", bad)
sys.exit(1 if bad or d.get("warnings") else 0)
PY
  then :; else echo "::error::hermes plugins validate failed for $p"; cat "$work/validate.err"; fail=1; fi
  echo "::endgroup::"
done

# A plugin in the repo root ships its own skills/ (registered by the plugin): not a tap, not checked here.
[ -f plugin.yaml ] || for s in skills/*/; do
  [ -f "$s/SKILL.md" ] || continue
  echo "::group::skill ${s%/}"
  if "$PY" - "${s%/}" <<'PY'
import sys
from pathlib import Path
from tools.skills_guard import scan_skill
from tools.skill_linter import lint_skill
p = Path(sys.argv[1])
scan = scan_skill(p, source="community")
lint = lint_skill(p / "SKILL.md")
print("scan:", scan.verdict, "| lint findings:", len(lint))
for f in lint:
    print("  ", f)
sys.exit(0 if scan.verdict == "safe" and not lint else 1)
PY
  then :; else echo "::error::skill check failed for $s"; fail=1; fi
  echo "::endgroup::"
done

[ ${#plugins[@]} -gt 0 ] || ls -d skills/*/ >/dev/null 2>&1 || { echo "::error::nothing to check"; fail=1; }
exit $fail
