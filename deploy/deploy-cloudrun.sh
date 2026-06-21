#!/bin/bash
# Cloud Run deployment script
# Usage:
#   ./deploy/deploy-cloudrun.sh
#
# 動作:
#   - .env から GCP メタ（GCP_PROJECT_ID / GCP_REGION / SERVICE_NAME）を読み込む
#   - .env の他の変数を Cloud Run の環境変数として注入（--env-vars-file、平打ち）
#     ※ 除外: DATABASE_URL / PYTHONPATH（Docker/supervisordで設定済み）、
#              GOOGLE_APPLICATION_CREDENTIALS（Cloud RunはADC自動）、デプロイ用メタ
#   - DEPLOY_SERVICE_ACCOUNT を設定すると、その専用SAでサービスを実行（未設定ならデフォルトCompute SA）
#
# 専用SA(B)に切り替える例:
#   DEPLOY_SERVICE_ACCOUNT=audit-pipeline@<PROJECT>.iam.gserviceaccount.com ./deploy/deploy-cloudrun.sh

set -e

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Load .env (GCPメタ取得用)
# 既に設定済みの環境変数は上書きしない＝コマンドライン指定（例 SERVICE_NAME=... ）を優先する。
if [ -f .env ]; then
    while IFS= read -r _line || [ -n "$_line" ]; do
        case "$_line" in ''|'#'*) continue ;; esac
        _key="${_line%%=*}"
        if [[ "$_key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] && [ -z "${!_key+x}" ]; then
            export "$_key=${_line#*=}"
        fi
    done < .env
    unset _line _key
fi

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:?GCP_PROJECT_ID is required}"
REGION="${GCP_REGION:-asia-northeast1}"
SERVICE_NAME="${SERVICE_NAME:-secure-mediation-a2a-platform}"
# 専用SAを使う場合のみ設定（未設定ならデフォルトCompute SAのまま＝現状維持）
DEPLOY_SERVICE_ACCOUNT="${DEPLOY_SERVICE_ACCOUNT:-}"

IMAGE_BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/secure-mediation-agent/${SERVICE_NAME}"
IMAGE_TAG="v$(date +%Y%m%d-%H%M%S)"
IMAGE_NAME="${IMAGE_BASE}:${IMAGE_TAG}"

echo "Deploying to Cloud Run"
echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
echo "Image: ${IMAGE_NAME}"

# --- .env から Cloud Run 用 env YAML を生成（平打ち、安全にエスケープ） ---
# json.dump で各値をクォート/エスケープするため、カンマやJSONを含む値でも壊れない。
ENV_YAML="$(mktemp -t cloudrun-env-XXXXXX.yaml)"
trap 'rm -f "$ENV_YAML"' EXIT

python3 - "$ENV_YAML" <<'PY'
import sys, json

out_path = sys.argv[1]
# Docker/supervisordで設定済み・Cloud Runでは不要/危険なキーは除外
exclude = set("""
DATABASE_URL PYTHONPATH GOOGLE_APPLICATION_CREDENTIALS
GCP_PROJECT_ID GCP_REGION SERVICE_NAME DEPLOY_SERVICE_ACCOUNT
""".split())

pairs = {}
with open(".env", encoding="utf-8") as f:
    for line in f:
        raw = line.rstrip("\n")
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in raw:
            continue
        key, val = raw.split("=", 1)
        key = key.strip()
        if not key or key in exclude:
            continue
        val = val.strip()
        # .env 側で値をクォート囲みしている場合は外す
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        pairs[key] = val

# Cloud Run --env-vars-file は YAML マップ。 "KEY": "VALUE" は valid YAML。
with open(out_path, "w", encoding="utf-8") as w:
    for k, v in pairs.items():
        w.write(json.dumps(k) + ": " + json.dumps(v) + "\n")

print(f"[env] {len(pairs)} 変数を Cloud Run に注入します", file=sys.stderr)
PY

# Build and push（Cloud Build でクラウド側ビルド）
# - amd64 でネイティブビルドされるため Apple Silicon(arm64) の exec format error を回避
# - ローカル Docker / ディスクを使わない（容量不足も回避）
# - ビルド済みイメージは Artifact Registry に自動 push
# .dockerignore で .venv 等は除外済みのためアップロードは軽量。
gcloud builds submit \
    --project "${PROJECT_ID}" \
    --tag "${IMAGE_NAME}" \
    --timeout=3600s \
    .

# Deploy
DEPLOY_ARGS=(
    --image "${IMAGE_NAME}"
    --platform managed
    --region "${REGION}"
    --port 8080
    --memory 2Gi
    --cpu 1
    --min-instances 0
    --max-instances 1
    --timeout 3600s
    --concurrency 80
    --cpu-boost
    --allow-unauthenticated
    --env-vars-file "${ENV_YAML}"
)

if [ -n "${DEPLOY_SERVICE_ACCOUNT}" ]; then
    DEPLOY_ARGS+=( --service-account "${DEPLOY_SERVICE_ACCOUNT}" )
    echo "Service account: ${DEPLOY_SERVICE_ACCOUNT}（専用SA）"
else
    echo "Service account: デフォルトCompute SA（DEPLOY_SERVICE_ACCOUNT 未設定）"
fi

# 注意: --env-vars-file は環境変数を「全置換」します。
# .env に無い変数（コンソール等で手動設定したもの）は消えるため、必ず .env を最新にしてから実行してください。
gcloud run deploy "${SERVICE_NAME}" "${DEPLOY_ARGS[@]}"

echo "Deployed: $(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format 'value(status.url)')"
