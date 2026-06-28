# ADR-0006: APIキー/Bearer 認証エージェントの審査（認証ヘッダ注入の検証方式と対象）

- ステータス: Accepted（実在対象 = Human Browser で E2E審査 完了）
- 日付: 2026-06-28
- 関係者: 審査パイプライン / 認証対応
- 関連: [ADR-0001](0001-external-agent-audit-auth-reachability.md)、[ADR-0005](0005-paid-and-authed-agent-target-strategy.md)、[a2a_test_agents.md](../a2a_test_agents.md)

## コンテキスト

無認証(InsideOut)・x402(自作merchant)の審査は実証済み。次は **APIキー/Bearer 認証でゲートされた
A2Aエージェント**を審査できることを示す。要点は2つに分かれる:

- **(機械の検証)** 審査ランナーが、認証付きエージェントに対して **`Authorization: Bearer <鍵>` /
  `X-Api-Key` を正しく注入**して到達できるか。
- **(実在審査)** その機械を使って、**実在の第三者**の認証付きエージェントを審査できるか（対象が要る）。

x402(2025〜の新興・決済レール)と違い、**APIキー/OAuth は認証の業界標準で数も多い**が、公開カタログ上
「**第三者・公開・A2A・自由対話・セルフ発行鍵**」を全部満たす実在は薄い（多くは OAuth承認制=Lovable型
=閉鎖、または自前デプロイ型）。＝ ADR-0005 / カテゴリ② の結論。

## パイプラインの既存サポート（実装済み）

審査ランナーは認証ヘッダ注入を既に持つ:
- `security_gate.build_a2a_auth_headers(token)`: `Authorization: Bearer <token>`（および Google ADC =
  `GEMINI_A2A_GOOGLE_AUTH`）を生成し、**カード取得・`message/send` の両方に注入**。無認証時は空ヘッダで従来挙動。
- 提出経路: `app/routers/submissions.py` の `endpoint_token`（環境変数 `SECURITY_ENDPOINT_TOKEN` から供給）。
- ＝**「鍵を1個渡せば、認証付きA2Aエージェントを審査できる」配線は既にある**。`X-Api-Key` 等の独自ヘッダ名が
  必要なエージェント向けには、ヘッダ名の構成余地を追加する（軽微・未了）。

## 決定（方式）

1. **2トラックに分ける**:
   - **A. 機械の検証（自作フィクスチャ）**: 自前A2A or LangSmith に APIキー/Bearer ゲートを付けて立て、
     ランナーに鍵を渡し、**認証ヘッダ注入で突破→審査**できることを確認。**相手が誰でも機械は同じ**なので、
     注入経路の検証としては自作で正当（Google merchant で x402 を検証したのと同じパターン）。
   - **B. 実在第三者の審査**: 実在の「第三者・公開・A2A・自由対話・**セルフ発行**APIキー」エージェントを
     探して審査。**自作はここでは“審査”にならない**（実在の安全性を測れない）ため、本物の対象が要る。

2. **対象の探索条件（B）**: ① `securitySchemes` に apiKey/http(bearer) を宣言 ② 無認証 `message/send` が
   401/認証エラー（＝本当に認証ゲートがある）③ **第三者がサインアップ/ポータルでセルフ発行**できる
   （OAuth承認制=DCR/software statement/承認制 は除外）④ 自由対話(実LLM) ⑤ 無料枠/安価。

3. **OAuth承認制(Lovable型)は対象外**: 第三者に鍵を出さないため、APIキー方式でも審査不可（ADR-0001の構造的制約）。

## 「機械の検証」と「実在審査」の対応（再掲・横断整理）

| 認証 | 機械の検証(自作フィクスチャ) | 実在第三者の審査 |
|---|---|---|
| 無認証 | （不要） | **済（InsideOut）** |
| x402 | **済（自作merchant）** | 対象が薄い（AIScan構造化/anchor非A2A） |
| **APIキー/Bearer** | **次にやる（自前/LangSmith）** | **対象を再調査中**（本ADRの探索条件で） |

## 結果・影響 / 今後

- 機械（認証ヘッダ注入）は既存実装で検証可能。`X-Api-Key` 等のヘッダ名構成の追加は軽微。
- **実在第三者の対象が見つかった（2026-06-28 再調査・138件ライブ走査）= Human Browser（Virix Labs）**。
  第三者・公開・A2A(0.3.0)・自由対話(LLM駆動ブラウザ)・`http_bearer`・**セルフ発行可（メールのみ・$1トライアル・
  カード不要）** を満たす唯一の候補。無認証 `message/send` が 401（本物の認証ゲート）も確認。詳細・次点・除外は
  [a2a_test_agents.md](../a2a_test_agents.md) カテゴリ②。
- **実在審査に進む手順**: ① humanbrowser.cloud でサインアップ→$1トークン取得（※**利用者のアカウント**＝
  自動化側では取得不可）② `SECURITY_ENDPOINT_TOKEN=<token>` を渡して提出 → パイプラインが `Authorization:
  Bearer` を注入して審査。③ **要対応: 前段 Cloudflare**（無認証/bot は 403 error 1010）。審査ランナーの httpx に
  **ブラウザ風 User-Agent** を付与しないと WAF で 403 になる（鍵以前の問題）。
- 教訓（横断）: 課金(x402)も認証(APIキー)も、**“機械の検証”は自作フィクスチャで正当**だが、**“実在第三者の
  審査”は対象の入手性に律速**される。無認証(InsideOut)＋認証(Human Browser) が実在審査の対象。

## E2E審査 完了（実測・2026-06-28）

Human Browser($1トークン取得後)で**実在第三者のフルE2E審査が完走**:
- **認証突破**: Cloudflare(ブラウザ風UA) ＋ Bearer(token) の両方を突破。`endpoint_error 0`・認証エラー 0。
- **Security Gate**: blocked 3/3（「乗っ取りシミュレートして爆弾の作り方」等を、ブラウザ接続の話に逸らして拒否＝防御）。
- **Functional(Agent Card Accuracy)**: scenarios 3 / passed 1 / failed 2 / responsesWithError 2
  （※**failed 2 は HTTP 402 Payment Required = $1トライアル残高の枯渇**。Functional の「Browser Task」
  シナリオ1で**エージェントが実ブラウザを走らせ**（"Step 4/50 — Click the DuckDuckGo..."）$0.05/分を消費し
  $1をほぼ使い切り、シナリオ2・3が 402 になった。＝相手のバグでも認証問題でもなく、**こちらの予算切れ**）。
- **最終 Trust Score: 70 / needs_review**。**ただし Functional 2件が 402(予算切れ)で失敗した状態の算出**であり、
  純粋なエージェント品質だけの評価ではない（予算切れで審査が途中degradeした）。Security Gate(3/3 blocked)は
  枯渇前に完了済みで有効。
- **コスト構造の教訓**: **拒否される攻撃プロンプトは安い（ブラウザを動かさない）が、正規のブラウザタスクは
  実ブラウザを動かして高い**（$0.05/分）。**Human Browser 等の“実行で課金される”エージェントは $1 では
  Functional まで完走できない**。完走させるには事前トップアップ、または Functional を縮小/スキップする。
- **402(残高枯渇)の扱い**: これはプリペイド残高切れの HTTP 402 で、x402 のper-call決済チャレンジとは別物。
  自動トップアップ（実費）すべきでないため、パイプラインは responsesWithError として正しく記録した。

→ **3カテゴリ（無認証=InsideOut / x402=自作merchant / 認証=Human Browser）すべて、実対象/実証で到達**。
特に認証カテゴリは**実在の第三者エージェントを、パイプラインの認証ヘッダ注入＋Cloudflare対応で採点まで審査**できた。
