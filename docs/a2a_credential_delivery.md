# A2Aエージェントにおける認証鍵の配布方式

調査日: 2026-06-18
対象: Trusted Agent Store 審査パイプラインで外部A2Aエージェントを評価する際の、認証鍵（クレデンシャル）の受け渡し設計

## 0. 結論（要点）

- **Agent Card に鍵そのものは載らない**。A2A仕様は「秘密情報をカードに埋め込まず、out-of-band（別経路）の動的クレデンシャルを使う」ことを強く推奨している。
- Agent Card が持つのは **「どの認証方式か（securitySchemes）」と「必要な権限（security / scope）」の宣言のみ**。実際の鍵は別チャネルで取得し、呼び出し時にHTTPヘッダ等で提示する。
- したがって **Agent Card が流出しても鍵は漏れない**（仕様を守っている限り）。リスクはエンドポイント/能力の偵察と、規約違反でカードに鍵直書きした場合に限られる。

出典: [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/) / [Agent Discovery](https://a2a-protocol.org/dev/topics/agent-discovery/)

---

## 1. 全体フロー

```
[1] Discovery   クライアントが /.well-known/agent-card.json を「無認証」で取得
                 → securitySchemes（Bearer / OAuth2 / apiKey 等）を読む
[2] 鍵の取得    宣言された方式に応じて “別経路” でクレデンシャルを入手
                 （OAuth同意フロー / 開発者ポータル発行 / クラウドIAM）
[3] 呼び出し    取得した動的トークンを Authorization ヘッダ等に載せて message/send
[4] 失効/更新   短命トークンは期限切れ後に再取得（リフレッシュ/再発行）
```

ポイント: **[1]だけは無認証で読める**。これは「この扉はOAuthですよ／Bearerですよ」という案内板の役割。鍵は[2]で初めて、カードとは別の経路から入手する。

---

## 2. 方式別の鍵配布

### 2-1. OAuth2（推奨・最も一般的）

- Agent Card には認可サーバのURL・token URL・scope のみ記載。
- クライアント（またはユーザー）が認可サーバへリダイレクト → **ユーザーがログイン・同意** → **短命のアクセストークン**が発行される。
- トークンはカードを通らず、各呼び出しで `Authorization: Bearer <token>` として送る。
- 期限切れ時はリフレッシュトークンで更新。

用途: 企業向け（Agentforce, Microsoft Copilot, Gemini Enterprise 等）。ユーザー単位の権限・監査が必要なケース。

### 2-2. APIキー / Bearer 静的トークン

- 提供者の **開発者ポータル / 管理コンソールでキーを事前発行**してもらう（out-of-band）。
- クライアントは `Authorization: Bearer <key>` または独自ヘッダ（`x-api-key` 等）で送る。
- 審査運用では **本番キーではなく「review用の使い捨てキー（スコープ・期限限定）」**を出させるのが安全。

用途: 開発者向けSaaSエージェント、サンドボックス。

### 2-3. クラウドIAM（AWS SigV4 等）

- AWS Bedrock AgentCore のように、エンドポイントが **IAM/SigV4署名**で保護される。
- 鍵＝**IAMロール/一時クレデンシャル（STS）**。クロスアカウントの場合はリソースベースポリシーで監査側アカウントに権限付与。
- 呼び出しは SigV4 署名付きリクエスト（`InvokeAgentRuntime` 等）。

用途: AWS上にデプロイされたA2Aエージェントの審査。

### 2-4. x402（オンチェーン決済 / 鍵ではなく支払い）

- 認証ではなく**課金ゲート**。鍵の代わりに**呼び出しごとにUSDC少額決済**で通過する。
- A2A x402拡張がHTTP 402に応答して支払う。AP2が支払いの承認ルール（上限・用途）を司る。
- 審査側は「プリファンド済み監査ウォレット＋支出上限（メータリング）＋審査リベートで回収」で対応（別設計メモ参照）。

出典: [Coinbase: AP2 + x402](https://www.coinbase.com/developer-platform/discover/launches/google_x402)

---

## 3. 審査パイプラインへの実装上の含意

| 項目 | 設計反映 |
|---|---|
| Credential Vault | 提出時に預かる鍵をKMS暗号化、評価中だけ復号、終了後破棄、ログにマスキング |
| PreCheckの追加検査 | **Agent Card内に鍵らしき文字列（高エントロピー値/`secret`/`token`等）が無いか**を検査し、あれば減点・差し戻し |
| 署名検証 | A2A v1.2 の署名付きAgent Card（ドメイン検証）を検証し、偽カードを排除 |
| 方式判定 | `securitySchemes` を読み、OAuth2/apiKey/IAM/x402 のどれかを自動判別して接続戦略を切替 |
| エンドポイント保護前提 | 監査時に渡される鍵は「監査専用・最小スコープ・短命」を必須とする運用ルール |

---

## 4. セキュリティ注記（カード流出時の影響）

- カードは公開前提のメタデータ。流出しても鍵は出ない。
- ただし **(a) エンドポイントURL・能力一覧の偵察、(b) 開発者が規約違反で鍵を直書きしていた場合の漏洩、(c) 静的コピー運用での署名・鮮度検証の欠落** が現実的リスク。
- 対策: 署名付きカードの使用、カードに秘密を入れない徹底、エンドポイントの認証必須化、PreCheckでの鍵直書き検査。

出典: [A2A Protocol Security](https://a2a-protocol.org/latest/specification/)
