# A2A テスト対象エージェント・カタログ（開放・自由対話型）

- 種別: リファレンス（生きたカタログ／決定ではない）
- 最終更新: 2026-06-24
- 関連: [ADR-0001](adr/0001-external-agent-audit-auth-reachability.md)（外部エージェント審査における認証到達性と対応方針）

> このドキュメントは、審査(セキュリティ評価)パイプラインと仲介エージェントのテスト対象に使える
> **開放型・自由対話型の実在A2Aエージェント**のカタログである。エージェントは増減・仕様変更するため、
> ADR（＝決定の記録）とは分離して「生きた一覧」としてここで管理する。**採用の決定**は ADR-0001 を参照。

## 選定要件

1. **開放型アクセス**: OAuth承認済みクライアント限定でない。無認証 / x402(機械が自動支払い) / セルフ発行APIキー。理想は**無料**。
2. **A2A準拠**: 公開Agent Card（無認証GET可が望ましい）、`message/send`(JSON-RPC)、preferredTransport JSONRPC。
3. **自由対話型(LLM/query応答)**: 構造化入力の実用API型ではなく自然言語で対話でき、**注入/脱獄の中身を試せるsurface**がある。
4. **公開到達可能**な実エンドポイント。できれば**実在企業/プロジェクト**。

（凡例: ✅確認済 / △疑義 / ❌不適。「確認済」＝実際に Card 取得や `message/send` をライブで叩いて確認した事実。）

## A2Aエージェントの4類型（選定の物差し）

**A2Aは「エージェント同士の通信プロトコル（封筒の形式）」を定めるだけで、封筒の中身が自然言語の対話とは限らない。**
同じ `message/send` でも、相手の「業務」によって受け付けるものが違う。だから A2A 準拠でも**自由対話できない**
エージェントは普通に存在する。「自由対話できるか」が**安全性審査の対象として使えるかの足切り条件**になる
（注入/脱獄は自然言語をLLMが解釈する余地が無いと試せないため）。実務で出会うのは概ね次の4類型:

| 類型 | 中身 | 注入/脱獄surface | 主な用途 | 例 |
|---|---|---|---|---|
| **① 自由対話型（LLM応答）** | 自然言語→LLMが解釈して返す | **あり（大）** | **安全性審査の本命** | marginalia |
| **② 構造化入力型（実用API型）** | `{skill,input}` 等の固定構造＝関数呼び出しに近い | なし（フォーマット外は弾く） | x402決済配管の検証 | AIScan / MERCURY / OptionsAhoy |
| **③ ルーティング/特化型** | 問い合わせを窓口へ振分け or 特定ドメイン特化 | 限定的 | （補助的） | PoolParty（"not free-form conversational"宣言）/ MoveHome |
| **④ スタブ（実LLM未接続）** | エコー/テンプレ返答。`upstreamConfigured:false` 等 | なし（LLMが無い） | A2Aプロトコル疎通の確認 | Aurelius |

**判別のチェックポイント**: (a) Agent Card の skill が `chat`/`query` 等の自然言語型か、`{skill,input}` の構造型か。
(b) ライブで `message/send` に自然文を投げ、**LLMらしい応答**が返るか（②③は定型、④はエコー/テンプレ）。
(c) `runtimeMode`/`upstreamConfigured` 等のメタで実LLM接続を示すか。**カード宣言だけを鵜呑みにせず必ずライブ確認**
（Aurelius はカード上「自然言語」だが実体は④だった）。

**選定への効き方**: 安全性審査＝①必須。x402決済の配管検証＝②で十分（むしろ自由対話surfaceは不要）。
プロトコル疎通の確認＝④で十分（安定・同期）。＝**1体で全部を兼ねる必要はなく、用途ごとに類型で割り当てる**
（下の役割分担表はこの物差しの適用結果）。

## 採用（役割分担）

| 用途 | 採用 |
|---|---|
| 安全性審査・仲介の本命対象 | **marginalia**（無認証・実LLM自由対話） |
| A2Aプロトコル疎通の確認 | **Aurelius**（同期・安定だが実LLM未接続のスタブ） |
| x402決済配管の検証 | **AIScan**（構造化入力・Base mainnet実費） |

---

## 最有力: marginalia（Polycode Limited）

要件1〜5をすべて満たし、**自由対話をライブで確認できた唯一の実在候補**。

| 項目 | 内容 |
|---|---|
| 提供者 | Polycode Limited（英国） |
| エンドポイント | `https://marginalia.polycode.co.uk/api/a2a` |
| Agent Card | `https://marginalia.polycode.co.uk/.well-known/agent-card.json`（無認証GET 200 ✅） |
| アクセス | apiKey(X-API-Key)は **"Optional today" / `security: []`** ＝**無認証で叩けて無料** ✅（将来 無料枠+従量へ移行予定とカード明記） |
| 自由対話 | skill `chat`(Open chat)/`recall-memory`/`research-projects`。「capital of France?」→ `"The capital of France is Paris."` をライブ確認 ✅。**注入/脱獄を試せる実LLMサーフェスあり** |
| A2A準拠 | protocolVersion `0.3.0` / preferredTransport `JSONRPC` / streaming `true`。`message/send`→`kind:"task"`(working→completed)の**非同期**応答（`tasks/get` 等でポーリング） ✅ |
| 要件充足 | 1✅ 2✅ 3✅ 4✅ 5✅ |

**実装上の注意**:
- ①応答が**非同期**＝評価ランナーに**ポーリング対応**が必要。
- ②**共有メモリグラフ**を持ち、過去訪問者(A2A含む)の発話が `memory_retrieved` に蓄積される設計＝**状態汚染**に注意（審査の再現性に影響しうる）。

## A2A形式テスト補助: Aurelius Agent（wundercorp）

| 項目 | 内容 |
|---|---|
| エンドポイント | `https://rpc.aureliusagent.dev/a2a` |
| Agent Card | `https://aureliusagent.dev/.well-known/agent-card.json`（無認証GET 200 ✅） |
| アクセス | `securitySchemes`/`security` とも空＝**完全無認証・無料** ✅ |
| 自由対話 | カード上は自然言語だが、ライブ確認で**応答がエコー/テンプレ**。`runtimeMode:"embedded-api"`, `upstreamConfigured:false`＝**実LLM未接続のスタブ** △ → **注入/脱獄評価には不適** ❌ |
| A2A準拠 | protocolVersion `0.3.0` / JSONRPC。`message/send`→`state:"completed"`+history+artifacts を**同期返却** ✅ |

→ **A2Aプロトコル準拠の機械テストに最適**（同期・即時・安定）。安全性評価には使わない切り分けが明快。

## 次点・要確認

| エージェント | 提供者 | エンドポイント | アクセス | 判定 |
|---|---|---|---|---|
| PoolParty Agent Concierge | PoolParty | `https://www.poolparty.io/api/a2a` | 無認証(read-only) / 保護MCPはBearer | カード上 "not free-form conversational"（ルーティング型）。自由対話 △。0.3.0/JSONRPC |
| MoveHome.org Property Agent | Move Home Organisation CIC | `https://movehome.org/api/a2a` | 無認証 | 物件検索特化。自由対話 限定的（未ライブ確認） |
| iwant-marketplace | iwant.fyi | `https://iwant.fyi/api/a2a` | 無認証(カード上) | カードJSON取得が不安定で**未確認** |

## 除外: 自由対話でない/無料でない（確認済）

x402対応エージェント群は概ね「Base **mainnet** で実USDC課金」かつ「構造化API型」。**testnet/無料枠の自由対話型は今回の登録一覧に見当たらず**。

| エージェント | 形式 | x402 | 除外理由 |
|---|---|---|---|
| AIScan（getaiscan.app） | 構造化スキャナ（`application/json`、18従量スキル） | Base mainnet / 0.06〜3.50 USDC | 自由対話でない・無料でない。**x402決済配管の検証には採用** |
| MERCURY Web Fetch | 単一 `web-fetch` ツール | Base mainnet / $0.003 USDC | 自由対話でない |
| aicomglobal | スキル呼び出し型（`DataPart{skill,input}`） | x402対応 | 自由対話でない |
| OptionsAhoy Equity Planner | 計算機呼び出し型（`{skill,input}`） | keyless無料 | 自由対話でない |

## 代替案（本命で不足する場合）

1. **A2A形式テストは Aurelius を併用**（同期・即時）。安全性評価には marginalia。
2. **自前デプロイ**: 実在OSSのA2Aサーバ（A2A公式サンプル等）に自社LLMバックエンドを繋いで**無認証公開**＝「制御可能な自由対話型」。再現性・安全性が最も高い。
3. **x402を試すなら**: Base **Sepolia testnet**（Circle/Alchemy フォーセット）に自前の自由対話型を立てて課金ゲートを検証（既存x402エージェントは構造化API型に偏るため）。

## 参照URL

- A2A Registry API（一次ソース）: https://a2aregistry.org/api/agents ／ トップ: https://a2aregistry.org/
- marginalia Card: https://marginalia.polycode.co.uk/.well-known/agent-card.json
- Aurelius Card: https://aureliusagent.dev/.well-known/agent-card.json
- PoolParty Card: https://www.poolparty.io/.well-known/agent-card.json
- AIScan Card: https://getaiscan.app/.well-known/agent-card.json
- MERCURY Card: https://network.mercury-hq.com/.well-known/agent-card.json
- A2A仕様: https://a2a-protocol.org/latest/specification/ ／ awesome-a2a: https://github.com/ai-boost/awesome-a2a
- x402: https://github.com/coinbase/x402 ／ https://www.alchemy.com/blog/how-x402-brings-real-time-crypto-payments-to-the-web
