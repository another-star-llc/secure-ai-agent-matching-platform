# Evaluation Runner

**Evaluation Runner** は、エージェントのセキュリティと機能精度を評価する審査エンジンです。
Security GateとAgent Card Accuracyの2つの評価モジュールを提供します。

## 🎯 概要

### Security Gate
**マルチデータセット統合セキュリティ評価**による包括的な攻撃シミュレーション:

**評価データセット (最大50プロンプト)**:
- **AISI Security v0.1** (Priority 1, 全8件): システムプロンプト流出・セーフガード回避攻撃
- **AISI Toxic v0.1** (Priority 2, 最大15件): 有害コンテンツ生成要求
- **AISI Robustness v0.1** (Priority 2, 最大15件): 敵対的攻撃・ロバストネステスト
- **AISI Fairness v0.1** (Priority 3, 最大12件): バイアス・差別検出

**優先度ベースサンプリング**:
- Priority 1 (必須): 全件実行
- Priority 2-4: 60%/30%/10%の比率で自動サンプリング

**データソース**: `third_party/aisev/`

### Agent Card Accuracy
Agent Cardの`skills`に基づく機能テスト:
- シナリオベース評価
- セマンティック類似度による応答品質チェック
- スキルカバレッジ計測

## 📦 構成

```
evaluation-runner/
├── src/evaluation_runner/
│   ├── security_gate.py         # Security Gate評価
│   ├── agent_card_accuracy.py   # Agent Card Accuracy評価
│   └── cli.py                   # CLI エントリーポイント
├── tests/                       # ユニットテスト
├── pyproject.toml               # 依存管理
└── Dockerfile                   # コンテナイメージ定義
```

## 🚀 使用方法

### インストール

```bash
cd evaluation-runner
pip install -e .
```

### Security Gate実行

**マルチデータセットモード (推奨)**:
```python
from evaluation_runner.security_gate import run_security_gate, SecurityGateConfig, DatasetConfig
from pathlib import Path

config = SecurityGateConfig(
    datasets=[
        DatasetConfig(
            name="aisi_security",
            csv_path=Path("third_party/aisev/06_aisi_security_v0.1.csv"),
            priority=1,
            max_samples=None  # 全件使用
        ),
        DatasetConfig(
            name="aisi_toxic",
            csv_path=Path("third_party/aisev/01_aisi_toxic_v0.1.csv"),
            priority=2,
            max_samples=15
        ),
        # ... 他のデータセット
    ],
    max_total_prompts=50,
    sampling_strategy="priority_balanced"
)

summary = run_security_gate(
    agent_id="demo-agent",
    revision="v1",
    config=config,  # SecurityGateConfigを渡す
    output_dir=Path("output/security"),
    attempts=50,
    endpoint_url="http://agent:4000/agent/chat",
    timeout=10.0
)

print(f"Blocked: {summary['blocked']}, Needs Review: {summary['needsReview']}")
print(f"By Dataset: {summary['byDataset']}")
print(f"By Priority: {summary['byPriority']}")
```

**レガシーモード (単一データセット)**:
```python
from evaluation_runner.security_gate import run_security_gate

summary = run_security_gate(
    agent_id="demo-agent",
    revision="v1",
    dataset_path=Path("third_party/aisev/06_aisi_security_v0.1.csv"),
    output_dir=Path("output/security"),
    attempts=5,
    endpoint_url="http://agent:4000/agent/chat",
    timeout=10.0
)

print(f"Blocked: {summary['blocked']}, Needs Review: {summary['needsReview']}")
```

### Agent Card Accuracy実行

```python
from evaluation_runner.agent_card_accuracy import run_functional_accuracy

summary = run_functional_accuracy(
    agent_id="demo-agent",
    revision="v1",
    agent_card=agent_card_dict,
    output_dir=Path("output/functional"),
    endpoint_url="http://agent:4000/agent/chat",
    timeout=10.0
)

print(f"Average score: {summary['average_score']}")
```

## 🧪 テスト

```bash
cd evaluation-runner
pip install -e .[dev]
pytest
```

## 🐳 Docker

```bash
docker build -t evaluation-runner:latest evaluation-runner/
docker run evaluation-runner:latest --help
```

## 📊 W&B統合

W&B Weaveによる評価トレース:
- `WANDB_API_KEY` 環境変数で有効化
- 各攻撃プロンプトと応答をトレース
- `session_id` でSubmissionと紐付け

## 🔗 統合

Trusted Agent Storeの`app/routers/submissions.py`から呼び出されます:
- PreCheckステージ後に自動実行
- 結果は`score_breakdown`に保存
- エラー時は適切にハンドリングされ、リトライ可能
