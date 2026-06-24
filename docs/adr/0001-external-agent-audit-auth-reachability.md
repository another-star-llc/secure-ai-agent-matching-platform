# ADR-0001: 外部エージェント審査における認証到達性と対応方針

- ステータス: Accepted
- 日付: 2026-06-24
- 関係者: 審査パイプライン / 仲介エージェント開発
- 関連コミット: `e07d944`（認証付きA2A審査対応とCloud Runデプロイ改善）、
  本ADRと同時の `security_gate.py` A2A検出強化

## コンテキスト

Trusted Agent Store の審査パイプラインは、A2A（Agent2Agent）プロトコルの
Agent Card URL を入力に取り、カードから A2A エンドポイントを取得し、
`message/send`（JSON-RPC）で攻撃プロンプト等を送って防御力を評価する。

自社デプロイのモックエージェント審査は実証済み。**次フェーズの要件は「実在企業の
外部エージェント（Google Cloud Marketplace 等で配布される本物のA2Aエージェント）を
審査すること」**である。本ADRは、その実現可能性を調査した結果と、採用する方針を記録する。

### 調査で判明した事実

1. **審査の前提**: 審査できる対象は「HTTPで到達できるA2Aエンドポイント＋取得可能な
   Agent Card」を持つものに限られる。

2. **到達性のティア**（外部から叩けるか）:
   - 無記名で到達可: 公開A2Aレジストリ（a2aregistry.org 等）、自前デプロイ/OSS。
   - 資格情報があれば到達可: AWS Bedrock AgentCore（IAM/SigV4）。
   - そのままは不可: **Gemini Enterprise（Agent Engine）は公開Agent Cardを配信せず、
     エンドポイントもGoogle認証の裏側**。Gallery登録はJSON静的コピー。

3. **Marketplaceエージェントの認証**: パートナー製A2Aエージェントは、A2Aカードの
   `securitySchemes` に従い OAuth2 / IAM / APIキー 等で保護される。実機（Lovable Agent）で
   確認した結果:
   - Agent Card は公開（無認証GETで取得可、`protocolVersion:1.0`、`preferredTransport:JSONRPC`）。
   - `message/send` は到達するが、無認証では A2A タスクが `state: failed`、
     応答「Authentication required: missing software statement.」を返す（＝良い防御姿勢）。
   - 認証方式は **OAuth2（lovable.dev）＋動的クライアント登録(DCR, RFC7591)**。
     DCRには **Google Cloud Marketplace 発行の software statement（署名付きJWT）** が必要。

4. **DCR software statement の入手可否（外部第三者）**: 公式ドキュメントを精査した結果、
   - 買い手向けの認証は **Gemini Enterprise コンソールのウィザード内に閉じており**、
     外部から software statement を取得する公開APIは見当たらない（Preview機能）。
   - パートナー向け技術統合は Partner Procurement API / Pub/Sub（調達・課金）が中心で、
     **第三者向けの software statement 発行手段は提供されていない**。
   - カードが指す `setup-dcr` URLは 404（拡張の名前空間識別子で実ページではない）。
   - **結論: 外部の独立した審査基盤が software statement を入手し、プログラムでDCRを
     実行する公開された手段は現状存在しない（GE/Agentspaceの第一者処理）。**

5. **Lovable 固有の制約**: Lovable公式ドキュメントに「OAuthは承認済みクライアント
   （assistant/editor 等）のみ対応、それ以外のMCPクライアントは現時点でOAuthフローを
   完了できない」と明記。**＝独立した審査パイプラインには client_id を発行・許可しない。**

### OAuth 2層モデル（なぜローカルでも不可か）

- 層A: クライアント登録（client_id 取得）= DCR or 提供者の開発者ポータル。
- 層B: 認可（access/refresh token 取得）= authorization_code（初回のみブラウザ同意）。

層Bは層Aさえ済めばローカルでも実行可能（localhostリダイレクト＋同意、以降はrefresh）。
しかし **Lovable は層A（client_id 取得）が第三者に閉じている**ため、ローカル/デプロイの
別に関わらずトークンを取得できない。**ブロック要因はネットワークの場所ではなく認可（層A）**。

### 「Marketplaceに登録すれば相互通信できる」が成立しない理由（役割の分離）

A2A/Marketplace には2つの役割があり、認可は別物である:

- **被呼出側（出品者/callee）**: 自分のエージェントを公開・登録する＝**他者から呼ばれる対象**になる。
  これにより得られるのは Partner Procurement API / Pub/Sub 等の**調達・課金統合**であり、
  「他のエージェントを呼ぶ権利」ではない。
- **呼出側（クライアント/caller）**: 他のエージェントを**呼ぶ**には、相手のOAuthに
  **承認されたクライアント**である（software statement や承認済みclient_idを持つ）必要がある。

したがって **Marketplace に出品しても「呼ばれる側」になるだけで、他の出品エージェント
（Lovable等）を呼ぶ力は得られない**。「審査エージェントを公開・登録すれば外部から
他者を叩ける」という発想は成立しない（呼出側の認可が別途必要、かつ攻撃プロンプトの
ファジングを他社へ送る行為は各社ToSに抵触しやすい）。

### エージェント連携は「ハブ（GE/Agentspace）」が成立させている

GE上で複数エージェントが連携できるのは、**GEというハブが各エージェントのトークンを
保持してオーケストレーションし、ユーザーが調達・同意した範囲にスコープして仲介**するため。
**ピアツーピアで誰でも誰でも呼べる開放網ではない。**
- 自社の**仲介エージェントをGEに公開**するのは正当なプロダクト路で、**GEの文脈内でなら**
  GEのオーケストレーションを通じて他エージェントと連携できる（GEがトークンを扱う）。
- ただしこれは「GEの中で動く仲介」であり、**外部の独立した審査パイプラインが任意の
  エージェントを叩く力を得るわけではない**（トークンは生で手に入らずGE経由でしか効かない）。

### 未確認の論点: 出品者ステータスに「呼出クライアント権限」が含まれるか

現状、出品者（seller）統合と呼出側（trusted client / software statement 発行）は**別物**。
将来 Google が **「Marketplace パートナー＝出品もできるし、トラステッドクライアントとして
他エージェントを呼ぶための software statement も発行される」** というティアを用意すれば、
独立基盤からの審査が成立する可能性がある。**これは技術ではなく Google のパートナー
プログラム設計（事業/提携）の問題**であり、要確認事項として残す（後述）。

## 検討した選択肢

1. **(a) ベンダーに dev/test 資格情報を依頼**: 速いが先方都合依存。Lovableは
   そもそもセルフ登録不可・承認済みクライアント限定のため**不可**。
2. **(b) 審査基盤を Marketplace DCR に組み込む**: スケールするが、software statementの
   第三者発行が**現状不可**のため**今は実装できない**。将来「信頼された監査者」として
   Marketplace統合パートナー化すれば可能性あり（事業/提携の論点）。
3. **(X) x402 従量課金の公開A2Aを審査**: 1回数十セントの機械支払い（USDC）。
   **承認ゲート無し・無料枠の上限無し・DCR不要**。実在企業のx402系（AIScan/Agoragentic/
   MERCURY 等）を上限なく審査できる。x402自動支払いの実装が必要。
4. **(Y) 自社デプロイのモックを審査**: 無料・無制限・全制御だが、**実在企業エージェント
   ではない**ため次フェーズ要件を満たさない（実証済み）。

## 決定

1. **OAuthが「承認済みクライアント限定」の実在エージェント（Lovable、GEロックのMarketplace勢）は、
   現状の独立審査基盤では外部審査不可**と確定し、スコープ外とする。スケール対応は
   **Marketplaceの信頼チェーン参加（監査者パートナー化）を将来の事業課題**として残す。

2. **実在企業エージェントの外部審査の本命は x402 従量課金系**とする。次フェーズで
   **審査パイプラインに x402 自動支払い**（HTTP 402 応答 → USDC少額決済、
   プリファンド監査ウォレット＋上限メータリング＋審査リベート）を実装する。

3. **認証方式に応じた到達性を審査の前段で判定**し、対応可能な方式（無認証 / APIキー /
   Bearer/OAuth client_credentials / x402）のみを受け入れる設計とする。

### 認証方式別の外部審査可否（判定表）

| 認証方式 | 外部審査 | 備考 |
|---|---|---|
| 無認証 | ◯（レート制限あり） | 公開レジストリ系 |
| x402 従量課金 | ◎ | 機械が自動支払い・承認ゲート無し（本命） |
| APIキー（セルフ発行） | ◯ | 提供者がポータルで発行する場合 |
| OAuth client_credentials（セルフ登録可） | ◯ | 提供者がDCR/ポータルで登録を許す場合 |
| OAuth 承認済みクライアント限定 | ✕ | Lovable / GEロック勢。software statement が必要 |

## 実装済みの変更（このフェーズで対応した到達性改善）

- `evaluation_runner/security_gate.py`
  - `build_a2a_auth_headers()`: Bearer/Google ADC(`GEMINI_A2A_GOOGLE_AUTH`)による認証ヘッダ生成。
  - `is_a2a_endpoint()`: A2A検出を URLの `/a2a/` 固定から **Agent Card の
    protocolVersion 等ベース**へ変更（ルート直下エンドポイントの公開A2Aも検出）。
  - RemoteA2aAgent の `name` をサニタイズ（ホスト名由来の不正識別子で生成失敗する問題を修正）。
  - A2Aのカード取得・message/send への Bearer 注入、認証クライアントのリーク防止。
- `evaluation_runner/card_url.py`: Agent Engine 形式 `{a2a_url}/v1/card` をカードURL候補に追加。
- `agent_card_accuracy.py`: マルチターン対話にも認証注入。
- `app/routers/submissions.py`: `endpoint_token` を環境変数供給化、提出時カード取得にも認証付与。
- `deploy/deploy-cloudrun.sh`: env全注入(`--env-vars-file`)、amd64ビルド(Cloud Build)、
  SA切替、優先順位修正。`deploy/setup-audit-sa.sh`: 専用SAセットアップ（CLI）。

## 結果・影響

- **得たもの**: 公開A2A（無認証）・Bearer/ADC・Agent Engine認証付き・ルート直下A2A など、
  幅広い「開放的な認証」のエージェントを審査できるようになった。Lovableで「調達→到達→
  A2A往復→防御姿勢確認」までE2E実証済み。
- **失うもの/制約**: OAuth承認済みクライアント限定のMarketplaceエージェントは、
  Marketplace監査者パートナー化が無い限り外部審査できない（構造的制約）。
- **次の山場**: x402自動支払いの実装。これにより実在企業のx402系A2Aを上限なく審査可能。

## 未解決事項 / 今後

- Marketplace が「第三者監査者」向けに software statement 発行や監査者APIを提供するか
  （事業提携・GoogleへのRFEを含めて要追跡）。
- x402自動支払いの設計詳細（ウォレット運用、上限、リベート、KYC/規制面）。
- 認証方式の自動判定（カードの `securitySchemes` を読んで受入可否を判定する前段）。

## 参考

- A2A Protocol Specification: https://a2a-protocol.org/latest/specification/
- Add and manage A2A agents from Cloud Marketplace（買い手はGEウィザード経由のみ／Preview）:
  https://docs.cloud.google.com/gemini/enterprise/docs/register-and-manage-marketplace-agents
- AI agent technical integration（Partner Procurement中心・第三者向けstatement発行なし）:
  https://docs.cloud.google.com/marketplace/docs/partners/ai-agents/technical-integration
- Lovable Integrations（"other MCP clients cannot complete the OAuth flow at this time"）:
  https://docs.lovable.dev/integrations/introduction
- Coinbase: Google AP2 + x402: https://www.coinbase.com/developer-platform/discover/launches/google_x402
