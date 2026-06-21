# A2A（Agent2Agent）プロトコル 最新バージョン調査レポート

調査日: 2026-05-07
調査者: Another Star合同会社（A2Aセキュアプラットフォーム プロジェクト）

---

## 1. エグゼクティブサマリー

| 項目 | 内容 |
|------|------|
| **プロトコル正式名称** | Agent2Agent Protocol（A2A） |
| **最新安定版** | **v1.0**（初の本番運用可能（GA）バージョン） |
| **v1.0 リリース日** | 2026年3月12日 |
| **管理団体** | Linux Foundation（A2A Project、2025年6月23日発足） |
| **原開発元** | Google（2025年4月発表 → Linux Foundationへ寄贈） |
| **公式仕様書 URL** | https://a2a-protocol.org/latest/specification/ |
| **GitHub** | https://github.com/a2aproject/A2A |
| **ライセンス** | Open Source（Linux Foundation Project） |
| **採用組織数（1周年時点）** | 150以上の組織（Google / Microsoft / AWS など主要クラウド統合済み） |

---

## 2. バージョン履歴と現状

| バージョン | 位置付け | 状態 |
|------------|----------|------|
| v0.2.x | 初期ドラフト | レガシー |
| v0.3.0 | 直前安定版 | サポート継続（v1.0と並行宣伝可能） |
| **v1.0.0** | **初の正式安定版（GA）** | **最新（推奨）** |
| v1.x（予定） | マイナー更新 | ロードマップ上 |

公式仕様サイトでは `latest` パスが v1.0 を指し、`v0.3.0`、`v0.2.5` などバージョン別ドキュメントも併せて公開されている。

---

## 3. v1.0 の主要強化点（初心者向け解説つき）

> 各項目で「**何が嬉しいか（やさしい説明）**」と「**どうやって実現しているか（実装メカニズム）**」をセットで解説する。

---

### 3.1 マルチプロトコル・トランスポート対応

#### 何が嬉しいか
従来「AI同士の会話」をするには、双方が同じ通信方式を喋れる必要があった。例えるなら、片方が日本語、片方が英語しか話せなければ通訳が要る。v1.0ではエージェントが **3種類の "言語"（プロトコル）のうち得意なものを使ってよい** ことになった。受け手側のエージェントが「私は日本語と英語、どっちでもOK」と名乗っておけば、相手が選んで話しかけられる。

サポートされるトランスポート（いずれもHTTPSで暗号化）:

| トランスポート | 特徴 | 主な使いどころ |
|----------------|------|----------------|
| **JSON-RPC 2.0 over HTTP(S)** | 軽量・実装が簡単、人間にも読みやすい | Webアプリ・スクリプト中心の環境 |
| **gRPC（HTTP/2 + Protobuf）** | 高速・低レイテンシ・双方向ストリーミングに強い | 大規模分散システム・低遅延要件 |
| **HTTP/REST（JSON+HTTP）** | 既存のWeb APIエコシステムと相性が良い | 既存のAPIゲートウェイ・WAFを再利用したい |

#### どうやって実現しているか
仕様書では3層構造で抽象化されており、**Layer 1（コア概念）→ Layer 2（抽象操作）→ Layer 3（プロトコルバインディング）** に切り分けている。同じ「タスク送信」という操作を JSON-RPC でも gRPC でも REST でも呼び出せるよう、3つのバインディング間で**等価性（equivalence guarantees）が仕様で保証**されている。

エージェントは自分が話せるトランスポートを **Agent Card（後述）の `preferredTransport`（必須）と `additionalInterfaces`（追加対応）** で宣言する。クライアントは Agent Card を見て、自分が対応しているトランスポートを選んで接続する（動的ネゴシエーションではなく、Agent Card の静的情報からの選択）。

```json
// Agent Card 例（抜粋）
{
  "name": "Search Agent",
  "preferredTransport": "JSONRPC",
  "url": "https://example.com/agent/jsonrpc",
  "additionalInterfaces": [
    { "transport": "GRPC", "url": "https://example.com/agent/grpc" },
    { "transport": "HTTP+JSON", "url": "https://example.com/agent/rest" }
  ]
}
```

---

### 3.2 マルチテナンシー（1つの入口で複数エージェント）

#### 何が嬉しいか
SaaS事業者は、お客さんごとに別々のエージェントを使い分けたいことが多い（例：A社用カスタマーサポートAgent、B社用社内ヘルプAgent）。
v0.x までは「**1つのURL = 1つのエージェント**」が基本だったので、お客さんが増えるたびに新しいURLを払い出す必要があり、**SaaS型の本番運用が事実上できなかった**。

v1.0では、**1つのURL（エンドポイント）の中に複数のエージェントを安全に同居させ、リクエストごとにどのテナント（顧客）のどのエージェントに渡すかを指定できる** ようになった。

#### どうやって実現しているか
- すべてのリクエストメッセージと `AgentInterface` に **`tenant` フィールドが追加** された
- リクエスト単位で `tenant` を指定可能。指定がない場合は `AgentInterface` のデフォルト値が使われる
- サーバ側は `tenant` を見てルーティング・隔離・認可を行う

これによって、Webサービスで使い慣れた「**ロードバランサ → APIゲートウェイ → 共有エンドポイント → テナント別ルーティング**」という枠組みをそのまま流用できる。Microsoft Agent Framework や AWS Bedrock AgentCore Runtime などはこの仕組みを使い、**任意のAIエージェントを数行のホスティングコードでA2A対応エンドポイントとして公開**できるようにしている。

---

### 3.3 Signed Agent Cards（署名付きエージェントカード）

#### 何が嬉しいか
Agent Card は「このエージェントは何ができるか／どこに繋がるか／誰が運営しているか」を書いた **名刺** のような存在。署名がなければ、悪意のある第三者が **偽の名刺を配って成りすまし**、本来のエージェントと通信しているように見せかけることができてしまう。

v1.0では Agent Card に**デジタル署名**を付けることで、

1. **発行元が本物か（authenticity）**
2. **途中で書き換えられていないか（integrity）**

をクライアントが暗号学的に検証できるようになった。これはまさに自社「A2Aセキュアプラットフォーム」の信頼スコアリング・仲介エージェント防御で前提となる仕組みである。

#### どうやって実現しているか
署名は **JWS（JSON Web Signature, RFC 7515）** を採用している。流れは以下のとおり。

1. **Canonicalization（正規化）**: 署名対象となる Agent Card の JSON を **JCS（JSON Canonicalization Scheme, RFC 8785）** で正規化する。これは「同じ意味のJSONなら、誰が処理しても完全に同一のバイト列になる」ようにするための規格。これが無いと、空白や順序の違いだけで署名検証が失敗する。
2. **Protocol Buffer の field presence セマンティクス**を尊重して、「明示的に省略された」「明示的にデフォルト値が設定された」を区別する（再構築時の検証ズレを防ぐ）。
3. **JWSで署名**し、Agent Card の `signature` フィールド（JWS detached signature 形式）に格納する。
4. **クライアントは JWKS（JSON Web Key Set）を信頼できる発行元から HTTPS で取得**し、署名を検証する。SDK上では `signature_verifier` コールバックを transport の `get_card()` に渡すパターンが標準（検証失敗時は例外を発生）。

> 関連: Sigstore コミュニティが `sigstore-a2a` という Agent Card 署名ツールを提供しており、Sigstoreの透明性ログと組み合わせた検証も可能。

```
┌────────────┐  1. AgentCardのJSONを取得         ┌──────────────┐
│ Client      │ ─────────────────────────────► │ Agent Server │
│ (検証側)    │                                  └──────────────┘
│             │  2. JWSのkidからJWKS URLを特定
│             │  3. https://issuer/.well-known/jwks.json を取得
│             │  4. JCSで正規化 → JWS署名を検証
│             │  5. OKなら通信開始 / NGなら拒否
└────────────┘
```

---

### 3.4 セキュリティフローの近代化

#### 何が嬉しいか
v0.x には、当時の慣行に合わせた古い認証パターンが残っていた。v1.0では **「2026年時点のベストプラクティスに合わない仕組みを撤廃」** し、**現代のWebセキュリティの常識に揃えた**。本番運用での監査対応やコンプライアンス（SOC 2、ISO 27001 など）が通しやすくなる。

#### どうやって実現しているか
- **トランスポート層の強制**: 本番環境では **HTTPS必須・TLS 1.2以上**。クライアントは TLS 証明書を信頼CAで検証することが規定（中間者攻撃対策）。
- **認証方式は OpenAPI 互換に統一**: 仕様書が許容するスキームは
  - **API Key**（HTTPヘッダ経由）
  - **OAuth 2.0**（Bearer Token）
  - **OpenID Connect Discovery**（`/.well-known/openid-configuration` でIdP発見）
- **資格情報はプロトコル外で取得**: A2A仕様自体は「どうトークンを取るか」を規定せず、既存のIdP・SSO・KMSと組み合わせる前提。これによって **企業のID基盤（Okta / Azure AD / Auth0 など）をそのまま再利用可能**。
- **認可はリモートエージェント側の責務**: 認証を通したからといって全機能を許すわけではなく、リモート側が「このクライアントにこのスキル／データを使わせてよいか」を判断する。
- **Agent Card の署名（3.3）** とセットで、**エージェントの身元 → クライアントの身元 → 操作の認可** の3段階が明確に整理された。

---

### 3.5 後方互換とバージョンネゴシエーション

#### 何が嬉しいか
v0.3 で動いている既存システムをいきなり全部 v1.0 に切り替えるのは現実的でない。v1.0 では **同じエージェントが「私はv0.3でもv1.0でも喋れますよ」と名乗れる** ようにすることで、**段階的な移行**を可能にしている。

#### どうやって実現しているか
- **Agent Card がバージョン情報を持つ**: 同じトランスポートで複数バージョンのインタフェースを公開可能。例えば「v0.3用URL」と「v1.0用URL」を両方広告する。
- **AgentCard内の `additionalInterfaces` で多重宣言**: 同一エージェントが複数のトランスポート × 複数のバージョンの組み合わせを宣言できる。
- **ただし動的ネゴシエーション仕様は持たない**: クライアントは Agent Card の静的情報を読んで、自分が対応する組み合わせを **選択**する方式（シンプルさ優先）。
- **SDKがバージョン管理を支援**: Python（a2a-python）、Java、.NET の各SDKが「どのバージョンで話すか」を明示するAPIを提供。
- **破壊的変更には移行ガイド**: enum記法の `SCREAMING_SNAKE_CASE` 化、Part構造の統合、ISO 8601 タイムスタンプ統一などはツールチェーン側で自動変換できるように設計されている（公式 Migration Guide あり）。

```
┌──────────────────────────┐
│ AgentCard                │
│  preferredTransport: JSONRPC                  ← 既定の窓口
│  url: https://x/v1/jsonrpc                     ← v1.0系
│  additionalInterfaces:
│   - { transport: GRPC,     url: .../v1/grpc } ← v1.0 / 別トランスポート
│   - { transport: JSONRPC,  url: .../v0.3/rpc } ← 旧クライアント向け互換窓口
└──────────────────────────┘
```

> ポイント: クライアントは「**自分が話せる組み合わせのうち、相手の preferredTransport に最も近いもの**」を選べばよい。サーバ側は v0.3 用のエンドポイントをしばらく残しつつ v1.0 へ誘導する、というロールアウトが可能。

---

## 4. 破壊的変更（v0.3 → v1.0）

| 項目 | v0.3.0 以前 | v1.0 |
|------|--------------|------|
| Enum記法 | kebab-case (例: `submitted`, `working`) | **SCREAMING_SNAKE_CASE** + プレフィクス (例: `TASK_STATE_SUBMITTED`, `TASK_STATE_WORKING`, `TASK_STATE_COMPLETED`)。ProtoJSON仕様準拠 |
| タイムスタンプ | 規定が緩い | **ISO 8601 UTC ミリ秒精度** (`YYYY-MM-DDTHH:MM:SS.sssZ`) を明示 |
| Part構造 | TextPart / FilePart / DataPart の別メッセージ型 | **単一の統合Partメッセージ**に再設計 |
| Agent Card | 単一バージョン広告 | バージョン併記による互換広告 |

> 既存の v0.3 実装は段階的移行が想定されており、Agent Cardの併記広告と移行ガイド（公式 Migration Guide）が用意されている。

---

## 5. アーキテクチャ概観

A2Aは3層構造で定義されている。

| レイヤ | 役割 |
|--------|------|
| **Layer 1: コアコンセプト** | Agent / Agent Card / Task / Message / Part / Artifact |
| **Layer 2: 抽象操作** | Task送信、ステータス取得、メッセージ送受信、ストリーミング購読など |
| **Layer 3: プロトコルバインディング** | JSON-RPC 2.0、gRPC、HTTP/REST へのマッピング |

### 5.1 コアコンセプト（Layer 1）詳細

A2Aの会話は、レストランでの注文に例えると分かりやすい。**Agent**（お店）が **Agent Card**（メニュー兼名刺）を出し、お客（クライアントエージェント）が **Message**（注文）で **Task**（厨房オーダー）を出し、最終的に **Artifact**（料理）が出てくる。**Part**（料理を構成する具材・小皿）は両者の中身を組み立てる最小単位、というイメージ。

#### 5.1.1 Agent（エージェント）

**やさしい説明**: 何らかの能力を提供するソフトウェア主体。LLMアプリ・特化型ボット・社内システムのフロントなど形態は問わない。A2Aでは「サーバとして動くエージェント（**A2A Server**）」と「クライアントとして動くエージェント（**A2A Client**）」の関係で会話する。1つのソフトが両方の役を兼ねることもある。

**実装上の正体**: HTTP(S) エンドポイントを持つWebサービス。フレームワーク（LangGraph / CrewAI / Microsoft Agent Framework / ADK / 自作 など）は不問。A2Aのインタフェースさえ満たせばどう実装してもよい。

#### 5.1.2 Agent Card（エージェントカード）

**やさしい説明**: エージェントの **デジタル名刺兼メニュー表**。「私は誰か」「何ができるか」「どこに繋がるか」「どうやって認証するか」が JSON で書かれている。クライアントは最初にこれを取得して、相手が用途に合うか・どう繋ぐかを判断する。

**主なフィールド**:

| フィールド | 役割 |
|------------|------|
| `name` / `description` | エージェントの名称と説明 |
| `version` | エージェント自体のバージョン |
| `protocolVersion` | 対応する A2A プロトコルバージョン（例: `1.0`） |
| `url` | 既定の接続先 |
| `preferredTransport` | 推奨トランスポート（`JSONRPC` / `GRPC` / `HTTP+JSON`） |
| `additionalInterfaces` | 追加の接続窓口（別トランスポート / 別バージョン併記） |
| `skills` | できることのリスト（IDと説明） |
| `securitySchemes` | 認証方式（API Key / OAuth 2.0 / OIDC など） |
| `capabilities` | streaming / push notification / state transition history などの対応可否 |
| `signature` | （任意）JWS署名（3.3節参照） |

**実装上の正体**: 通常 `https://<agent>/.well-known/agent.json` のような **公開URLでGET取得可能なJSONドキュメント**。プライベート利用ではAuthが必要なURLに置く構成もあり得る。

#### 5.1.3 Task（タスク）

**やさしい説明**: A2Aにおける **作業の単位**。「この調査をして」「このコードをレビューして」など、1つの依頼が1つのTaskになる。**ID付きで状態を持つ（Stateful）** ので、長時間かかる仕事を進捗付きで追跡できる。

**ライフサイクル（v1.0、SCREAMING_SNAKE_CASE）**:

```
TASK_STATE_SUBMITTED      ── 受付済み・着手前
        ↓
TASK_STATE_WORKING        ── 実行中
        ↓ （必要に応じて）
TASK_STATE_INPUT_REQUIRED ── クライアントへ追加情報を要求中（人間や上位エージェントへ問い返し）
        ↓
TASK_STATE_COMPLETED      ── 正常完了
TASK_STATE_FAILED         ── 失敗
TASK_STATE_CANCELED       ── キャンセル
```

**実装上の正体**: サーバ側で永続化される実体（DB行・キュー上のレコードなど）。A2Aクライアントはタスクの **ID** と **コンテキストID（複数タスクを束ねる会話単位）** を頼りに、ポーリング／ストリーミング／Webhookで状態を追跡する。

#### 5.1.4 Message（メッセージ）

**やさしい説明**: クライアントとエージェントの **1ターン分のやり取り**。チャットの「1吹き出し」に相当する。これを送ることでTaskを開始したり、進行中のTaskに追加情報を送ったり、エージェント側から途中経過や問い返しを返したりする。

**主なフィールド**:

| フィールド | 役割 |
|------------|------|
| `role` | `user`（クライアント発）か `agent`（エージェント発）かを示す |
| `parts` | 1個以上の Part（次節） |
| `messageId` | メッセージの一意ID |
| `taskId` / `contextId` | 紐づくTask・コンテキスト |
| `metadata` | 任意の付加情報 |

**実装上の正体**: JSONオブジェクト。Taskを「箱」とすると、Messageはその中で行き来する「1通の便箋」のようなもの。

#### 5.1.5 Part（パート）

**やさしい説明**: MessageやArtifactの中身を構成する **最小ブロック**。1つのMessageには複数のPartを入れられるので、「テキスト + 画像 + 構造化JSON」を1メッセージで一度に渡すことができる（マルチモーダル対応）。

**3種類の中身（v1.0では統一Partメッセージにまとめられた）**:

| 種類 | 内容 | 用途例 |
|------|------|--------|
| **Text Part** | プレーンテキストやMarkdown | 自然言語の指示や応答 |
| **File Part** | ファイル本体（base64）または URI 参照 | PDF、画像、音声、動画 |
| **Data Part** | 構造化JSON（任意のスキーマ） | フォーム値、API応答、計算結果 |

**v1.0の重要変更**: v0.3 以前は `TextPart` / `FilePart` / `DataPart` を別の型として定義していたが、v1.0 では **`oneof` で中身を切り替える単一のPartメッセージ** に統合された。これにより各SDKの型扱いが単純化され、`Part` 配列を受け取った側は中身を1か所で分岐すればよくなった。

**UIネゴシエーション**: Part にはコンテンツタイプ（MIME相当）が付くので、受け手が「自分はマークダウンしか描画できない」「画像も表示できる」を判断して、エージェント側に最適な形式を選ばせることが可能。

#### 5.1.6 Artifact（アーティファクト）

**やさしい説明**: Taskの **最終成果物**。Taskが「依頼伝票」だとすると、Artifactは「納品物」。1つのTaskが複数のArtifactを返すこともある（例：レポート本文.md + 添付グラフ画像 + 構造化JSONサマリ）。

**主なフィールド**:

| フィールド | 役割 |
|------------|------|
| `artifactId` | 一意ID |
| `name` / `description` | 名称と説明 |
| `parts` | Artifactを構成するPartのリスト（Messageと同じPart構造を再利用） |
| `metadata` | 任意の付加情報 |

**ストリーミング対応**: Artifactは **段階的に追記（append）** できる。レポートを少しずつ生成・送信したり、大きなファイルをチャンク分割で届けたりするユースケースに使う。クライアントはSSEなどで `artifact.update` イベントを受け取り、Partを順次取り込んでいく。

**Message と Artifact の違い**:
- **Message** = 「会話のやり取り（途中の発言・問い返し・指示）」
- **Artifact** = 「Taskの正式な成果物（最終納品物）」

会話の途中の発言は Message、確定した成果は Artifact、という整理。

#### 5.1.7 全体関係図

```
┌─────────────────────────────────────────────────────────┐
│ Agent (サーバ)                                           │
│  └─ Agent Card (公開メタデータ)                          │
│       ├─ skills, securitySchemes, transports           │
│       └─ signature (JWS, 任意)                           │
│                                                         │
│  受信した Task                                           │
│   ├─ id / contextId / status (TASK_STATE_*)             │
│   ├─ Messages[]                                         │
│   │    └─ Message                                       │
│   │         ├─ role (user / agent)                      │
│   │         └─ Parts[] (Text / File / Data)             │
│   └─ Artifacts[]  ←── 最終成果物                         │
│        └─ Artifact                                      │
│             └─ Parts[] (Text / File / Data)             │
└─────────────────────────────────────────────────────────┘
        ▲
        │ HTTP(S) (JSON-RPC / gRPC / REST)
        ▼
┌─────────────────────────────────────────────────────────┐
│ Client Agent                                            │
│  1. Agent Card 取得 → 署名検証 → スキル確認              │
│  2. Message 送信で Task 開始                             │
│  3. ストリーミング/ポーリング/Webhookで進捗追跡          │
│  4. Artifact 受領                                        │
└─────────────────────────────────────────────────────────┘
```

### 5.2 通信パターン
- 同期 Request/Response
- ストリーミング（Server-Sent Events / SSE）
- 非同期 Push Notification（Webhook）
- ポーリング

---

## 6. セキュリティモデル（v1.0）

| 観点 | 仕様 |
|------|------|
| **トランスポート暗号化** | 本番では HTTPS 必須、TLS 1.2 以上を推奨 |
| **サーバ認証** | クライアントは TLS証明書を信頼CAで検証（中間者攻撃防止） |
| **クライアント認証** | OpenAPI互換: API Key / OAuth 2.0 / OpenID Connect Discovery |
| **資格情報の伝送** | 標準 HTTP ヘッダ経由（プロトコル外取得） |
| **認可** | リモートエージェント側でアクセス制御を実施 |
| **エージェント身元検証** | Signed Agent Cards により署名検証 |

A2Aセキュアプラットフォーム（自社プロジェクト）の信頼スコアリング・審査パイプライン・仲介エージェント防御は、これらの v1.0 仕様を前提に設計可能。

---

## 7. エコシステム動向（2026年4月時点）

- **Microsoft**: Azure AI Foundry / Copilot Studio へ A2A v1 を統合（.NET向け Microsoft Agent Framework で対応）
- **AWS**: Amazon Bedrock AgentCore Runtime で A2A をサポート
- **Google Cloud**: Vertex AI / Agent Engine で標準採用、Linux Foundationへ寄贈済み
- **SDK**: Python（a2a-python）、Java（A2A Java SDK 0.3.0）、.NET、Go など多言語実装が公式リポジトリ群で提供
- **採用組織**: 150社以上、複数業界で本番稼働事例あり

---

## 8. 自社プロジェクトへの示唆（A2Aセキュアプラットフォーム）

1. **設計のベースラインは v1.0 へ更新**：信頼スコアリング・仲介エージェントが扱うAgent Cardは Signed Agent Cards 前提とする。
2. **マルチプロトコル仲介**：JSON-RPC / gRPC / REST いずれも仲介できる構造にすることで、対応エージェントの裾野を最大化。
3. **マルチテナント設計**：1エンドポイントで複数エージェントを安全にホストするユースケースが標準化されたため、自社プラットフォームの審査パイプラインもテナント分離を前提に設計。
4. **TASK_STATE 表記更新**：内部状態管理ロジック（`submitted` 等の文字列）は SCREAMING_SNAKE_CASE 化が必要。
5. **Agent Card 併記広告**：移行期は v0.3 と v1.0 を同時広告して下位互換確保。

---

## 9. 参考情報源（エビデンスURL）

### 公式・一次情報（追加：5.1 コアコンセプトの根拠）
- A2A Core Concepts（公式）: https://a2a-protocol.org/latest/topics/key-concepts/
- A2A Community: Core Concepts Overview: https://agent2agent.info/docs/concepts/overview/
- A2A Community: AgentCard: https://agent2agent.info/docs/concepts/agentcard/
- A2A Community: Artifact: https://agent2agent.info/docs/concepts/artifact/
- A2A Community: Core Protocol Specification: https://agent2agent.info/specification/core/
- HuggingFace Blog: A2A Protocol Explained: https://huggingface.co/blog/1bo/a2a-protocol-explained
- Microsoft Tech Community: Implementing A2A in .NET: https://techcommunity.microsoft.com/blog/azuredevcommunityblog/implementing-a2a-protocol-in-net-a-practical-guide/4480232

### 公式・一次情報（追加：3.1〜3.5の根拠）
- Agent Card署名（JWS / JCS / RFC 7515 / RFC 8785）: https://a2a-protocol.org/latest/specification/
- Sigstore A2A（Agent Card署名ツール）: https://github.com/sigstore/sigstore-a2a
- Agent Card v1.0 Schema: https://gist.github.com/SecureAgentTools/0815a2de9cc31c71468afd3d2eef260a
- Issue #916（Agent Card 署名提案）: https://github.com/a2aproject/A2A/issues/916
- Issue #1672（Agent Identity Verification 提案）: https://github.com/a2aproject/A2A/issues/1672
- Issue #1151（Transport Support 仕様更新）: https://github.com/a2aproject/A2A/issues/1151
- Microsoft Agent Framework（A2Aホスティング実装例）: https://devblogs.microsoft.com/agent-framework/a2a-v1-is-here-cross-platform-agent-communication-in-microsoft-agent-framework-for-net/
- AWS Bedrock AgentCore（A2Aプロトコル契約）: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-a2a-protocol-contract.html
- LangChain Agent Server（A2Aエンドポイント）: https://docs.langchain.com/langsmith/server-a2a

### 公式・一次情報
- A2A Protocol 公式（最新仕様）: https://a2a-protocol.org/latest/specification/
- A2A v1.0 リリースアナウンス: https://a2a-protocol.org/latest/announcing-1.0/
- What's New in v1.0: https://a2a-protocol.org/latest/whats-new-v1/
- v0.3.0 仕様（旧版）: https://a2a-protocol.org/v0.3.0/specification/
- ロードマップ: https://a2a-protocol.org/latest/roadmap/
- エンタープライズ機能: https://a2a-protocol.org/latest/topics/enterprise-ready/
- GitHub リポジトリ（a2aproject/A2A）: https://github.com/a2aproject/A2A
- GitHub Releases: https://github.com/a2aproject/A2A/releases

### Linux Foundation
- A2A Project 発足プレスリリース（2025/6/23）: https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project-to-enable-secure-intelligent-communication-between-ai-agents
- 1周年（150組織超）プレスリリース: https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year
- LFX Insights: https://insights.linuxfoundation.org/project/agent2agent-a2a-protocol

### 主要ベンダ
- Google Developers Blog（A2A発表）: https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/
- Google Cloud（Linux Foundation寄贈）: https://developers.googleblog.com/en/google-cloud-donates-a2a-to-linux-foundation/
- Google Cloud Blog（A2Aアップグレード）: https://cloud.google.com/blog/products/ai-machine-learning/agent2agent-protocol-is-getting-an-upgrade
- Microsoft Agent Framework（A2A v1）: https://devblogs.microsoft.com/agent-framework/a2a-v1-is-here-cross-platform-agent-communication-in-microsoft-agent-framework-for-net/
- Microsoft Learn 移行ガイド: https://learn.microsoft.com/en-us/agent-framework/migration-guide/agent-to-agent-sdk-v1
- IBM Think（A2A概要）: https://www.ibm.com/think/topics/agent2agent-protocol
- Salesforce: https://www.salesforce.com/agentforce/ai-agents/agent2agent-protocol/
- Red Hat Developer（A2Aセキュリティ強化）: https://developers.redhat.com/articles/2025/08/19/how-enhance-agent2agent-security

### 報道・解説
- AIwire（1周年振り返り）: https://www.hpcwire.com/aiwire/2026/04/09/linux-foundation-a2a-protocol-marks-one-year-with-broad-enterprise-and-cloud-adoption/
- The Fast Mode: https://www.thefastmode.com/technology-solutions/48034-linux-foundation-s-a2a-protocol-gains-rapid-enterprise-adoption-across-cloud-giants
- Codilime（解説記事）: https://codilime.com/blog/a2a-protocol-explained/
- DeepWiki（バージョン履歴）: https://deepwiki.com/a2aproject/A2A/6.3-protocol-version-history

---

*本レポートは公開情報を基に作成。仕様詳細実装時は必ず公式仕様書（a2a-protocol.org/latest/specification/）の最新版を参照のこと。*
