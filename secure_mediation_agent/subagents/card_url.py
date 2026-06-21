"""Agent Card URL の候補生成ユーティリティ。

A2A仕様ではエージェントカードの ``url`` フィールドは RPC サービスの
エンドポイントであり、カード自身の配信場所ではない。標準的な外部エージェントは
カードをオリジン直下 (RFC 8615: ``https://host/.well-known/agent-card.json``) で
配信するが、このプラットフォーム内蔵のエージェントはパスベース
(``http://host/a2a/{name}/.well-known/agent-card.json``) で配信する。

そのため、エンドポイントURLからカードURLを導出する際は両方を候補にし、
順に試す（先頭から成功したものを採用する）。
"""

from __future__ import annotations

from urllib.parse import urlparse

WELL_KNOWN_PATH = "/.well-known/agent-card.json"


def card_url_candidates(endpoint_url: str) -> list[str]:
    """エンドポイントURLからカードURLの候補を優先順で返す。

    1. 既に完全なカードURLならそれ自体
    2. パスベース（エンドポイントのパスを保持して well-known を付与）
    3. オリジン直下（RFC 8615 準拠）
    """
    url = (endpoint_url or "").rstrip("/")
    if not url:
        return []

    if url.endswith(WELL_KNOWN_PATH):
        return [url]

    parsed = urlparse(url)
    candidates: list[str] = []

    path_based = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}{WELL_KNOWN_PATH}"
    candidates.append(path_based)

    origin_root = f"{parsed.scheme}://{parsed.netloc}{WELL_KNOWN_PATH}"
    if origin_root not in candidates:
        candidates.append(origin_root)

    return candidates
