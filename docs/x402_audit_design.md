# x402 課金ゲート対応の審査設計

- ステータス: Draft（feature/x402-audit）
- 日付: 2026-06-24
- 関連: ADR-0001（外部エージェント審査における認証到達性と対応方針）

## 目的

x402（HTTP 402 + オンチェーン少額決済, USDC）で課金ゲートされた**実在企業のA2Aエージェント**
（例: AIScan / Agoragentic / MERCURY）を審査対象にする。x402は**承認ゲートが無く、機械が
自動支払いできる**ため、OAuth承認制（Lovable等）と異なり**外部の独立審査基盤でも到達可能**。

## 全体フロー

```
[1] 審査パイプラインが A2A エンドポイントへ message/send
[2] エージェントが HTTP 402（Payment Required）＋x402支払い要件を返す
[3] x402ハンドラが要件を解析（amount/network/asset/payTo）
[4] 上限チェック（1回上限・累計上限・許可ネットワーク）
[5] 支払い（dry-run=送金せず記録 / live=Payerが署名・送金）→ X-PAYMENT ヘッダ生成
[6] 同リクエストを X-PAYMENT 付きで再送 → 200・実応答を取得
[7] 取得した実応答を Security Gate で評価
```

## 実装（このブランチで追加した足場）

`evaluation-runner/src/evaluation_runner/x402_payment.py`:

- `X402PaymentRequirements`: 402応答の解析結果（scheme/network/asset/amount/payTo）。
- `parse_402_response()`: 402応答の best-effort 解析（動的402チャレンジ用）。
- `parse_payment_from_card()`: **Agent Card 宣言型**の支払い要件を解析（AIScan等は
  `payment_schemes[]` ＋ スキルの `x-payment-info.price` に価格を先出しする。実AIScanカードで
  最安スキル自動選択・skill指定・dry-run記録を検証済み）。x402 v2 / network `eip155:8453`(Base)対応。
- `X402Config`: 既定は **無効（enabled=False）・dry-run・低上限**（max_per_call=0.5, max_total=5）。
- `SpendMeter`: 1回上限／累計上限／許可ネットワークを検証・計測（超過は拒否）。
- `Payer`(Protocol) / `DryRunPayer`(既定): 実署名・送金は利用者実装に委譲。dry-runは送金しない。
- `handle_payment_required()`: 上限内なら支払いヘッダを返す。dry-run/無効はNone（送金しない）。

## 安全設計（必読）

- **既定で送金しない**。`enabled=False` かつ `mode="dry_run"`。
- **live（実送金）は、利用者が `Payer`（ウォレット実装）を注入し、明示的に有効化した場合のみ**。
  Payer未注入のliveは `DisabledPayerError` で**自動送金を拒否**。
- **鍵はリポジトリに持たせない**。署名・ブロードキャストは外部のPayer実装に隔離。
- **上限メータリング**で暴発を防止。`max_per_call` / `max_total` / `allowed_networks`。
- 実運用前に **ウォレット運用・レート・規制/KYC・監査ログ** を必ずレビュー（財務行為）。

## 監査ウォレット運用（ADR-0001 の課金ゲート設計と整合）

- **プリファンド**: 監査用ウォレットに少額USDCを前入れ。
- **メータリング**: 1審査あたりの支出を計測・上限化。
- **審査リベート（任意）**: 支出を登録完了時に提供者へ請求/相殺するモデルも検討余地。

## 統合ポイント（TODO・本ブランチ未実施）

1. `security_gate.invoke_endpoint` の呼び出し経路で 402 を捕捉するフックを追加。
   - **A2A/RemoteA2aAgent 経路**: 402 が HTTP 層で出るか、A2Aタスクの payment-required 状態で
     出るか、x402拡張の流儀を**実機（AIScan等）で確認**してから配線する。
   - **legacy/直POST 経路**: HTTP 402 を直接捕捉しやすいので、まずこちらで疎通検証。
2. `parse_402_response()` を**実機の402応答**に合わせて確定。
3. `X402Config` を `.env`（`X402_ENABLED` / `X402_MODE` / `X402_MAX_PER_CALL` / `X402_MAX_TOTAL`）から構成。
4. 実 `Payer` 実装（x402 SDK / Coinbase CDP 等）を別モジュールに隔離して注入。

## 検証段取り

1. **dry-run で配管**: 402検出→解析→上限チェック→「未払いのため未実行」を審査結果に記録、まで。
2. **テストネット（base-sepolia）＋少額**で live を限定検証（実送金の最小確認）。
3. 問題なければ本番ネットワークで**上限を低く**して実審査。

## 未解決事項

- 実機の x402 / A2A x402拡張の正確な応答・再送フロー（要実機検証）。
- Payer 実装の選定（x402公式SDK / CDP / 自前署名）と鍵管理（KMS/Secret Manager）。
- 規制・会計・税務（少額とはいえオンチェーン送金の扱い）。
