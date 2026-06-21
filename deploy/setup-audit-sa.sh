#!/bin/bash
# 専用サービスアカウント(audit-pipeline)を CLI だけで作成・権限付与するスクリプト。
# コンソール作業は不要。
#
# 使い方:
#   PIPELINE_PROJECT=<パイプラインを動かすプロジェクトID> \
#   TENANT_PROJECT=<審査対象エージェントが動くプロジェクトID> \
#   DEPLOYER=<デプロイを実行する人/SAのメール> \
#   ./deploy/setup-audit-sa.sh
#
#   - TENANT_PROJECT 省略時は PIPELINE_PROJECT と同じとみなす
#   - DEPLOYER 省略時は actAs 権限付与をスキップ（後述の手順4を手動で）
#
# 完了後の切替:
#   DEPLOY_SERVICE_ACCOUNT=audit-pipeline@<PIPELINE_PROJECT>.iam.gserviceaccount.com \
#     ./deploy/deploy-cloudrun.sh

set -e

PIPELINE_PROJECT="${PIPELINE_PROJECT:?PIPELINE_PROJECT is required (SAを作るプロジェクトID)}"
TENANT_PROJECT="${TENANT_PROJECT:-$PIPELINE_PROJECT}"
SA_NAME="${SA_NAME:-audit-pipeline}"
DEPLOYER="${DEPLOYER:-}"
SA_EMAIL="${SA_NAME}@${PIPELINE_PROJECT}.iam.gserviceaccount.com"

echo "== 専用SAセットアップ =="
echo "SA:               ${SA_EMAIL}"
echo "作成先プロジェクト:  ${PIPELINE_PROJECT}"
echo "権限付与先(対象):   ${TENANT_PROJECT}"
echo ""

# 1. SAを作成（既に存在すればスキップ）
echo "[1/3] SAを作成..."
gcloud iam service-accounts create "${SA_NAME}" \
    --project="${PIPELINE_PROJECT}" \
    --display-name="Trusted Agent Store audit pipeline" \
    || echo "  既に存在するためスキップ: ${SA_EMAIL}"

# 2. Vertex AI 権限を付与（Gemini / Agent Engine 審査に必要）
echo "[2/3] roles/aiplatform.user を ${TENANT_PROJECT} に付与..."
gcloud projects add-iam-policy-binding "${TENANT_PROJECT}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/aiplatform.user" \
    --condition=None

# 3. デプロイ実行者が「このSAとして実行する」ための actAs 権限
#    （Cloud Run を --service-account 指定でデプロイするのに必須）
if [ -n "${DEPLOYER}" ]; then
    echo "[3/3] ${DEPLOYER} に iam.serviceAccountUser を付与（actAs）..."
    # DEPLOYER が人(ユーザー)かSAかを自動判定
    if [[ "${DEPLOYER}" == *".gserviceaccount.com" ]]; then
        MEMBER="serviceAccount:${DEPLOYER}"
    else
        MEMBER="user:${DEPLOYER}"
    fi
    gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
        --project="${PIPELINE_PROJECT}" \
        --member="${MEMBER}" \
        --role="roles/iam.serviceAccountUser"
else
    echo "[3/3] DEPLOYER 未指定のためスキップ。"
    echo "  デプロイ実行者に手動で actAs を付与してください:"
    echo "    gcloud iam service-accounts add-iam-policy-binding ${SA_EMAIL} \\"
    echo "      --project=${PIPELINE_PROJECT} \\"
    echo "      --member=\"user:<あなたのGoogleアカウント>\" \\"
    echo "      --role=\"roles/iam.serviceAccountUser\""
fi

echo ""
echo "完了。次のコマンドで専用SA運用に切り替えてデプロイできます:"
echo "  DEPLOY_SERVICE_ACCOUNT=${SA_EMAIL} ./deploy/deploy-cloudrun.sh"
