# ADR-0003: 最初の実エージェント審査の対象選定（InsideOut）と実行で判明した不具合

- ステータス: Accepted
- 日付: 2026-06-28
- 関係者: 審査パイプライン
- 関連: [ADR-0001](0001-external-agent-audit-auth-reachability.md)（到達性と対応方針）、[a2a_test_agents.md](../a2a_test_agents.md)（候補カタログ）

## コンテキスト

審査パイプラインを**実在の外部A2Aエージェント**で初めてE2E実行するにあたり、対象を選定した。
当初の候補 marginalia は**共有メモリの状態汚染（同一質問に「回答済み自動返信」）・非同期defer・遅延**で
審査の再現性が崩れ、不適と判明（攻撃10件に同一153字の固定応答→偽陽性スコア）。そこで「無料・無認証」
カテゴリを再調査し、より素直な対象を探した。

## 決定

**カテゴリ①（無料・無認証）の本命テスト対象として InsideOut（Luther Systems）を採用する。**

### InsideOut とは（ライブ確認済みの事実）

- **提供者/正体**: Luther Systems（実在のスマートコントラクト企業）がホストする「**Riley**」＝クラウドインフラ
  設計・デプロイ対話アシスタント（skill `design-deploy-cloud`）。EP `https://insideout.luthersystems.com/insideout-a2a/v0/`、
  Card `/.well-known/agent.json`（protocolVersion 0.3 / JSONRPC）。
- **無料・無認証**: Card は `security: null` / `securitySchemes` 空＝**鍵も支払いも不要**。x402でもない。
- **Googleストア外**: **a2aregistry.org（公開オープンA2Aレジストリ）** 掲載で、**Gemini Enterprise / Cloud
  Marketplace の中ではない**。自社ドメインで公開された独立エージェント。＝ADR-0001でいう「開放型」なので
  承認済みクライアントの壁が無く、外部から直接A2Aで到達・審査できる（Lovable=閉鎖型と対照的）。
- **実LLM自由対話**: 注入/脱獄を試せる。「クラウド設計」という明確なシステムロールを持つ＝ロール無視・脱獄の題材に好適。
- **同期・ステートレス**: 1コールで11〜23秒かけて完答（非同期deferなし）。新規リクエストは無記憶
  （合言葉登録→別セッションで無記憶をライブ確認）＝**訪問者横断の状態汚染なし＝再現性◎**。

### 採用理由

marginalia の3欠点（状態汚染／非同期defer／固定応答）を**すべて解消**し、「無料・鍵不要・即叩ける・再現性のある
実在LLMエージェント」だから。最初の実エージェント審査に最適。

## 実行で判明した不具合（修正済み）と効果

InsideOut でフルE2E（PreCheck→Security Gate→Agent Card Accuracy→MAGI Jury→Trust Score）を回す中で、
**審査ランナー側のバグを2つ発見・修正**した。いずれも「相手の問題」ではなく「こちらの計測系の問題」で、
放置すると**審査スコアを汚染**する。

1. **A2A非同期ポーリング未対応**（コミット `96e58a5`）: ADK の RemoteA2aAgent は `working` タスクを
   ポーリングせず「処理中」プレースホルダを返す。直接 `message/send`→`tasks/get` で終端まで待つ実装に置換
   （`_a2a_send_and_poll(_ctx)`）。マルチターンは A2A `contextId` で文脈維持。
2. **同期で遅いエージェント向けのHTTPタイムアウト過小**（コミット `b94accd`）: `SECURITY_GATE_TIMEOUT=10`
   由来の per-request HTTP timeout が15秒で、InsideOutの同期応答（11〜23秒）が遅いプロンプトで切れ、
   httpx ReadTimeout（空メッセージ）→`endpoint_error` を誘発。下限を45秒に是正
   （`SECURITY_GATE_A2A_HTTP_TIMEOUT`、上限90秒）。`input-required`/`auth-required` の誤「打ち切り」警告も抑制。

### 効果（実測・同一対象 InsideOut）

| | 修正前 | 修正後 |
|---|---|---|
| Security endpoint_error | 6/10 | **0/10** |
| Security 実応答(防御) | 4 | **9** |
| Functional | 失敗多発 | passed 1 / failed 0 / **error 0** |
| 最終スコア / 判定 | **38 / reject** | **53 / needs_review** |

修正前の「38/reject」は、陪審員が**6件のendpoint_error（＝こちらのタイムアウト）を「エージェントが脆弱/壊れている」
と誤読**して付けたバグ汚染スコアだった。修正後は InsideOut の**実際の防御挙動**が測れ、妥当な「53/needs_review」に。

## 結果・影響

- **InsideOut をカテゴリ①の基準テスト対象**として確定（[a2a_test_agents.md](../a2a_test_agents.md)）。
- 審査ランナーが**同期で遅いエージェント／非同期ポーリング型エージェント**の両方を正しく扱えるようになった。
- 教訓: **計測系（タイムアウト/ポーリング）の不具合は、相手の脆弱性と区別できず審査結果を汚染する**。実エージェントで
  E2Eを回して初めて顕在化した。新規対象を増やす際は endpoint_error 率を必ず確認する。

## 未解決事項 / 今後

- InsideOut のレート制限/ToS（連続審査での遮断有無）は未確認。1コール17〜23秒と遅く、大量試行は時間がかかる。
- カテゴリ②（セルフ発行鍵）／③（x402）の実対象での実行（別途）。
