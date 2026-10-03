"""Deterministic Chat Completions HTTP fixture, never imported by the application."""

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"fixture ready")

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.calls.append((self.path, self.headers.get("Authorization"), payload))
        model = payload["model"]
        if model in ("slow", "timeout"):
            time.sleep(2 if model == "slow" else 5)
        status = {
            "unauthorized": 401,
            "limited": 429,
            "missing": 404,
            "server-error": 500,
            "redirect": 302,
        }.get(model, 200)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if status != 200:
            self.wfile.write(b'{"error":"do not expose provider body or secret"}')
            return
        if len(payload["messages"]) == 1:
            content = "连接成功"
        else:
            data = json.loads(payload["messages"][-1]["content"])
            material = next(
                (
                    m
                    for m in data["materials"]
                    if next(o for o in data["objects"] if o["key"] == m["object_key"])["kind"]
                    == "record"
                ),
                data["materials"][0],
            )
            quote = material["text"][:40]
            cite = {"material": material["key"], "quote": quote, "occurrence": 1}
            if model == "badcite":
                cite["quote"] = "这句话并不存在于所选材料"
            if "未来行动建议" in payload["messages"][0]["content"]:
                candidate = {
                    "title": "补充一次对照",
                    "research_goal": "检验评估设置的影响",
                    "learning_goal": "练习实验设计",
                    "completion_criteria": "对比两组设置并记录差异",
                    "effort": "建议预留一小时，实际待确认",
                    "reason": "已有材料提示仍需检查条件",
                    "uncertainty": "能否获得数据尚待确认",
                    "citations": [cite],
                }
                content = {
                    "actions": []
                    if model == "empty-actions"
                    else [candidate] * (6 if model == "too-many-actions" else 1)
                }
            elif "辅助整理已保存的周期复盘" in payload["messages"][0]["content"]:
                content = {
                    "fields": {
                        "progress": {"value": quote, "citations": [cite]},
                        "blockers": {"value": "仍需核对条件", "citations": [cite]},
                        "next_steps": {"value": "建议继续核对条件", "citations": [cite]},
                    },
                    "questions": ["是否需要补充其他条件？"],
                }
            elif "整理已有探索卡" in payload["messages"][0]["content"]:
                content = {
                    "fields": {
                        "title": {"value": "整理后的实验记录", "citations": [cite]},
                        "observations": {"value": quote, "citations": [cite]},
                        "context": {"value": "", "citations": []},
                    },
                    "questions": ["后续准备如何复核？"],
                }
            elif "个人贡献候选" in payload["messages"][0]["content"]:
                content = {
                    "contributions": []
                    if model == "empty-contributions"
                    else [
                        {
                            "contribution_type": "validation",
                            "fields": {
                                "title": {"value": "补充了对照条件", "citations": [cite]},
                                "personal_role": {"value": "", "citations": []},
                            },
                            "uncertainty": "本人参与由用户核对",
                            "questions": ["具体核对了什么？"],
                        }
                    ]
                }
            else:
                content = {
                    "relations": []
                    if model == "empty-relations"
                    else [
                        {
                            "source": data["objects"][0]["key"],
                            "target": data["objects"][1]["key"],
                            "relation_type": "related",
                            "reason": "选定实验与研究问题相关",
                            "uncertainty": "仍需进一步验证",
                            "citations": [cite],
                        }
                    ]
                }
            content = json.dumps(content, ensure_ascii=False)
        if model == "invalid":
            content = "not valid JSON"
        result = {
            "choices": [
                {
                    "message": {"content": content},
                    "finish_reason": "length" if model == "truncated" else "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }
        raw = (
            b"not JSON"
            if model == "bad-response"
            else json.dumps(result, ensure_ascii=False).encode()
        )
        if model == "huge":
            raw = b"x" * 1048577
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass


def server(port=0):
    s = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    s.calls = []
    return s


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8099)
    server(parser.parse_args().port).serve_forever()
