# Gemini Enterprise エージェントを審査パイプラインで評価する手順書

最終更新: 2026-06-21
対象読者: Trusted Agent Store を運用し、Gemini Enterprise（Vertex AI Agent Engine ホスト）の
A2A エージェントを審査対象に加えたい担当者

---

## 0. 前提と全体像

審査パイプラインは「公開A2AエンドポイントのカードURLを提出 → カードからA2Aエンドポイントを取得 →
`message/send` で評価」という設計。一方 Gemini Enterprise / Agent Engine のエージェントは、

- 公開 Agent Card を配信しない（認証付き `{a2a_url}/v1/card` で取得）
- エンドポイントが Google IAM/OAuth で保護されている

ため、**「外から無記名で」叩けない**。よって審査パイプラインの実行サービスアカウント（SA）に
**テナント側プロジェクトへのアクセス権限を持たせ、内側から認証付きで叩く**必要がある。

必要ロール: **`roles/aiplatform.user`（Vertex AI ユーザー）**
有効化スイッチ（実装済み）: 環境変数 **`GEMINI_A2A_GOOGLE_AUTH=true`**（または明示トークン `SECURITY_ENDPOINT_TOKEN`）

---

## パート A: Gemini Enterprise に登録してストアを見る

「まず見るだけ」なら Business版の30日無料トライアルが最短。

1. [business.gemini.google](https://business.gemini.google/) で「無料トライアル」を開始し、ビジネスGoogleアカウントでサインイン。
2. 席数（自分1席でOK）・請求期間・国・連絡先を入力して開始。
3. Gemini Enterprise アプリ（web）を開く。
4. 左ナビの **「Agents」** をクリック → Agent Gallery が開く。
5. ギャラリーの4区分（Made by Google / From your organization / Your agents / **Marketplace**）のうち
   **Marketplace** で、業種・ユースケース・「Gemini Enterprise互換」等で検索・閲覧。
6. 使いたいエージェント名をクリック → **Request access**（管理者承認。自分が管理者なら自分で承認）。

本格運用（Standard/Plus）の場合:

1. Google Cloud コンソール → Gemini Enterprise → **Manage subscriptions → Create subscription** → エディション選択 → Subscribe。
2. ユーザーにライセンス割当。
3. 管理者が Marketplace エージェントを追加: Gemini Enterprise ページ → アプリ → **Agents → Add Agents** →
   「**Agents via Marketplace**」→ 検索 → Next → 詳細確認 → 認証情報入力 → Finish。

参考:
- Sign up for a free trial (Business): https://support.google.com/g/answer/16547933?hl=en
- Browse agents with Agent Gallery: https://docs.cloud.google.com/gemini/enterprise/docs/agent-gallery
- Add and manage A2A agents from Cloud Marketplace: https://docs.cloud.google.com/gemini/enterprise/docs/register-and-manage-marketplace-agents

---

## パート B: 審査パイプラインから審査できるようにする（SA権限付与）

### B-1. 準備（控えておく値）

- `TENANT_PROJECT` … 対象エージェントが動くプロジェクトID（Gemini Enterprise テナント側）
- `PIPELINE_PROJECT` … 審査パイプラインを動かすプロジェクトID
- `REGION` / `IMAGE` / `SERVICE_NAME` … Cloud Run デプロイ時の値
- 審査パイプラインの実行サービスアカウント（無ければ B-2 で作成）

> 同一プロジェクトで動かす場合は `TENANT_PROJECT` = `PIPELINE_PROJECT` でよい。

### B-2. サービスアカウントを用意する

```bash
gcloud iam service-accounts create audit-pipeline \
  --project=PIPELINE_PROJECT \
  --display-name="Trusted Agent Store audit pipeline"
```

生成されるメール例: `audit-pipeline@PIPELINE_PROJECT.iam.gserviceaccount.com`

### B-3. SAに権限（社員証）を付与する ★核心

対象エージェントのプロジェクトに `roles/aiplatform.user` を付与:

```bash
gcloud projects add-iam-policy-binding TENANT_PROJECT \
  --member="serviceAccount:audit-pipeline@PIPELINE_PROJECT.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

### B-4. パイプラインがそのSAで認証（ADC）するようにする

**Cloud Run で動かす場合（推奨）** — SAを紐付ければADCは自動:

```bash
gcloud run deploy SERVICE_NAME \
  --service-account=audit-pipeline@PIPELINE_PROJECT.iam.gserviceaccount.com \
  --region=REGION --image=IMAGE \
  --update-env-vars GEMINI_A2A_GOOGLE_AUTH=true
```

**ローカルで動かす場合** — どちらか:

- 自分の権限で試す: `gcloud auth application-default login`
- SAキーを使う（キーは秘密。コミット禁止・Secret Manager推奨）:
  ```bash
  gcloud iam service-accounts keys create key.json \
    --iam-account=audit-pipeline@PIPELINE_PROJECT.iam.gserviceaccount.com
  export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json
  ```

### B-5. 認証を有効化する（実装済みスイッチ）

`.env` に設定:

```
GEMINI_A2A_GOOGLE_AUTH=true
# 明示的なBearerトークンを使う場合のみ（OAuth2/APIキー等）。未設定なら無認証。
SECURITY_ENDPOINT_TOKEN=
```

- ローカル（`deploy/run-local.sh`）は `--env-file .env` で自動注入。
- Cloud Run は現行 `deploy-cloudrun.sh` が env を転送しないため、B-4 のように
  `--update-env-vars` で渡すか、`deploy-cloudrun.sh` を改修する。

### B-6. 対象エージェントを提出して審査

- Agent Engine エージェントの A2A エンドポイントURLを提出。
- パイプラインが自動で `{a2a_url}/v1/card` を認証付き取得 → `message/send` にBearer付与で Security Gate を実行。

### B-7. 動作確認

- 成功ログ: `A2A認証: Google ADC からアクセストークンを取得しました`
- 401/403 が出る場合のチェック:
  - B-3 のロール付与先プロジェクトが対象エージェントのプロジェクトと一致しているか（最頻ミス）
  - SAがADCとして実際に使われているか（Cloud Runの `--service-account`、ローカルのADC/キー）
  - 対象エンドポイントURLが正しいか（`/v1/card` が解決できるか）

---

## 実装側の対応箇所（参考）

今回の認証対応で変更したファイル:

- `trusted_agent_store/evaluation-runner/src/evaluation_runner/security_gate.py`
  … `build_a2a_auth_headers()` 追加、A2Aのカード取得・message/send にBearer注入
- `trusted_agent_store/evaluation-runner/src/evaluation_runner/card_url.py`
  … Agent Engine の `{a2a_url}/v1/card` を候補に追加
- `trusted_agent_store/evaluation-runner/src/evaluation_runner/agent_card_accuracy.py`
  … マルチターン対話にも認証注入
- `trusted_agent_store/app/routers/submissions.py`
  … `endpoint_token` を環境変数供給化、提出時カード取得にも認証付与
- `.env` / `.env_sample` … `GEMINI_A2A_GOOGLE_AUTH` / `SECURITY_ENDPOINT_TOKEN` を追記

---

## 注意 / 残課題

- 本手順は **Bearer/OAuth系認証**（Gemini Agent Engine の ADC トークン、または明示トークン）に対応。
- **AWS Bedrock AgentCore は SigV4署名**でBearerではないため、別途署名対応が必要。
- **x402 等の課金ゲート**は認証とは別問題（プリファンド監査ウォレット＋上限＋リベートの設計が別途必要）。
- より厳密には SA共有ではなく **エージェント単位の Agent Identity（最小権限）** が推奨。
  参考: https://cloud.google.com/agent-builder/agent-engine/agent-identity

## 参考リンク

- IAM roles and permissions (aiplatform): https://docs.cloud.google.com/iam/docs/roles-permissions/aiplatform
- Set up the environment — Vertex AI Agent Engine: https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/set-up
- Managing access for deployed agents: https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/manage/access
- Use an Agent2Agent agent — Agent Engine: https://docs.cloud.google.com/agent-builder/agent-engine/use/a2a
