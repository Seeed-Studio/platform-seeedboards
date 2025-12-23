#!/usr/bin/env python3

from __future__ import annotations

import sys

from _examples_build_lib import (
    build_projects,
    filter_projects_by_prefix,
    find_platformio_projects,
    make_argparser,
    repo_root,
)


def main(argv: list[str]) -> int:
    parser = make_argparser("Build Arduino PlatformIO example projects under examples/ (all envs).")
    args = parser.parse_args(argv)

    examples_dir = (repo_root() / args.examples_dir).resolve()
    if not examples_dir.exists():
        print(f"Examples dir not found: {examples_dir}", file=sys.stderr)
        return 2

    projects = find_platformio_projects(examples_dir)
    projects = filter_projects_by_prefix(projects, allowed_prefixes=("arduino-",))
    if not projects:
        print(f"No Arduino projects found under: {examples_dir}", file=sys.stderr)
        return 2

    if args.list:
        for project_dir in projects:
            print(str(project_dir.relative_to(repo_root())))
        return 0

    return build_projects(projects, verbose=args.verbose)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
