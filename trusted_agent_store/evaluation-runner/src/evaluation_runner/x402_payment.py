"""x402（HTTP 402 / オンチェーン少額決済）対応の審査用スキャフォールド。

目的:
  x402 で課金ゲートされた実在A2Aエージェント（AIScan / Agoragentic / MERCURY 等）を
  審査対象にできるよう、HTTP 402（Payment Required）を検出・解析し、上限管理のうえで
  支払いヘッダを構築する仕組みを提供する。

安全設計（重要）:
  - **既定は無効（enabled=False）かつ dry-run**。実際の送金は一切行わない。
  - 実決済（live）は、利用者が **自前のウォレット実装（Payer）を明示的に注入し、
    かつ enabled=True / mode="live" を設定** した場合のみ有効。
  - すべての支払いは **1回あたり上限（max_per_call）と累計上限（max_total）** で
    メータリングされ、超過は拒否される。
  - 本モジュールは送金を「計画・計測・委譲」するのみで、**鍵管理や署名・ブロードキャストは
    利用者が用意する Payer に委ねる**（このリポジトリにウォレット鍵を持たせない）。

注意:
  実際のオンチェーン送金は財務行為である。live 運用前に、ウォレット、上限、レート、
  対象ネットワーク、規制・KYC、監査ログを必ずレビューすること。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, Protocol, Sequence

logger = logging.getLogger(__name__)


@dataclass
class X402PaymentRequirements:
    """402 応答から解析した支払い要件（x402 / A2A x402 拡張）。"""

    scheme: str                      # 例: "exact"
    network: str                     # 例: "base", "base-sepolia"
    asset: str                       # 例: USDC のコントラクトアドレス or シンボル
    amount: Decimal                  # 必要額（asset 単位）
    pay_to: str                      # 受取先アドレス
    resource: Optional[str] = None   # 対象リソースURI
    description: Optional[str] = None
    raw: Optional[dict] = None       # 元の生データ（監査用）


@dataclass
class X402Config:
    """x402 支払いの挙動設定。既定は安全（無効・dry-run・低上限）。"""

    enabled: bool = False                       # 既定: 無効
    mode: str = "dry_run"                        # "dry_run" | "live"（liveは要Payer注入）
    max_per_call: Decimal = Decimal("0.50")     # 1回あたり上限（USD相当）
    max_total: Decimal = Decimal("5.00")        # 審査セッション累計上限
    allowed_networks: Sequence[str] = field(
        # CAIP-2 形式（eip155:8453=Base本番, eip155:84532=Base Sepolia）と別名を許可。
        # 注意: 本番ネットワークでの live 送金は、上限を低く設定し意図的に有効化すること。
        default_factory=lambda: (
            "eip155:8453", "eip155:84532", "base", "base-sepolia",
        )
    )

    def is_live(self) -> bool:
        return self.enabled and self.mode == "live"


class SpendMeter:
    """支払い累計を計測し、上限超過を拒否するメーター。"""

    def __init__(self, config: X402Config) -> None:
        self._config = config
        self._total = Decimal("0")
        self.records: list[dict] = []

    @property
    def total(self) -> Decimal:
        return self._total

    def check(self, req: X402PaymentRequirements) -> None:
        """上限・ネットワークを検証。違反時は ValueError を送出（＝支払いしない）。"""
        if req.network not in self._config.allowed_networks:
            raise ValueError(
                f"x402: 許可されていないネットワーク {req.network!r}"
                f"（許可: {list(self._config.allowed_networks)}）"
            )
        if req.amount > self._config.max_per_call:
            raise ValueError(
                f"x402: 1回上限超過 {req.amount} > {self._config.max_per_call}"
            )
        if self._total + req.amount > self._config.max_total:
            raise ValueError(
                f"x402: 累計上限超過 {self._total + req.amount} > {self._config.max_total}"
            )

    def record(self, req: X402PaymentRequirements, executed: bool) -> None:
        self._total += req.amount
        self.records.append(
            {
                "amount": str(req.amount),
                "network": req.network,
                "pay_to": req.pay_to,
                "executed": executed,
                "running_total": str(self._total),
            }
        )


class Payer(Protocol):
    """支払い実行インターフェース。実装は利用者が用意（ウォレット・署名）。

    create_payment は x402 の ``X-PAYMENT`` ヘッダ値（署名済みペイロード）を返す。
    """

    def create_payment(self, req: X402PaymentRequirements) -> str:  # pragma: no cover
        ...


class DryRunPayer:
    """既定の安全な Payer。送金せず、支払い内容をログするだけ。"""

    def create_payment(self, req: X402PaymentRequirements) -> str:
        logger.warning(
            "[x402 dry-run] 支払いはスキップ（送金なし）: amount=%s network=%s pay_to=%s",
            req.amount, req.network, req.pay_to,
        )
        # dry-run では実ヘッダを返さない（呼び出し側は「支払わなかった」として扱う）
        return ""


class DisabledPayerError(RuntimeError):
    pass


def parse_402_response(status_code: int, headers: dict, body: object) -> Optional[X402PaymentRequirements]:
    """HTTP 402 応答から x402 支払い要件を解析する。

    x402 の応答形式（ヘッダ ``WWW-Authenticate`` / JSON body の ``accepts`` 等）は
    実装差があるため、ここでは代表的な JSON body 形を best-effort で解釈する。
    実エージェントの応答に合わせて拡張すること（TODO: 実機レスポンスで検証）。
    """
    if status_code != 402:
        return None
    try:
        data = body if isinstance(body, dict) else None
        if not data:
            return None
        # x402 仕様: body.accepts[] に支払い選択肢が入る想定
        accepts = data.get("accepts") or data.get("paymentRequirements") or []
        if isinstance(accepts, dict):
            accepts = [accepts]
        if not accepts:
            return None
        a = accepts[0]
        return X402PaymentRequirements(
            scheme=str(a.get("scheme", "exact")),
            network=str(a.get("network", "")),
            asset=str(a.get("asset", "")),
            amount=Decimal(str(a.get("maxAmountRequired") or a.get("amount") or "0")),
            pay_to=str(a.get("payTo") or a.get("pay_to") or ""),
            resource=a.get("resource"),
            description=a.get("description"),
            raw=data,
        )
    except Exception as exc:  # pragma: no cover - 応答形式は環境依存
        logger.warning("x402: 402応答の解析に失敗: %s", exc)
        return None


def parse_payment_from_card(
    card: dict, skill_id: Optional[str] = None
) -> Optional[X402PaymentRequirements]:
    """Agent Card に宣言された x402 支払い要件を解析する。

    AIScan 等は HTTP 402 を待たず、カードに価格を先出しする:
      - トップレベル ``payment_schemes[]``: network / asset / payTo / protocol。
      - スキルごとの ``skills[].x-payment-info``: price.amount / price.currency。

    skill_id を指定するとそのスキルの価格を採用。未指定なら最安スキルを採る。
    """
    try:
        schemes = card.get("payment_schemes") or []
        x402 = next((s for s in schemes if str(s.get("protocol", "")).lower() == "x402"), None)
        if not x402:
            return None

        # スキル価格の決定
        skills = card.get("skills") or []
        chosen = None
        if skill_id:
            chosen = next((s for s in skills if s.get("id") == skill_id), None)
        if chosen is None:
            # 最安の有料スキルを選ぶ（配管検証用）
            priced = [
                s for s in skills
                if (s.get("x-payment-info") or {}).get("price", {}).get("amount")
            ]
            chosen = min(
                priced,
                key=lambda s: Decimal(str(s["x-payment-info"]["price"]["amount"])),
                default=None,
            )
        amount = Decimal("0")
        if chosen:
            amount = Decimal(str(chosen["x-payment-info"]["price"]["amount"]))

        return X402PaymentRequirements(
            scheme=str((x402.get("flows") or ["exact"])[0]).split()[0],
            network=str(x402.get("network", "")),
            asset=str(x402.get("asset", x402.get("currency", ""))),
            amount=amount,
            pay_to=str(x402.get("payTo") or x402.get("pay_to") or ""),
            resource=(chosen or {}).get("x-payment-info", {}).get("endpoint"),
            description=(chosen or {}).get("name"),
            raw={"payment_scheme": x402, "skill": chosen},
        )
    except Exception as exc:  # pragma: no cover - カード形式は環境依存
        logger.warning("x402: カードからの支払い要件解析に失敗: %s", exc)
        return None


def handle_payment_required(
    req: X402PaymentRequirements,
    config: X402Config,
    meter: SpendMeter,
    payer: Optional[Payer] = None,
) -> Optional[str]:
    """402 を受けて、上限内であれば支払いヘッダ（X-PAYMENT 値）を返す。

    戻り値:
      - dry-run / 無効時: None（＝支払わない。呼び出し側は審査結果に
        「課金ゲートにより未実行」と記録する）。
      - live かつ Payer 注入時: 署名済み支払いヘッダ文字列。

    例外:
      - 上限/ネットワーク違反: ValueError（支払いしない）。
      - live なのに Payer 未注入: DisabledPayerError。
    """
    meter.check(req)  # 上限超過なら ValueError

    if not config.is_live():
        # 既定の安全経路: dry-run（送金しない）
        used = payer or DryRunPayer()
        used.create_payment(req)  # ログのみ
        meter.record(req, executed=False)
        return None

    # live 経路: 利用者が Payer を明示注入していなければ拒否（自動で勝手に送金しない）
    if payer is None:
        raise DisabledPayerError(
            "x402 live モードだが Payer（ウォレット実装）が注入されていない。"
            "実決済には利用者が Payer を用意し、上限・規制・監査を確認すること。"
        )
    header = payer.create_payment(req)
    meter.record(req, executed=True)
    return header


def x402_config_from_env() -> X402Config:
    """環境変数から X402Config を構成する（既定は安全: 無効・dry-run）。

    - X402_ENABLED: "true"/"1"/"yes" で有効化（既定 False）
    - X402_MODE: "dry_run"（既定）/ "live"
    - X402_MAX_PER_CALL / X402_MAX_TOTAL: 上限（USD相当, 文字列で指定可）
    """
    def _truthy(v: str) -> bool:
        return v.strip().lower() in ("1", "true", "yes")

    cfg = X402Config(
        enabled=_truthy(os.environ.get("X402_ENABLED", "")),
        mode=os.environ.get("X402_MODE", "dry_run").strip() or "dry_run",
    )
    mpc = os.environ.get("X402_MAX_PER_CALL")
    mt = os.environ.get("X402_MAX_TOTAL")
    if mpc:
        cfg.max_per_call = Decimal(str(mpc))
    if mt:
        cfg.max_total = Decimal(str(mt))
    return cfg


# プロセス共有のメーター（審査セッション全体で累計上限を効かせる）
_PROCESS_METER: Optional[SpendMeter] = None


def get_process_meter(config: Optional[X402Config] = None) -> SpendMeter:
    """プロセス共有の SpendMeter を返す（無ければ生成）。"""
    global _PROCESS_METER
    if _PROCESS_METER is None:
        _PROCESS_METER = SpendMeter(config or x402_config_from_env())
    return _PROCESS_METER
