from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ApprovalPaths:
    analyzer_dir: Path
    pending_path: Path
    approved_dir: Path


def _paths() -> ApprovalPaths:
    analyzer_dir = Path("data") / "analyzer"
    analyzer_dir.mkdir(parents=True, exist_ok=True)
    pending_path = analyzer_dir / "pending.json"
    approved_dir = Path(os.getenv("APPROVAL_DIR", "out/approvals"))
    approved_dir.mkdir(parents=True, exist_ok=True)
    return ApprovalPaths(analyzer_dir, pending_path, approved_dir)


def write_pending_plan(plan: Dict[str, Any], plan_id: str) -> Path:
    """
    Persist a pending analyzer plan for human approval.
    """
    p = _paths()
    payload = {"planId": plan_id, "plan": plan}
    p.pending_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p.pending_path


def get_pending_plan() -> Optional[Dict[str, Any]]:
    """
    Return pending plan payload if exists, else None.
    """
    p = _paths()
    if not p.pending_path.exists():
        return None
    try:
        return json.loads(p.pending_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_approved(plan_id: str) -> bool:
    """
    Consider the plan approved if a file `out/approvals/<planId>.approved` exists.
    """
    p = _paths()
    marker = p.approved_dir / f"{plan_id}.approved"
    return marker.exists()


def promote_if_approved() -> Optional[Path]:
    """
    If a pending plan exists and has been approved, promote it to keyword_stats.json.
    Returns the path to the promoted file if promotion occurred.
    """
    p = _paths()
    payload = get_pending_plan()
    if not payload:
        return None
    plan_id = str(payload.get("planId") or "").strip()
    if not plan_id or not is_approved(plan_id):
        return None
    plan = payload.get("plan") or {}
    target = p.analyzer_dir / "keyword_stats.json"
    try:
        target.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        # Clear pending after promotion
        try:
            p.pending_path.unlink(missing_ok=True)  # py3.8+: ok param
        except TypeError:
            # Py < 3.8 compatibility if needed
            if p.pending_path.exists():
                p.pending_path.unlink()
        return target
    except Exception:
        return None
