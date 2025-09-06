from __future__ import annotations

import os
from importlib import import_module


def _resolve_main():
    try:
        from catalyst_bot.finviz_elite import screener_unusual_volume  # type: ignore

        def _main():
            os.getenv("FINVIZ_AUTH_TOKEN")
            rows = screener_unusual_volume()
            print(
                f"finviz_ingest: rows={len(rows)} sample={(rows[0] if rows else None)}"
            )
            return 0

        return _main
    except Exception:
        mod = import_module("finviz_ingest")
        return getattr(mod, "main")


def main():
    return _resolve_main()()


if __name__ == "__main__":
    raise SystemExit(main())
