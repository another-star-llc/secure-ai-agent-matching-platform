# x402 課金ゲート対応の審査設計

- ステータス: Draft（feature/x402-audit）
- 日付: 2026-06-24（前提知識セクション追記: 2026-06-28）
- 関連: ADR-0001（外部エージェント審査における認証到達性と対応方針）、[a2a_test_agents.md](a2a_test_agents.md)

## 目的

x402（HTTP 402 + オンチェーン少額決済, USDC）で課金ゲートされた**実在企業のA2Aエージェント**
（例: AIScan / Agoragentic / MERCURY）を審査対象にする。x402は**承認ゲートが無く、機械が
自動支払いできる**ため、OAuth承認制（Lovable等）と異なり**外部の独立審査基盤でも到達可能**。

## 前提知識（x402を動かす前に知っておくこと）

### ブロックチェーン用語

- **Base**: Coinbase が運営する Ethereum L2（Layer 2）ブロックチェーン（OP Stack系）。x402のUSDC決済はこの上で行う。
- **mainnet（本番）** = `eip155:8453`。**本物のUSDC（実際のお金）**が動く。実費が発生する。
- **testnet（テストネット）= Base Sepolia** = `eip155:84532`。Ethereumのテスト用ネットワーク「Sepolia」上のBase版。
  - **トークンに金銭的価値が無い**。開発・検証専用。
  - テスト用USDC/ETHは **フォーセット(faucet)から無料でもらえる**（Circle / Alchemy 等が配布）。
  - → **本物のお金を一切使わず**に、x402の決済フロー（402応答→支払い→再送→200）を丸ごと通せる。x402配管検証の定石。
- **USDC**: 米ドル連動のステーブルコイン。x402の支払い通貨。
- **ウォレット**: USDC送金に署名するための秘密鍵を持つアカウント。自己管理(MetaMask/プログラム鍵)でも、マネージド(Coinbase CDP のサーバウォレット等)でもよい。

### クレジットカードは不要・必要なのはウォレット

x402は**オンチェーンのUSDC決済**であり、**クレジットカードは使わない**。秘密鍵でUSDC送金に署名する。
必要なものは段階で変わる:

| 段階 | 必要なもの | クレカ | ウォレット | 実費 |
|---|---|---|---|---|
| **dry-run（既定）** | 何も不要（「払うはず」を記録のみ） | 不要 | 不要 | ¥0 |
| **mock facilitator** | オンチェーンすら不要（配管だけ通す） | 不要 | 不要 | ¥0 |
| **testnet（Base Sepolia）** | テストネット用ウォレット＋faucetの無料テストUSDC | **不要** | 要（テスト用） | **¥0** |
| **mainnet（本番）** | 本物のUSDCを入れたウォレット | 不要※ | 要 | 実費 |

※ x402自体はカード非対応。ただし「本物のUSDCをウォレットに入れる」過程で取引所/オンランプ（≒KYC、場合により銀行/カード）が絡むことはある。これはx402の要件ではなく**暗号資産を入手する一般手順**の話。

→ **まず dry-run / mock で無料検証 → testnet（無料ウォレット＋faucet）で実決済フロー → 本番USDCはmainnetの最終段階だけ**。
本リポジトリの実装は**既定 dry-run・送金しない**設計（[x402_payment.py](../trusted_agent_store/evaluation-runner/src/evaluation_runner/x402_payment.py)）なので、**ウォレット無しで配管検証から始められる**。

### 「merchantのシステムプロンプトを審査対象に差し替える」とは

Google公式の `a2a-x402` デモ（[a2a_test_agents.md](a2a_test_agents.md) カテゴリ③の本命）には **「merchant（店）役のエージェント」**があり、
中身は **Gemini（LLM）＋システムプロンプト**で「商品を売る店員」を演じている（x402決済フローを見せるためのデモ）。

merchant は**“ただのLLM＋差し替え可能なシステムプロンプト”**なので:
- そのシステムプロンプトを、**審査したいエージェントのプロンプト**（任意の役・試したい振る舞い）に**置き換える**。
- すると **x402決済ゲートはそのまま**（＝決済配管を検証できる）／**LLMの中身は審査対象の振る舞い**になる（＝注入/脱獄の**中身審査**ができる）。
- ＝**1つのデモで「決済配管(A2A+x402)」と「中身の安全性審査」を両方**試せる。

注意: これは**自分が設定したプロンプトのLLM**を審査するので、第三者の実エージェントそのものではない。
「自前の審査対象を、x402ゲート越しに、testnetで審査できる」＝**パイプラインの能力検証用**という位置づけ。

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
