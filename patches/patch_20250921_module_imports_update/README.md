This patch updates the `catalyst_bot` package `__init__.py` files to fix `ModuleNotFoundError` errors seen during
pytest.  The existing `__init__.py` defined an empty `__all__`, which prevented Python from delegating
attribute resolution to `__getattr__` when executing statements like `from catalyst_bot import alerts`.  By
removing the static `__all__` definition, the dynamic loader implemented in `__getattr__` is used for unknown
submodules, allowing imports like `from catalyst_bot import alerts, config, classify` to succeed.  The patch
also retains the compatibility shim that attaches `get_settings` to the `alerts` module for unit tests.

Files included:

- `src/catalyst_bot/__init__.py`: updated to remove the static `__all__` and add explanatory comments.
- `catalyst-bot/catalyst-bot-main/src/catalyst_bot/__init__.py`: updated similarly.
- `APPLY.ps1`: script to copy the modified `__init__.py` files into your repository.  It will also
  synchronise the canonical package into `src/catalyst_bot` if missing.

To apply this patch, run the following from a PowerShell prompt:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\APPLY.ps1 -RepoRoot C:\path\to\catalyst-bot -PatchRoot .
```

After applying, re-run `pre-commit run -a` and `pytest -q` from your repository root.  The import errors
should be resolved.