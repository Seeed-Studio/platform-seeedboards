#!/usr/bin/env python3
"""Workflow-structure gate.

GitHub silently ignores a workflow file it cannot parse, and a workflow that
only runs on `main` never validates the branch this repository ships from.
Both failure modes are invisible in a green matrix, so check them offline:

  * every .github/workflows/*.yml parses (undefined YAML aliases fail here);
  * every workflow declares least-privilege `permissions: contents: read`;
  * every push workflow includes the maintained `v3` branch.

    python scripts/ci/verify_workflows.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _on_block(data):
    # PyYAML resolves the YAML 1.1 `on` key to boolean True.
    value = data.get("on", data.get(True))
    return value if isinstance(value, dict) else {}


def check_workflows(workflows_dir: Path) -> list:
    errors = []
    try:
        import yaml
    except ImportError:
        return ["PyYAML is required (pip install -r requirements-ci.txt)"]

    paths = sorted(workflows_dir.glob("*.yml")) + sorted(
        workflows_dir.glob("*.yaml"))
    if not paths:
        return ["no workflow files under %s" % workflows_dir]

    for path in paths:
        rel = path.relative_to(workflows_dir)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            errors.append("%s: YAML parse failed: %s" % (rel, exc))
            continue
        if not isinstance(data, dict):
            errors.append("%s: top-level value is not a mapping" % rel)
            continue

        permissions = data.get("permissions")
        if not isinstance(permissions, dict):
            errors.append(
                "%s: missing least-privilege `permissions:` block" % rel)
        elif permissions.get("contents") not in ("read",):
            errors.append(
                "%s: permissions.contents must be `read` (got %r)"
                % (rel, permissions.get("contents")))

        on_block = _on_block(data)
        push = on_block.get("push")
        if isinstance(push, dict):
            branches = push.get("branches")
            if isinstance(branches, list) and "v3" not in branches:
                errors.append(
                    "%s: push branches %r do not include `v3`; badges and "
                    "post-merge validation target v3" % (rel, branches))
        elif push is not None:
            errors.append("%s: push event must be a mapping" % rel)

    return errors


def main(argv: list = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflows-dir", type=Path,
                        default=REPO_ROOT / ".github" / "workflows")
    args = parser.parse_args(argv)

    errors = check_workflows(args.workflows_dir)
    if errors:
        for error in errors:
            print("verify_workflows: %s" % error, file=sys.stderr)
        print("verify_workflows: FAILED (%d error(s))" % len(errors),
              file=sys.stderr)
        return 1
    print("verify_workflows: OK (YAML parses; permissions and v3 push "
          "branches present)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())