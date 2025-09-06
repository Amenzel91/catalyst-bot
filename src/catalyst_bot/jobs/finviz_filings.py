from __future__ import annotations

import os
from importlib import import_module


def _resolve_main():
    # Prefer packaged helper
    try:
        from catalyst_bot.finviz_elite import export_latest_filings  # type: ignore

        def _main():
            tok = os.getenv("FINVIZ_AUTH_TOKEN")
            rows = export_latest_filings(auth=tok)
            print(
                f"finviz_filings: rows={len(rows)} sample={(rows[0] if rows else None)}"
            )
            return 0

        return _main
    except Exception:
        # Fallback to a top-level module named 'finviz_filings' if present
        mod = import_module("finviz_filings")
        return getattr(mod, "main")


def main():
    return _resolve_main()()


if __name__ == "__main__":
    raise SystemExit(main())
