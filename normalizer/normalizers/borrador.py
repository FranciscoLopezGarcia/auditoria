from __future__ import annotations

from normalizer.normalizers.base import BaseNormalizer


class BorradorNormalizer(BaseNormalizer):

    def __init__(self):
        super().__init__("borrador")