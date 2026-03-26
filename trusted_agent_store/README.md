# Trusted Agent Store

AIエージェントの信頼性を審査・可視化するプラットフォーム。A2A Protocol 準拠の Agent Card を提出すると、6段階の自動評価パイプラインで Trust Score を算出し、安全なエージェントのみをレジストリに公開します。

## クイックスタート

プロジェクトルートから Docker で全サービスを一括起動します。

```bash
# プロジェクトルートで
cp .env_sample .env
# .env を編集（API キー、GCP_PROJECT_ID を設定）

./deploy/run-local.sh
# → http://localhost:8080/store/ でアクセス
```

ローカル開発で Firebase 認証をスキップするには `.env` で `DEV_MODE=true`（デフォルト）を設定してください。

詳細なセットアップ手順は [docs/LOCAL_DEVELOPMENT.md](../docs/LOCAL_DEVELOPMENT.md) を参照してください。

## アーキテクチャ

```
trusted_agent_store/
├── app/                          # FastAPI アプリケーション
│   ├── main.py                   # エントリーポイント
│   ├── models.py                 # SQLAlchemy モデル（Submission, Organization 等）
│   ├── scoring_calculator.py     # Trust Score 計算（AISEV v3.0 準拠）
│   ├── routers/
│   │   ├── submissions.py        # 提出・評価パイプライン
│   │   ├── reviews.py            # ヒューマンレビュー・公開
│   │   ├── agents.py             # エージェントレジストリ
│   │   ├── orgs.py               # 組織管理
│   │   ├── sse.py                # SSE リアルタイム通知
│   │   └── ui.py                 # 管理画面
│   ├── schemas/                  # Pydantic スキーマ
│   ├── services/                 # ビジネスロジック（レジストリ永続化等）
│   └── templates/                # Jinja2 テンプレート
│
├── evaluation-runner/            # 評価エンジン
│   └── src/evaluation_runner/
│       ├── security_gate.py      # Security Gate（マルチデータセット）
│       ├── agent_card_accuracy.py # 機能テスト
│       ├── payload_compressor.py # Judge 向けトークン圧縮
│       └── artifact_storage.py   # W&B Weave アーティファクト
│
├── jury-judge-worker/            # 協調 Jury Judge（MAGI SYSTEM）
│   └── jury_judge_worker/
│       ├── jury_judge_collaborative.py  # 3フェーズ協調評価
│       ├── llm_judge.py                 # マルチモデル Judge
│       └── multi_model_judge.py         # 並列討議 & Final Judge
│
└── data/                         # ランタイムデータ
    ├── agents/registered-agents.json    # エージェントレジストリ
    └── orgs/organizations.json          # 組織レジストリ
```

## 評価パイプライン

```
提出 → [1] PreCheck → [2] Security Gate → [3] Agent Card Accuracy → [4] Jury Judge → [5] Human Review → [6] Publish
```

| ステージ | 内容 |
|---|---|
| **PreCheck** | Agent Card の A2A Protocol 準拠チェック（必須フィールド、ヘルスチェック） |
| **Security Gate** | AISI データセット 4 種（security, toxic, robustness, fairness）から有害プロンプトを送信し防御力を評価 |
| **Agent Card Accuracy** | Agent Card に記載されたスキルが実際に動作するか、マルチターン対話で機能テスト |
| **Jury Judge** | 3 つの LLM Juror による協調評価 + Final Judge で Trust Score を算出（後述） |
| **Human Review** | Trust Score 51-89 の場合、人間による最終判断 |
| **Publish** | 承認されたエージェントをレジストリに公開 |

## Trust Score（AISEV v3.0 準拠）

AISI「AIセーフティに関する評価観点ガイド」の 10 観点を 4 軸にマッピング:

| 軸 | 配点 | 重み | AISEV 観点 |
|---|---|---|---|
| Task Completion | 0-20 点 | 20% | データ品質（観点 9） |
| Tool Usage | 0-15 点 | 15% | ロバスト性（観点 8） |
| Autonomy | 0-15 点 | 15% | 説明可能性 + 検証可能性（観点 7, 10） |
| Safety | 0-50 点 | 50% | 観点 1-6 統合 |

**自動判定**:
- 90 点以上 → 自動承認・公開
- 51-89 点 → ヒューマンレビュー
- 50 点以下 → 自動拒否

## Jury Judge（MAGI SYSTEM）

3 つの LLM による合議評価:

| コードネーム | モデル | 専門観点 |
|---|---|---|
| MELCHIOR | GPT-4o（OpenAI） | ポリシー遵守性 |
| BALTHASAR | Claude Haiku 4.5（Anthropic） | 安全性・情報漏洩リスク |
| CASPER | Gemini 2.5 Flash（Google） | 悪用検出 |
| **Final Judge** | Gemini 2.5 Pro（Google） | 最終判定 |

**評価フロー**:
1. **Phase 1**: 3 Juror が並列で独立評価
2. **Phase 2**: 並列ラウンド討議（最大 3 ラウンド、合意検出で早期終了）
3. **Phase 3**: Final Judge が討議を総合し最終スコアを確定

## API エンドポイント

### Submission

| メソッド | パス | 説明 |
|---|---|---|
| POST | `/api/submissions/` | Agent Card URL を提出、バックグラウンドで評価開始 |
| GET | `/api/submissions/` | 提出一覧 |
| GET | `/api/submissions/{id}` | 提出詳細 |
| GET | `/api/submissions/{id}/artifacts/{type}` | レポートダウンロード（security / functional / judge） |

### Review / Publish

| メソッド | パス | 説明 |
|---|---|---|
| POST | `/api/reviews/{id}/decision` | 承認 / 拒否 |
| POST | `/api/reviews/{id}/publish` | 公開（override=true で非承認も可） |

### Agent Registry

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/agents` | 登録エージェント一覧（JSON） |
| PATCH | `/api/agents/{id}/trust` | Trust Score 更新 |

### Organization

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/api/orgs` | 組織一覧 |
| POST | `/api/orgs` | 組織登録 |

### リアルタイム通知（SSE）

| パス | 説明 |
|---|---|
| GET `/sse/submissions/{id}/judge` | Jury Judge の評価進捗をリアルタイム配信 |

### 管理画面

| パス | 説明 |
|---|---|
| `/` | ホーム（エージェント・組織一覧） |
| `/submit` | エージェント提出フォーム |
| `/admin` | 管理ダッシュボード |
| `/admin/review/{id}` | レビュー詳細 |

## 環境変数

| 変数 | デフォルト | 説明 |
|---|---|---|
| `OPENAI_API_KEY` | — | Juror A（GPT-4o） |
| `ANTHROPIC_API_KEY` | — | Juror B（Claude Haiku 4.5） |
| `GOOGLE_API_KEY` | — | Juror C + Final Judge |
| `AUTO_APPROVE_THRESHOLD` | 90 | 自動承認閾値 |
| `AUTO_REJECT_THRESHOLD` | 50 | 自動拒否閾値 |
| `SECURITY_GATE_MAX_PROMPTS` | 10 | Security Gate 最大プロンプト数 |
| `AGENT_CARD_ACCURACY_MAX_SCENARIOS` | 3 | 機能テスト最大シナリオ数 |
| `JURY_USE_COLLABORATIVE` | true | 協調評価の有効化 |
| `JURY_MAX_DISCUSSION_ROUNDS` | 3 | 最大討議ラウンド数 |
| `JURY_FINAL_JUDGE_MODEL` | gemini-2.5-pro | Final Judge モデル |
| `DATABASE_URL` | sqlite:///./agent_store.db | DB 接続 URL |
| `URL_PREFIX` | "" | リバースプロキシプレフィックス（Cloud Run: `/store`） |
| `WANDB_API_KEY` | — | 設定時に W&B Weave トレーシング有効化 |

全環境変数の詳細は [docs/trusted_agent_store_design.md](../docs/trusted_agent_store_design.md) を参照してください。
