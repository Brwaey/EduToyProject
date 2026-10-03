"""In-process dispatcher; network awaits NEVER hold a database transaction."""

import asyncio
import json
import logging

import httpx
from pydantic import ValidationError
from sqlalchemy import select, text, update

from .ai_credentials import decrypt
from .ai_data import input_rows, inputs_view, validate_output
from .ai_prompts import messages
from .db import now
from .models_ai import AIConfig, AISuggestion, AITask
from .security import Problem

log = logging.getLogger("yanji.ai")


async def request_model(endpoint, model, key, msgs, timeout):
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(
                follow_redirects=False,
                trust_env=False,
                timeout=httpx.Timeout(timeout, connect=min(10, timeout)),
            ) as client:
                async with client.stream(
                    "POST",
                    endpoint,
                    headers={"Authorization": "Bearer " + key},
                    json={"model": model, "messages": msgs, "stream": False},
                ) as response:
                    errors = {
                        401: ("ai_auth_failed", "模型鉴权失败，请检查 API Key"),
                        403: ("ai_auth_failed", "模型访问被拒绝，请检查权限"),
                        404: ("ai_not_found", "接口地址或模型不存在，请检查 URL 和模型名"),
                        429: ("ai_rate_limited", "模型服务限流，请稍后手动重试"),
                    }
                    if response.status_code in errors:
                        raise Problem(502, *errors[response.status_code])
                    if response.status_code >= 300:
                        raise Problem(
                            502,
                            "ai_http_error",
                            f"模型服务返回 HTTP {response.status_code}，请检查配置或稍后重试",
                        )
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 1048576:
                            raise Problem(502, "ai_response_too_large", "模型响应超过 1 MiB")
        result = json.loads(data)
        choice = result["choices"][0]
        if choice.get("finish_reason") in ("length", "content_filter") or choice["message"].get(
            "refusal"
        ):
            raise Problem(502, "ai_incomplete_output", "模型拒绝回答或输出被截断，请调整材料后重试")
        content = choice["message"].get("content")
        if not isinstance(content, str) or not content.strip():
            raise Problem(502, "ai_empty_output", "模型未返回可用文本")
        raw_usage = result.get("usage")
        usage = (
            {
                k: v
                for k, v in (raw_usage or {}).items()
                if k in ("prompt_tokens", "completion_tokens", "total_tokens")
                and isinstance(v, int)
                and not isinstance(v, bool)
                and v >= 0
            }
            if isinstance(raw_usage, dict)
            else None
        )
        return content, usage
    except (httpx.TimeoutException, TimeoutError):
        raise Problem(502, "ai_timeout", "模型请求超时，可缩小材料范围后手动重试") from None
    except httpx.HTTPError:
        raise Problem(502, "ai_connection_failed", "无法连接模型服务，请检查地址与网络") from None
    except (ValueError, KeyError, IndexError, TypeError):
        raise Problem(
            502, "ai_invalid_response", "模型服务未返回兼容的 Chat Completions 响应"
        ) from None


class AIWorker:
    def __init__(self, app):
        self.app = app
        self.running = {}
        self.dispatch = None
        self.stopping = False

    async def start(self):
        def recover():
            with self.app.state.sessions() as db:
                db.execute(text("BEGIN IMMEDIATE"))
                db.execute(
                    update(AITask)
                    .where(AITask.status == "running")
                    .values(
                        status="failed",
                        error_code="ai_interrupted",
                        error_message="服务已重启，先前请求已中断；请手动重试",
                        finished_at=now(),
                    )
                )
                db.commit()

        await asyncio.to_thread(recover)
        self.dispatch = asyncio.create_task(self.loop())

    async def stop(self):
        self.stopping = True
        if self.dispatch:
            self.dispatch.cancel()
            await asyncio.gather(self.dispatch, return_exceptions=True)
        for task in list(self.running.values()):
            task.cancel()
        await asyncio.gather(*self.running.values(), return_exceptions=True)

    def queue(self):
        with self.app.state.sessions() as db:
            live = list(
                db.scalars(
                    select(AITask)
                    .where(AITask.status.in_(["queued", "running"]))
                    .order_by(AITask.created_at, AITask.id)
                )
            )
            return [(t.id, t.owner_id, t.status) for t in live]

    async def loop(self):
        while True:
            try:
                live = await asyncio.to_thread(self.queue)
                live_ids = {t[0] for t in live}
                for key, task in list(self.running.items()):
                    if task.done():
                        self.running.pop(key)
                    elif key not in live_ids:
                        task.cancel()
                busy = {owner for tid, owner, status in live if tid in self.running}
                for tid, owner, status in live:
                    if status == "running" and tid not in self.running:
                        # Retry only the terminal database write, never the external call.
                        await asyncio.to_thread(
                            self.finish,
                            tid,
                            error=Problem(
                                503,
                                "database_busy",
                                "保存模型结果时数据库繁忙，任务已结束；请手动重试",
                            ),
                        )
                    if len(self.running) >= 2:
                        break
                    if status == "queued" and owner not in busy and tid not in self.running:
                        self.running[tid] = asyncio.create_task(self.run(tid))
                        busy.add(owner)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("AI dispatcher %s", type(exc).__name__)
            await asyncio.sleep(0.2)

    def claim(self, task_id):
        with self.app.state.sessions() as db:
            db.execute(text("BEGIN IMMEDIATE"))
            task = db.get(AITask, task_id)
            if task.status != "queued":
                return None
            try:
                c = db.get(AIConfig, task.owner_id)
                if not c or c.version != task.config_version:
                    raise Problem(409, "ai_config_changed", "模型配置已变化，请重新确认后重试")
                key = decrypt(self.app.state.settings, db, c)
                inputs = inputs_view(db, task.owner_id, input_rows(db, task.id))
                if any(o["deleted"] or o["archived"] for o in inputs["objects"]):
                    raise Problem(409, "ai_input_unavailable", "输入对象已删除或归档，请恢复后重试")
                payload = (task.endpoint, task.model, key, messages(task.kind, inputs))
                task.status = "running"
                task.started_at = now()
            except Problem as e:
                self.failure(task, e)
                payload = None
            db.commit()
            return payload

    @staticmethod
    def failure(task, e):
        task.status = "failed"
        task.error_code = e.code
        task.error_message = e.message
        task.finished_at = now()

    def finish(self, task_id, content=None, usage=None, error=None):
        with self.app.state.sessions() as db:
            db.execute(text("BEGIN IMMEDIATE"))
            task = db.get(AITask, task_id)
            if task.status != "running":
                return
            c = db.get(AIConfig, task.owner_id)
            try:
                if error:
                    raise error
                if task.kind != "connection_test":
                    inputs = inputs_view(db, task.owner_id, input_rows(db, task.id))
                    if any(o["deleted"] or o["archived"] for o in inputs["objects"]):
                        raise Problem(
                            409, "ai_input_unavailable", "输入对象已删除或归档，本次结果未保存"
                        )
                    outputs = validate_output(db, task, content)
                    db.add_all(
                        [
                            AISuggestion(
                                owner_id=task.owner_id, task_id=task.id, kind=task.kind, original=o
                            )
                            for o in outputs
                        ]
                    )
                task.status = "succeeded"
                task.usage = usage
                task.finished_at = now()
            except (ValidationError, ValueError, TypeError):
                self.failure(
                    task,
                    Problem(502, "ai_invalid_output", "模型输出结构不符合约定，请调整材料后重试"),
                )
            except Problem as e:
                self.failure(task, e)
            if c and c.version == task.config_version and task.kind == "connection_test":
                c.test_status = task.status
            db.commit()

    async def run(self, task_id):
        try:
            payload = await asyncio.to_thread(self.claim, task_id)
            if payload is None:
                return
            try:
                content, usage = await request_model(*payload, self.app.state.settings.ai_timeout)
                payload = None
                await asyncio.to_thread(self.finish, task_id, content, usage)
            except Problem as e:
                await asyncio.to_thread(self.finish, task_id, error=e)
        except asyncio.CancelledError:
            await asyncio.to_thread(
                self.finish, task_id, error=Problem(503, "ai_interrupted", "请求已中断，请手动重试")
            )
            raise
        except Exception as exc:
            log.error("AI task %s failed: %s", task_id, type(exc).__name__)
            await asyncio.to_thread(
                self.finish,
                task_id,
                error=Problem(503, "ai_internal_error", "任务暂时无法完成，请手动重试"),
            )
