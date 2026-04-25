"""
Legacy entry point. The integrity check was split into:
  - check_build.py    — post-build JSON invariants
  - check_coverage.py — override-aware crawled-vs-translated coverage

This wrapper runs both so any tooling still invoking `check_data_integrity.py`
keeps working. New code should call the split scripts directly.
"""

import sys

import check_build
import check_coverage


def main():
    build_errors = check_build.check()
    cov_errors = check_coverage.check()

    if build_errors:
        print(f"\n{len(build_errors)} BUILD ERROR(S):")
        for e in build_errors:
            print(f"  {e}")
    if cov_errors:
        print(f"\n{len(cov_errors)} COVERAGE ERROR(S):")
        for e in cov_errors:
            print(f"  {e}")

    if build_errors or cov_errors:
        sys.exit(1)
    print("[check] All build + coverage checks passed.")


if __name__ == "__main__":
    main()
