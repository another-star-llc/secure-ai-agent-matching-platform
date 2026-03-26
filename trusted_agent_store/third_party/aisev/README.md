# AISI Security Evaluation Datasets

Japan AI Safety Institute (AISI) の「AIセーフティに関する評価観点ガイド」に基づく評価データセットです。

## 出典

- リポジトリ: https://github.com/Japan-AISI/aisev
- ライセンス: Apache License 2.0

## 含まれるデータセット

| ファイル | 観点 | 件数 |
|---|---|---|
| `01_aisi_toxic_v0.1.csv` | 有害コンテンツ生成 | 約43K |
| `02_aisi_misinformation_v0.1.csv` | 偽誤情報 | — |
| `03_aisi_fairness_v0.1.csv` | 公平性・バイアス | 約34K |
| `06_aisi_security_v0.1.csv` | セキュリティ（プロンプトリーク等） | 8 |
| `07_aisi_explainability_v0.1.csv` | 説明可能性 | — |
| `08_aisi_robustness_v0.1.csv` | ロバスト性・敵対的攻撃 | 約5.2K |

## 更新方法

最新データセットは上記リポジトリから取得できます:

```bash
git clone --depth 1 https://github.com/Japan-AISI/aisev.git /tmp/aisev
cp /tmp/aisev/backend/dataset/output/*.csv trusted_agent_store/third_party/aisev/
rm -rf /tmp/aisev
```
