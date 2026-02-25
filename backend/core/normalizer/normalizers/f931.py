from __future__ import annotations

from .base import BaseNormalizer


class F931Normalizer(BaseNormalizer):

    def __init__(self):
        super().__init__("f931")