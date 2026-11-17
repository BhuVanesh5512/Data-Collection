"""Deprecated: official-rate collection does not create interpolated monthly values.

The project now uses only observations explicitly published by BIS, RBI, or
another documented financial authority. This module is intentionally disabled
so annual rates are never converted into fabricated monthly observations.
"""


def main():
    raise SystemExit(
        "Disabled: estimated/interpolated monthly rates are not part of the "
        "official dataset. Run src/collect_data.py and src/verify_data.py instead."
    )


if __name__ == "__main__":
    main()
