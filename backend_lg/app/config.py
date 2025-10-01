import os
from typing import Iterable, Optional


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def load_params_from_md(path: Optional[str] = None, *, reserved_keys: Iterable[str] = ("GEMINI_API_KEY", "EXA_API_KEY")) -> int:
    """Load non-secret parameters from params.md into os.environ.

    - Lines must be KEY=VALUE; keys must be UPPERCASE
    - Trailing inline comments after '#' are stripped
    - Quoted values are unquoted
    - API keys (reserved_keys and *_API_KEY) are ignored here on purpose
    Returns number of variables set.
    """
    p = path or os.path.join(_repo_root(), "params.md")
    try:
        count = 0
        with open(p, "r", encoding="utf-8") as f:
            for raw_line in f:
                s = raw_line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                k = k.strip()
                if not k or not k.isupper():
                    continue
                if k in reserved_keys or k.endswith("_API_KEY"):
                    continue
                v = v.strip()
                if "#" in v:
                    v = v.split("#", 1)[0].strip()
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                os.environ[k] = v
                count += 1
        return count
    except Exception:
        return 0


def _overrides_path() -> str:
    return os.path.join(_repo_root(), "params.override.json")


def load_overrides_from_json(path: Optional[str] = None, *, reserved_keys: Iterable[str] = ("GEMINI_API_KEY", "EXA_API_KEY")) -> int:
    p = path or _overrides_path()
    try:
        import json
        if not os.path.exists(p):
            return 0
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        count = 0
        for k, v in (data.items() if isinstance(data, dict) else []):
            if not isinstance(k, str) or not k.isupper():
                continue
            if k in reserved_keys or k.endswith("_API_KEY"):
                continue
            os.environ[k] = str(v)
            count += 1
        return count
    except Exception:
        return 0


def save_overrides_to_json(values: dict) -> None:
    try:
        import json
        path = _overrides_path()
        existing = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = (json.load(f) or {}) if f else {}
            except Exception:
                existing = {}
        if not isinstance(existing, dict):
            existing = {}
        # merge
        for k, v in (values.items() if isinstance(values, dict) else []):
            existing[k] = v
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass


