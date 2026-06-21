# 稼働中A2Aエージェント一覧（新仕様 `agent-card.json`）

調査日: 2026-06-18
出典: [A2A Registry API](https://a2aregistry.org/api/agents?conformance=standard) のライブデータ＋各Agent Cardの実取得で検証。
稼働率（uptime）・応答時間・ヘルス状態はレジストリの30分ごとヘルスチェックに基づく実測値。

## 疎通検証結果（2026-06-18 実測）

ブラウザ経由で各エンドポイントへ実際に `message/send`（JSON-RPC 2.0）をPOSTした結果。

| エージェント | Card取得(GET) | message/send(POST) | 結果 | デモ可否 |
|---|---|---|---|---|
| **agent-ready** | ✅ 200 | ✅ 200 | 正常な `message` 応答を返却（認証なし） | ◎ 最有力 |
| **LogicNodes** | ✅ 200 | ✅ 200 | `task: completed`＋capability resolution応答（認証なし） | ◎ |
| **Packrift** | ✅ 200 | ✅ 200 | `task: completed`＋調達ルーティング応答（認証なし） | ◎ |
| **MoveHome.org** | ✅ 200 | ✅ 200 | A2A準拠で疎通OK。ただし構造化DataPart（`skill`＋正確なparams）必須。フリーテキスト/推測paramsは`failed`で弾かれる | ○（要スキーマ） |
| **Agoragentic** | ✅ 200 | 未実行 | スキル実行が apiKey / x402 ゲート。Card到達は確認済み | △（要認証/課金） |
| **AIScan** | ✅ 200 | 未実行 | スキル実行が x402 課金ゲート | △（要課金） |
| **PostalForm** | ✅ 200 | 未実行 | 実発送系はx402/MPP。proto 1.0 | △（要課金） |

**結論**: 明日のVCデモは **agent-ready.dev / LogicNodes / Packrift** の3つが認証・課金なしで即疎通できる本命。MoveHomeは正確なparamスキーマを用意できれば追加可。

---

## 凡例（課金列）

- **無料**: x402等の決済ゲートを検出せず。認証なしで疎通できる可能性が高い（本番前に要 `curl` 確認）。
- **有料(x402)**: スキル実行が x402（Base上のUSDC決済）でゲートされている。Agent Card取得・疎通自体は可能だが、実スキル応答には支払いが必要。
- **一部無料**: 無料枠あり、または一部スキルのみ無料。

> デモで「`message/send` を投げて応答を引き出す」なら、**無料** または **一部無料** を選ぶのが安全です。

## 推奨（デモ疎通向け・新パス・稼働確認済み）

| エージェント | Agent Card (新パス) | A2Aエンドポイント | proto | 稼働 | uptime | 応答 | 課金 | 備考 |
|---|---|---|---|---|---|---|---|---|
| **agent-ready** | https://agent-ready.dev/.well-known/agent-card.json | https://agent-ready.dev/api/v1/a2a | 0.3.0 | ✅ | 100% | 659ms | 無料 | `application/a2a+json`配信。疎通検証向きの最有力 |
| **LogicNodes** | https://logicnodes.io/.well-known/agent-card.json | https://logicnodes.io/a2a | 0.3.0 | ✅ | 100% | 805ms | 一部無料 | bonded-verdict等が無料5回/日/IP、以降$0.05(x402) |
| **AIScan** | https://getaiscan.app/.well-known/agent-card.json | https://api.getaiscan.app/a2a | 0.3.0 | ✅ | 100% | 432ms | 有料(x402) | 最速。18スキル。0.06〜3.50 USDC |
| **Agoragentic** | https://agoragentic.com/.well-known/agent-card.json | https://agoragentic.com/api/a2a | 0.3.0 | ✅ | 100% | 754ms | 有料(x402) | |
| **Packrift** | https://packrift-agent-discovery-hub.vercel.app/.well-known/agent-card.json | https://packrift-agent-discovery-hub.vercel.app/api/a2a | 0.3.0 | ✅ | 100% | 874ms | 無料 | 梱包調達ルーター |
| **MoveHome.org** | https://movehome.org/.well-known/agent-card.json | https://movehome.org/api/a2a | 0.3.0 | ✅ | 100% | 1033ms | 無料 | 不動産 |
| **PostalForm** | https://postalform.com/.well-known/agent-card.json | https://postalform.com/a2a | 1.0 | ✅ | 100% | 1161ms | 有料(x402) | proto 1.0 |

## その他の稼働中エージェント（新パス）

| エージェント | Agent Card (新パス) | A2Aエンドポイント | proto | 稼働 | uptime | 応答 | 課金 | 備考 |
|---|---|---|---|---|---|---|---|---|
| PoolParty Agent Concierge | https://www.poolparty.io/.well-known/agent-card.json | https://www.poolparty.io/api/a2a | 0.3.0 | ✅ | 100% | 1452ms | 無料 | |
| marginalia | https://marginalia.polycode.co.uk/.well-known/agent-card.json | https://marginalia.polycode.co.uk/api/a2a | 0.3.0 | ✅ | 100% | 1446ms | 無料 | |
| iwant-marketplace | https://iwant.fyi/.well-known/agent-card.json | https://iwant.fyi/api/a2a | 0.3.0 | ✅ | 100% | 2479ms | 無料 | マーケットプレイス |
| Mobility Quote Agent | https://212-47-77-33.sslip.io/.well-known/agent-card.json | https://212-47-77-33.sslip.io/ | 0.3.0 | ✅ | 100% | 2041ms | 無料 | IP直/sslip.io |
| AgentSearch | https://agentsearch.luthersystems.com/.well-known/agent-card.json | https://agentsearch.luthersystems.com/api/a2a | 0.3.0 | ✅ | 100% | 3092ms | 無料 | |
| ANP2 Network Relay | https://anp2.com/.well-known/agent-card.json | https://anp2.com/api/a2a | 0.3.0 | ✅ | 100% | 3422ms | 無料 | |
| GitDealFlow Signal Agent | https://signals.gitdealflow.com/.well-known/agent-card.json | https://signals.gitdealflow.com/api/a2a | 0.3.0 | ✅ | 100% | 1998ms | 無料 | |
| PartsTable Intelligence | https://partsiq-api.onrender.com/.well-known/agent-card.json | https://partsiq-api.onrender.com/a2a | 0.3.0 | ✅ | 100% | 2592ms | 無料 | |
| Perkoon — Agent Data Layer | https://perkoon.com/.well-known/agent-card.json | https://perkoon.com/a2a | 0.3.0 | ✅ | 100% | 3511ms | 無料 | |
| ARCASOS Short-Term Rental | https://arcasos.com/.well-known/agent-card.json | https://queehgaoooupmvindevw.supabase.co/functions/v1/agent-message-send | 0.3.0 | ✅ | 100% | 3525ms | 無料 | エンドポイントはSupabase Functions |
| SwarmSync Commerce Demo | https://swarmsync-agents.onrender.com/.well-known/agent.json | https://swarmsync-agents.onrender.com/a2a | 0.3.0 | ✅ | 100% | 2227ms | 無料 | ⚠️旧パス(agent.json) |
| MERCURY Web Fetch | https://network.mercury-hq.com/.well-known/agent-card.json | https://network.mercury-hq.com/a2a | 0.3.0 | ✅ | 98% | 1008ms | 有料(x402) | |
| HexNest | https://hex-nest.com/.well-known/agent-card.json | http://127.0.0.1:10000/a2a | 0.3.0 | ✅ | 100% | 3377ms | 無料 | ⚠️url が localhost。疎通不可の恐れ |

## 参考・除外（デモ非推奨）

| エージェント | Agent Card | 課金 | 除外理由 |
|---|---|---|---|
| Torify | https://torify.dev/.well-known/agent.json | 有料(x402) | ⚠️旧仕様(agent.json)。ご指摘どおり |
| InsideOut | https://insideout.luthersystems.com/.well-known/agent.json | 無料 | ⚠️旧仕様(agent.json), proto 0.3 |
| Zee | https://p0stman.com/.well-known/agent.json | 無料 | ⚠️旧仕様(agent.json) |
| Korean Public Data Agent | https://publicdata-agent.songt50.us/.well-known/agent.json | 無料 | ❌非稼働(health=false, uptime81%), 旧パス |
| Korean News Agent | https://news-agent.songt50.us/.well-known/agent.json | 無料 | ❌非稼働(health=false, uptime81%), 旧パス |

## 疎通テストコマンド

```bash
# 1) Agent Card取得（新パス）
curl https://agent-ready.dev/.well-known/agent-card.json

# 2) A2A message/send（JSON-RPC 2.0）
curl -X POST https://agent-ready.dev/api/v1/a2a \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"message/send",
       "params":{"message":{"role":"user",
       "parts":[{"kind":"text","text":"hello"}],
       "messageId":"demo-1"}}}'

# 3) レジストリから生きてるエージェントを動的に取得
curl "https://a2aregistry.org/api/agents?conformance=standard&limit=50"
```

---
注: 課金列の「無料」は x402 等の決済ゲートを検出しなかったことを示すもので、認証不要を保証するものではありません。本番デモ前に必ず実際に `curl` で応答確認してください（クラウド稼働のため瞬断の可能性あり。本命1＋予備2を推奨）。
