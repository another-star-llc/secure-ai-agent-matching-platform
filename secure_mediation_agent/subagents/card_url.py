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

# A2A仕様ではカードのファイル名がバージョンで異なる。
# - 0.3 系: ``/.well-known/agent-card.json``
# - 0.2 系（InsideOut 等の実エージェントで現役）: ``/.well-known/agent.json``
# 両方を候補に含めないと、片方しか配信しないエージェントのカードに辿り着けない。
WELL_KNOWN_PATHS = ("/.well-known/agent-card.json", "/.well-known/agent.json")
# 後方互換: 旧定数名を参照している箇所のために残す
WELL_KNOWN_PATH = WELL_KNOWN_PATHS[0]


def card_url_candidates(endpoint_url: str) -> list[str]:
    """エンドポイントURLからカードURLの候補を優先順で返す。

    1. 既に完全なカードURLならそれ自体
    2. パスベース（エンドポイントのパスを保持して well-known を付与）
    3. オリジン直下（RFC 8615 準拠）

    各段で ``agent-card.json``（0.3）と ``agent.json``（0.2）の両ファイル名を試す。
    """
    url = (endpoint_url or "").rstrip("/")
    if not url:
        return []

    if url.endswith(WELL_KNOWN_PATHS):
        return [url]

    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    candidates: list[str] = []

    for well_known in WELL_KNOWN_PATHS:
        path_based = f"{parsed.scheme}://{parsed.netloc}{path}{well_known}"
        if path_based not in candidates:
            candidates.append(path_based)
    for well_known in WELL_KNOWN_PATHS:
        origin_root = f"{parsed.scheme}://{parsed.netloc}{well_known}"
        if origin_root not in candidates:
            candidates.append(origin_root)

    return candidates
