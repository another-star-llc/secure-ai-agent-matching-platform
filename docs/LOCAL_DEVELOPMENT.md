# ローカル環境での実行（開発者向け）

このドキュメントでは、ローカル環境でプラットフォームを実行する方法を説明します。

## 環境要件

- **OS**: macOS 12.0 以降 / Linux
- **Docker**: インストール済み
- **API キー**: Google (Gemini), OpenAI, Anthropic

## セットアップ手順

```bash
# 1. リポジトリをクローン
git clone <repository-url>
cd secure-ai-agent-matching-platform

# 2. 環境変数を設定
cp .env_sample .env
# .env を編集し、以下を設定:
#   - GOOGLE_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY（LLM API キー）
#   - GCP_PROJECT_ID（Docker イメージのタグに使用）
#   - DEV_MODE=true のままなら Firebase 認証をスキップ

# 3. ビルド & 起動
./deploy/run-local.sh

# ✅ ブラウザで http://localhost:8080 を開きます
```

Docker コンテナ内で nginx + 全サービスが起動し、1つのポート（8080）で全機能にアクセスできます。

## URL マッピング

| パス | サービス |
|---|---|
| http://localhost:8080/ | 仲介エージェント（ADK Web UI） |
| http://localhost:8080/store/ | エージェントストア |
| http://localhost:8080/store/submit | エージェント提出フォーム |
| http://localhost:8080/store/admin | 管理ダッシュボード |

## 認証について

- **ローカル開発**: `DEV_MODE=true` を設定すると Firebase 認証をバイパスできます（`.env_sample` のデフォルト）
- **本番/ステージング**: Firebase プロジェクトを作成し、`.env` に `FIREBASE_*` 環境変数を設定してください

## フロントエンドについて

UI はサーバーサイドの Jinja2 テンプレート + バニラ JavaScript で構成されています。
npm / Node.js のビルドステップは不要です。

## デモプロンプト例

仲介エージェント（http://localhost:8080/）で以下を入力:

```
沖縄旅行の予約をお願いします。
- 人数：2人
- フライト: 羽田→那覇 (12/20-12/23)
- ホテル: 那覇市内 3泊
- レンタカー: コンパクトカー

セキュリティチェックを行いながら実行プランを作成してください。
```

## トラブルシューティング

### ポートが使用中の場合

```bash
lsof -i :8080
kill -9 <PID>
```

### Docker ビルドのキャッシュをクリア

```bash
./deploy/run-local.sh --no-cache
```

### ビルド済みイメージで起動（再ビルドなし）

```bash
./deploy/run-local.sh --no-build
```

### コンテナのログを確認

```bash
docker logs -f secure-platform
```

## 関連ドキュメント

- [アーキテクチャ詳細](secure_mediation_agent_design/ARCHITECTURE.md)
- [エージェントストア設計](trusted_agent_store_design.md)
- [エージェントストア README](../trusted_agent_store/README.md)
