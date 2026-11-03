"""
clean_raw: Remove cloned Python library source trees

Deletes directories under raw_python/. Without arguments, removes all of them.
Pass one or more library names to remove only those.

Usage:
    python clean_raw.py                  # remove all
    python clean_raw.py requests         # remove one
    python clean_raw.py requests pandas  # remove several
"""

import shutil
import sys
from pathlib import Path

RAW_DIR = Path("raw_python")


def remove(name: str) -> None:
    target = RAW_DIR / name
    if target.is_dir():
        shutil.rmtree(target)
        print(f"Removed: {target}")
    else:
        print(f"Not found: {target}")


def main() -> None:
    if not RAW_DIR.is_dir():
        print(f"Nothing to do — {RAW_DIR} does not exist.")
        return

    if sys.argv[1:]:
        for name in sys.argv[1:]:
            remove(name)
    else:
        targets = [p for p in RAW_DIR.iterdir() if p.is_dir()]
        if not targets:
            print(f"{RAW_DIR}/ is already empty.")
            return
        print(f"This will delete {len(targets)} director(ies):")
        for t in targets:
            print(f"  {t}")
        confirm = input("Confirm? [y/N] ").strip().lower()
        if confirm == "y":
            for t in targets:
                shutil.rmtree(t)
                print(f"Removed: {t}")
        else:
            print("Aborted.")


if __name__ == "__main__":
    main()
