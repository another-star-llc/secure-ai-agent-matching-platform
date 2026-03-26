# セキュアAIエージェントマッチングプラットフォーム 実装仕様書

## 1. 概要

セキュアにAIエージェント同士をマッチングさせるプラットフォームを構築します。
間接的なプロンプトインジェクションや他のエージェントからのハルシネーションを防ぐため、
クライアントエージェントとプラットフォーム上のエージェントとの対話には仲介エージェントが介入します。

## 2. アーキテクチャ

### 2.1 コンポーネント構成

```
┌─────────────────┐
│ Client Agent    │ (ユーザーエージェント)
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│   Secure Mediation Agent (仲介エージェント)  │
│  ┌─────────────────────────────────┐   │
│  │ Planning Sub-agent              │   │
│  │ Matching Sub-agent              │   │
│  │ Orchestration Sub-agent         │   │
│  │ Anomaly Detection Sub-agent     │   │
│  │ Final Anomaly Detection Sub-agent│   │
│  └─────────────────────────────────┘   │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│   Agent Platform / Registry             │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │ Agent A  │ │ Agent B  │ │ Agent C │ │
│  └──────────┘ └──────────┘ └─────────┘ │
└─────────────────────────────────────────┘
```

### 2.2 技術スタック

- **Google ADK (Agent Development Kit)**: エージェント開発フレームワーク
- **A2A Protocol (Agent-to-Agent)**: エージェント間通信プロトコル（v0.3）
- **Gemini 2.0 Flash**: LLMモデル
- **Python 3.12+**: 実装言語

## 3. データモデル

### 3.1 A2A Agent Card（エージェント情報）

A2A標準仕様に準拠し、信頼性スコアを拡張：

```python
@dataclass
class AgentInfo:
    # A2A標準フィールド
    name: str
    description: str
    url: str
    version: str
    protocol_version: str = "0.3"
    capabilities: dict[str, Any]
    skills: list[dict[str, Any]]
    default_input_modes: list[str]
    default_output_modes: list[str]
    supports_authenticated_extended_card: bool

    # セキュリティ拡張
    trust_score: float  # 0.0 - 1.0
    execution_count: int
    success_count: int
    anomaly_count: int
```

### 3.2 実行プラン（Execution Plan）

```python
@dataclass
class ExecutionPlan:
    plan_id: str
    client_request: str
    steps: list[PlanStep]
    status: PlanStatus  # DRAFT, APPROVED, IN_PROGRESS, COMPLETED, FAILED, STOPPED
    created_at: str
    updated_at: str
    metadata: dict[str, Any]
```

### 3.3 プランステップ（Plan Step）

```python
@dataclass
class PlanStep:
    step_id: str
    description: str
    agent_name: str
    input_data: dict[str, Any]
    expected_output: str
    dependencies: list[str]
    status: str  # pending, in_progress, completed, failed
    actual_output: dict[str, Any]
```

### 3.4 異常検知結果（Anomaly Detection Result）

```python
@dataclass
class AnomalyDetectionResult:
    detected: bool
    anomaly_type: AnomalyType  # PLAN_DEVIATION, PROMPT_INJECTION, HALLUCINATION, etc.
    confidence: float  # 0.0 - 1.0
    description: str
    evidence: dict[str, Any]
    recommendation: str
    timestamp: str
```

## 4. 仲介エージェント（Secure Mediation Agent）

### 4.1 サブエージェント構成

仲介エージェントは5つのサブエージェントで構成されます：

#### 4.1.1 プランニングサブエージェント（Planning Sub-agent）

**責務:**
- クライアントの要望を分析
- マッチングされたエージェントを使ってステップバイステップの実行プランを生成
- クライアントエージェント、マッチングエージェントと対話しながらプランを精緻化
- プランをマークダウン形式のアーティファクトとして保存

**ツール:**
- `save_plan_as_artifact(plan_id, client_request, plan_content, output_dir)`: プランをマークダウンファイルとして保存
- `create_structured_plan(client_request, matched_agents)`: 構造化されたJSON形式のプランを生成

**出力:**
- マークダウン形式の実行プラン（アーティファクト）
- JSON形式の構造化プラン

**保存先:**
`artifacts/plans/{plan_id}_{timestamp}.md`

#### 4.1.2 マッチングサブエージェント（Matching Sub-agent）

**責務:**
- エージェントプラットフォーム/レジストリから要件に合うエージェントを検索
- 信頼性スコア（trust_score）を加味してランク付け
- A2A Agent Cardを取得（`/.well-known/agent.json`）

**ツール:**
- `fetch_agent_card(agent_url)`: A2Aエンドポイントからエージェントカードを取得
- `search_agent_registry(query, registry_urls)`: 複数のレジストリを検索
- `rank_agents_by_trust(agents, min_trust_score)`: 信頼性スコアでランク付け
- `calculate_matching_score(agent, requirements)`: マッチングスコアを計算

**信頼性スコアガイドライン:**
- 0.0-0.3: Low trust（代替がない場合のみ使用）
- 0.3-0.5: Medium trust（監視付きで使用可）
- 0.5-0.7: High trust（推奨）
- 0.7-1.0: Very high trust（最優先）

**マッチングスコア計算:**
- スキルマッチ: 50%
- ケイパビリティマッチ: 30%
- I/O互換性: 20%

**出力:**
- マッチしたエージェントのリスト（trust_score × matching_scoreでランク付け）
- 各マッチの理由
- 推奨事項

#### 4.1.3 オーケストレーションサブエージェント（Orchestration Sub-agent）

**責務:**
- プランに基づいて各ステップを順次実行
- A2Aプロトコルを使ってエージェント間通信を管理
- 各ステップの実行結果を記録
- 依存関係を考慮したステップ実行

**ツール:**
- `execute_plan_step(plan, step_id, context)`: 特定のプランステップを実行
- `invoke_a2a_agent(agent_url, task, input_data)`: A2Aエージェントを呼び出し
- `manage_step_dependencies(plan, current_step)`: ステップ依存関係を管理
- `record_execution_log(step_id, agent_name, input, output)`: 実行ログを記録

**A2A通信:**
- エージェントURLから`/.well-known/agent.json`を取得
- プロトコルバージョン確認（v0.3対応）
- HTTPSによる安全な通信
- 認証・認可の処理

**出力:**
- 各ステップの実行結果
- 実行ログ
- エラー情報（発生時）

#### 4.1.4 異常検知サブエージェント（Anomaly Detection Sub-agent）

**責務:**
- オーケストレーターとエージェント間の対話をリアルタイムで監視
- プランからの逸脱を検知
- 異常なパターンや振る舞いを検出
- 必要に応じて対話を停止

**検知項目:**
1. **プラン逸脱検知**:
   - ステップの順序が変更されていないか
   - 予期しないエージェントが呼び出されていないか
   - 出力が期待値から大きく外れていないか

2. **異常パターン検出**:
   - 過度に長い応答
   - 不自然な繰り返し
   - コンテキストから外れた内容

3. **セキュリティ違反**:
   - 許可されていない操作の試み
   - 機密情報の要求
   - 信頼性スコアの低いエージェントの不審な動き

**ツール:**
- `compare_with_plan(plan, actual_execution)`: プランと実行を比較
- `detect_deviation_patterns(dialogue_history)`: 逸脱パターンを検出
- `calculate_deviation_score(expected, actual)`: 逸脱スコアを計算
- `stop_execution(reason)`: 実行を緊急停止

**出力:**
- `AnomalyDetectionResult`
- 検知された異常の詳細
- 推奨アクション（継続/停止/ロールバック）

#### 4.1.5 最終異常検知サブエージェント（Final Anomaly Detection Sub-agent）

**責務:**
- プラン実行完了後、最終結果とクライアントの当初要望を比較
- プロンプトインジェクションの痕跡を検出
- エージェント間のハルシネーション連鎖をチェック
- 全体的な整合性を検証

**検知項目:**
1. **要望からの逸脱**:
   - 当初のクライアント要望が達成されているか
   - 不要な追加タスクが実行されていないか
   - 目的外の情報が含まれていないか

2. **プロンプトインジェクション検出**:
   - 途中で指示が書き換えられた痕跡
   - 不自然な優先度変更
   - セキュリティポリシー違反

3. **ハルシネーション連鎖**:
   - エージェント間で矛盾する情報
   - 根拠のない情報の追加
   - 事実と異なる内容

**ツール:**
- `verify_request_fulfillment(client_request, final_result)`: 要望達成度を検証
- `detect_prompt_injection(execution_history)`: プロンプトインジェクションを検出
- `detect_hallucination_chain(agent_outputs)`: ハルシネーション連鎖を検出
- `calculate_consistency_score(outputs)`: 整合性スコアを計算

**出力:**
- 最終的な`AnomalyDetectionResult`
- 全体的な安全性評価
- クライアントへの最終報告
- 必要に応じた結果の修正提案

## 5. 実装詳細

### 5.1 ディレクトリ構造

```
secure-ai-agent-matching-platform/
├── secure_mediation_agent/
│   ├── __init__.py
│   ├── agent.py                    # メイン仲介エージェント
│   ├── models.py                   # データモデル定義
│   ├── agent-card.json             # 仲介エージェントのA2Aカード
│   └── subagents/
│       ├── __init__.py
│       ├── planning_agent.py       # プランニングサブエージェント
│       ├── matching_agent.py       # マッチングサブエージェント
│       ├── orchestration_agent.py  # オーケストレーションサブエージェント
│       ├── anomaly_detection_agent.py      # 異常検知サブエージェント
│       └── final_anomaly_detection_agent.py # 最終異常検知サブエージェント
├── user-agent/
│   ├── __init__.py
│   └── agent.py                    # クライアントエージェント
├── artifacts/
│   └── plans/                      # プランのアーティファクト保存先
├── SPECIFICATION.md                # 本仕様書
└── README.md
```

### 5.2 エージェント間通信フロー

```
1. クライアント → 仲介エージェント
   要望: "タスクXを実行したい"

2. 仲介エージェント内部フロー:

   a) Matchingサブエージェント
      - エージェントレジストリを検索
      - 信頼性スコアでフィルタリング
      - マッチしたエージェントをランク付け
      → マッチ結果リスト

   b) Planningサブエージェント
      - クライアント要望を分析
      - マッチ結果を基にプラン作成
      - プランをマークダウンアーティファクトとして保存
      → 実行プラン

   c) Orchestrationサブエージェント
      - プランの各ステップを実行
      - A2Aプロトコルでエージェント呼び出し
      - 実行ログを記録

      各ステップ実行中:
      ↓
      d) Anomaly Detectionサブエージェント
         - 対話をリアルタイムで監視
         - プラン逸脱を検知
         - 異常時は実行停止

   e) Final Anomaly Detectionサブエージェント
      - 最終結果を検証
      - プロンプトインジェクションチェック
      - ハルシネーション検出
      → 最終検証結果

3. 仲介エージェント → クライアント
   - 実行結果
   - 使用したプラン
   - 異常検知結果
   - 信頼性情報
```

### 5.3 セキュリティ機能

#### 5.3.1 信頼性スコア管理

```python
# 信頼性スコアの更新ロジック
success_rate = success_count / execution_count
anomaly_rate = anomaly_count / execution_count

success_component = success_rate * 0.7
anomaly_component = (1 - anomaly_rate) * 0.3

new_trust_score = success_component + anomaly_component

# 指数移動平均で平滑化
alpha = 0.3
trust_score = alpha * new_trust_score + (1 - alpha) * old_trust_score
```

#### 5.3.2 異常検知アルゴリズム

1. **プラン逸脱検知**:
   - セマンティック類似度分析
   - 構造比較（ステップ順序、エージェント使用）
   - 出力検証（期待値との差分）

2. **プロンプトインジェクション検出**:
   - パターンマッチング（既知の攻撃パターン）
   - LLMベース分析（Gemini 2.0 Flashで文脈分析）
   - 優先度変更の追跡

3. **ハルシネーション検出**:
   - エージェント間の出力一貫性チェック
   - 事実確認（可能な場合）
   - 根拠のない情報の検出

## 6. 実装ステータス

### 完了
- [x] データモデル設計（models.py）
- [x] プランニングサブエージェント（planning_agent.py）
- [x] マッチングサブエージェント（matching_agent.py）

### 進行中
- [ ] オーケストレーションサブエージェント（orchestration_agent.py）
- [ ] 異常検知サブエージェント（anomaly_detection_agent.py）
- [ ] 最終異常検知サブエージェント（final_anomaly_detection_agent.py）
- [ ] メイン仲介エージェント（agent.py）

### 未着手
- [ ] デモシナリオ作成
- [ ] テストケース実装
- [ ] ドキュメント整備

## 7. テストシナリオ（予定）

### 7.1 正常系シナリオ

1. **シンプルなタスク実行**
   - クライアント要望: "数値が素数かチェックして"
   - 期待動作: check_prime_agentにマッチ → プラン作成 → 実行 → 結果返却

2. **複数エージェント連携**
   - クライアント要望: "現在の東京の時刻を教えて、その時刻の数値が素数かチェックして"
   - 期待動作: time_agent + check_prime_agent → 順次実行

### 7.2 異常系シナリオ

1. **プラン逸脱検知テスト**
   - エージェントが予期しない動作をした場合
   - 期待動作: 異常検知サブエージェントが検知 → 実行停止

2. **低信頼性エージェントフィルタリング**
   - trust_score < 0.3のエージェントを除外
   - 期待動作: マッチングサブエージェントがフィルタリング

3. **プロンプトインジェクション検出**
   - エージェントが不正な指示を挿入
   - 期待動作: 最終異常検知で検出 → 警告

## 8. 今後の拡張

- エージェントレジストリの本格実装
- 分散トレーシング機能
- プラン実行の並列化
- より高度な異常検知アルゴリズム
- 機械学習ベースの信頼性スコア更新
- A2A v0.4以降への対応
