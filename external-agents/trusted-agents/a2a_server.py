"""Custom A2A Server for external agents.

Google ADK の adk api_server --a2a の代替として動作するカスタムA2Aサーバー。
セッションを永続化してマルチターン会話に対応し、エージェントが生成した
Artifact を TaskArtifactUpdateEvent (FilePart / FileWithBytes) として返す。

変更理由:
- adk api_server --a2a は _pending_artifacts の収集機能を持たない
- 本サーバーでは get_pending_artifacts() で収集した Artifact を
  A2A プロトコルの FilePart として返す（テキスト埋め込みは行わない）
"""

import importlib.util
import json
import logging
import sys
import uuid
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse

from a2a.server.apps.jsonrpc.starlette_app import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.agent_execution import AgentExecutor
from a2a.types import (
    AgentCard, Artifact, FilePart, FileWithBytes, Message, Part,
    TaskArtifactUpdateEvent, TextPart,
)
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ADKAgentExecutor(AgentExecutor):
    """永続ランナーを持つA2Aエグゼキューター。

    - InMemoryRunner をインスタンスごとに1回だけ生成（セッション継続のため）
    - context_id をセッションIDとして使用（マルチターン対応）
    - エージェントの _pending_artifacts を FilePart として TaskArtifactUpdateEvent で送信
    """

    def __init__(self, adk_agent, agent_name: str, agent_module=None):
        self.adk_agent = adk_agent
        self.agent_name = agent_name
        self.agent_module = agent_module
        self._runner = None  # 遅延初期化・以降再利用

    def _get_runner(self):
        """InMemoryRunner を取得（初回のみ生成）。"""
        if self._runner is None:
            try:
                from google.adk.agents import InMemoryRunner
            except ImportError:
                try:
                    from google.adk.runners import InMemoryRunner
                except ImportError:
                    from google.adk import Runner as InMemoryRunner
            self._runner = InMemoryRunner(
                agent=self.adk_agent,
                app_name=self.agent_name,
            )
            logger.info(f"InMemoryRunner created for agent: {self.agent_name}")
        return self._runner

    async def execute(self, context, event_queue):
        """エージェントを実行し、レスポンスと Artifact を送信する。"""
        # ユーザーメッセージを取得
        user_message = ""
        if hasattr(context, "get_user_input"):
            user_message = context.get_user_input()
        if not user_message and hasattr(context, "message") and context.message:
            for part in context.message.parts:
                root = getattr(part, "root", part)
                if hasattr(root, "text") and root.text:
                    user_message = root.text
                    break

        if not user_message:
            user_message = "Hello"

        # マルチターン対応: context_id をセッションIDに使用
        session_id = context.context_id or f"session_{self.agent_name}"
        user_id = "a2a_user"

        logger.info(
            f"[{self.agent_name}] execute: session={session_id}, "
            f"msg={user_message[:80]!r}"
        )

        runner = self._get_runner()
        collected_parts: list[str] = []

        try:
            # セッションが存在しない場合は作成（adk api_server --a2a と同じ挙動）
            session = await runner.session_service.get_session(
                app_name=runner.app_name,
                user_id=user_id,
                session_id=session_id,
            )
            if session is None:
                await runner.session_service.create_session(
                    app_name=runner.app_name,
                    user_id=user_id,
                    session_id=session_id,
                    state={},
                )
                logger.info(f"[{self.agent_name}] Session created: {session_id}")

            # Phase 1: エージェントを実行してテキストを収集
            from google.genai import types as genai_types
            content = genai_types.Content(
                parts=[genai_types.Part(text=user_message)],
                role="user",
            )
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=content,
            ):
                if hasattr(event, "content") and event.content:
                    for part in event.content.parts or []:
                        if hasattr(part, "text") and part.text:
                            collected_parts.append(part.text)

            # Phase 2: ツール実行完了後に Artifact を収集
            artifacts = self._collect_artifacts()

            # テキストレスポンスを構築
            final_text = "\n".join(collected_parts) if collected_parts else "(no response)"

            # Phase 2.5: Artifact 情報をテキストに埋め込む
            # ADK RemoteA2aAgent は TaskArtifactUpdateEvent を ADK Event に変換しない
            # 可能性があるため、テキスト内に [A2A Artifacts] セクションを付加して
            # evaluation-runner の _parse_artifacts_from_text() で確実に検出させる。
            # メタデータに加え、デコード済みコンテンツプレビューも含めて
            # セキュリティ分析（MIME偽装・PII・Prompt Injection 検知）を可能にする。
            if artifacts:
                import base64 as _b64
                lines = ["\n\n[A2A Artifacts]"]
                for art in artifacts:
                    name = art.get("name", "artifact")
                    for part_data in art.get("parts", []):
                        mime = part_data.get("mimeType", "application/octet-stream")
                        data_b64 = part_data.get("data", "")
                        size = len(data_b64) * 3 // 4  # base64→bytes概算
                        lines.append(f"- {name}: mime_type={mime}, size={size} bytes")
                        # コンテンツプレビュー（先頭500文字）をセキュリティ検査用に付加
                        # 改行を \\n にエスケープして1行テキストとして埋め込む
                        # （パーサーが行単位で解析するため）
                        try:
                            decoded = _b64.b64decode(data_b64).decode("utf-8", errors="replace")
                            preview = decoded[:500].replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")
                            lines.append(f"  content_preview: {preview}")
                        except Exception:
                            lines.append("  content_preview: (binary data)")
                final_text += "\n".join(lines)
                logger.info(
                    f"[{self.agent_name}] Embedded {len(artifacts)} artifact(s) "
                    f"in text response as [A2A Artifacts] section (with content preview)"
                )

            await event_queue.enqueue_event(
                Message(message_id=str(uuid.uuid4()), role="agent", parts=[TextPart(text=final_text)])
            )

            # Phase 3: Artifact を FilePart として TaskArtifactUpdateEvent で送信
            task_id = context.task_id
            context_id = context.context_id
            if artifacts and task_id and context_id:
                for art in artifacts:
                    a2a_parts: list[Part] = []
                    for part_data in art.get("parts", []):
                        mime_type = part_data.get("mimeType", "application/octet-stream")
                        data_b64 = part_data.get("data", "")
                        file_name = art.get("name", "artifact")
                        a2a_parts.append(
                            Part(root=FilePart(
                                file=FileWithBytes(
                                    bytes=data_b64,
                                    mime_type=mime_type,
                                    name=file_name,
                                )
                            ))
                        )
                    a2a_artifact = Artifact(
                        artifact_id=str(uuid.uuid4()),
                        name=art.get("name", "artifact"),
                        parts=a2a_parts,
                        metadata=art.get("metadata"),
                    )
                    await event_queue.enqueue_event(
                        TaskArtifactUpdateEvent(
                            task_id=task_id,
                            context_id=context_id,
                            artifact=a2a_artifact,
                            last_chunk=True,
                        )
                    )
                    logger.info(
                        f"[{self.agent_name}] Artifact sent: {art.get('name')} "
                        f"({art.get('parts', [{}])[0].get('mimeType', '?')})"
                    )
            elif artifacts:
                logger.warning(
                    f"[{self.agent_name}] {len(artifacts)} artifacts collected but "
                    f"task_id/context_id unavailable — skipped"
                )

        except Exception as e:
            logger.error(f"[{self.agent_name}] Error: {e}", exc_info=True)
            await event_queue.enqueue_event(
                Message(message_id=str(uuid.uuid4()), role="agent", parts=[TextPart(text=f"Error: {e}")])
            )

    def _collect_artifacts(self) -> list:
        """エージェントモジュールから pending artifacts を収集する。"""
        if self.agent_module and hasattr(self.agent_module, "get_pending_artifacts"):
            try:
                arts = self.agent_module.get_pending_artifacts()
                if arts:
                    logger.info(f"[{self.agent_name}] Collected {len(arts)} artifacts")
                return arts
            except Exception as e:
                logger.warning(f"[{self.agent_name}] Failed to collect artifacts: {e}")
        return []

    async def cancel(self, context, event_queue):
        pass


def load_agent_card(agent_dir: Path, base_url: str) -> tuple[AgentCard, dict]:
    """agent.json から AgentCard と 生データ dict を読み込む。

    Returns:
        tuple of (AgentCard, raw_data_dict):
            - AgentCard: A2Aライブラリ用の型付きオブジェクト（RPC処理で使用）
            - raw_data_dict: agent.json の全フィールドを保持した dict
              （useCases 等、AgentCard Pydantic モデルが extra="ignore" で
               落としてしまうフィールドを /.well-known/agent-card.json で返すために使用）
    """
    card_path = agent_dir / "agent.json"
    with open(card_path) as f:
        data = json.load(f)
    agent_name = agent_dir.name
    data["url"] = f"{base_url}/a2a/{agent_name}"
    return AgentCard(**data), data


def create_app(host: str, port: int, agents_dir: Path) -> Starlette:
    """全エージェントを含む Starlette アプリを生成する。"""
    routes = []
    base_url = f"http://{host}:{port}"

    for agent_path in sorted(agents_dir.iterdir()):
        if not agent_path.is_dir():
            continue
        if agent_path.name.startswith((".", "__")):
            continue
        if not (agent_path / "agent.json").exists():
            continue

        agent_name = agent_path.name
        logger.info(f"Loading agent: {agent_name}")

        try:
            agent_card, raw_card_data = load_agent_card(agent_path, base_url)

            # useCases 等を含む生データで agent-card.json を返すカスタムルート
            # （AgentCard Pydantic モデルは useCases を extra="ignore" で落とすため）
            _raw = raw_card_data  # クロージャ用

            async def agent_card_endpoint(request, _data=_raw):
                return JSONResponse(_data)

            card_url = f"/a2a/{agent_name}{AGENT_CARD_WELL_KNOWN_PATH}"
            routes.append(Route(card_url, agent_card_endpoint))

            # エージェントモジュールを独立した名前空間でロード
            agent_py = agent_path / "agent.py"
            module_name = f"agent_{agent_name}"
            spec = importlib.util.spec_from_file_location(module_name, str(agent_py))
            agent_module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = agent_module
            sys.path.insert(0, str(agent_path))
            try:
                spec.loader.exec_module(agent_module)
            finally:
                sys.path.pop(0)

            adk_agent = agent_module.root_agent
            executor = ADKAgentExecutor(adk_agent, agent_name, agent_module=agent_module)
            handler = DefaultRequestHandler(agent_executor=executor, task_store=None)
            a2a_app = A2AStarletteApplication(agent_card=agent_card, http_handler=handler)
            agent_routes = a2a_app.routes(
                rpc_url=f"/a2a/{agent_name}",
                # agent-card.json はカスタムルートで上書き済みなので
                # A2Aライブラリのルートも登録するが、先に登録したカスタムルートが優先される
                agent_card_url=f"/a2a/{agent_name}{AGENT_CARD_WELL_KNOWN_PATH}",
            )
            routes.extend(agent_routes)
            logger.info(f"Agent loaded: /a2a/{agent_name} (useCases preserved: {bool(raw_card_data.get('useCases'))})")

        except Exception as e:
            logger.error(f"Failed to load agent {agent_name}: {e}", exc_info=True)

    async def root(request):
        return JSONResponse({
            "status": "ok",
            "agents": [r.path for r in routes if "agent-card.json" in r.path],
        })

    routes.insert(0, Route("/", root))
    return Starlette(routes=routes)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Custom A2A Server for external agents")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("agents_dir", type=Path)
    args = parser.parse_args()

    if not args.agents_dir.exists():
        logger.error(f"Agents directory not found: {args.agents_dir}")
        sys.exit(1)

    app = create_app(args.host, args.port, args.agents_dir)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
