from __future__ import annotations

import re
from typing import Any, Dict, Optional

from .models import IndexedItem
from .dictionary_loader import MatcherDef


def _attributes_match(item_attrs: Dict[str, Any], filt: Optional[Dict[str, Any]]) -> bool:
    if not filt:
        return True
    for k, v in filt.items():
        if item_attrs.get(k) != v:
            return False
    return True


def matcher_matches(item: IndexedItem, matcher: MatcherDef) -> bool:
    if not _attributes_match(item.attributes, matcher.attributes_filter):
        return False

    t = matcher.type.lower().strip()

    if t == "equals":
        if matcher.case_sensitive:
            return item.label == matcher.value
        return (item.label or "").lower() == (matcher.value or "").lower()

    if t == "regex":
        return re.search(matcher.value, item.label or "", flags=re.IGNORECASE) is not None

    if t == "codigo":
        return (item.codigo == matcher.value) or (item.label == matcher.value)

    if t == "json_path":
        return item.json_path == matcher.value

    raise ValueError(f"Matcher type no soportado: {matcher.type!r}")