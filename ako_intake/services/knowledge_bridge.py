"""M05 Knowledge Bridge：术语表只读索引 + 可选 RAG 查询。"""

from __future__ import annotations

from typing import Dict, List

import httpx

from ako_intake.config import TermEntry


class KnowledgeBridge:
    """知识桥：本地术语索引优先，远程知识库可选。"""

    def __init__(self, terms: List[TermEntry], base_url: str = "", enabled: bool = False) -> None:
        self._index: Dict[str, TermEntry] = {entry.term: entry for entry in terms}
        self._cache: Dict[str, List[TermEntry]] = {}
        self.base_url = base_url
        self.enabled = enabled

    def resolve_term(self, text: str) -> List[TermEntry]:
        """按文本命中术语表（含缓存）。"""
        if text in self._cache:
            return self._cache[text]
        hits = [entry for term, entry in self._index.items() if term and term in text]
        self._cache[text] = hits
        return hits

    def remote_query(self, query: str) -> List[TermEntry]:
        """远程知识库检索（网络失败返回空）。"""
        if not self.enabled or not self.base_url:
            return []
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(
                    f"{self.base_url.rstrip('/')}/search", params={"q": query}
                )
                response.raise_for_status()
                data = response.json()
            return [TermEntry(term=item["term"], module=item["module"], actions=item.get("actions", [])) for item in data]
        except Exception:
            return []

