"""
会議シミュレーションロジック
"""
import json
import os
import time
import uuid
from datetime import datetime, date

import anthropic


def _json_serial(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

def _dumps(data):
    return json.dumps(data, default=_json_serial)


class MeetingRoom:
    def __init__(self, persona_manager, data_dir=None):
        self.persona_manager = persona_manager
        if data_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            data_dir = os.path.join(base, "data", "meetings")
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = "claude-sonnet-4-20250514"
        self.sessions = {}

    def _stream_with_retry(self, max_tokens, system, messages, max_retries=3):
        """overloaded_errorの場合にリトライするストリーミング"""
        for attempt in range(max_retries):
            try:
                return self.client.messages.stream(
                    model=self.model, max_tokens=max_tokens,
                    system=system, messages=messages
                )
            except anthropic.APIStatusError as e:
                if 'overloaded' in str(e).lower() and attempt < max_retries - 1:
                    wait = (attempt + 1) * 10
                    print(f"API過負荷 リトライ {attempt+1}/{max_retries} ({wait}秒後)")
                    time.sleep(wait)
                else:
                    raise

    def create_session(self, topic, member_ids, user_id=None):
        session_id = str(uuid.uuid4())[:8]
        members = self.persona_manager.get_personas_by_ids(member_ids)
        facilitator = self.persona_manager.get_facilitator()
        session = {
            "session_id": session_id,
            "topic": topic,
            "members": members,
            "facilitator": facilitator,
            "messages": [],
            "created_at": datetime.now().isoformat(),
            "status": "active"
        }
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id):
        return self.sessions.get(session_id)

    def add_message(self, session_id, role, persona_id, content):
        session = self.sessions.get(session_id)
        if not session:
            return
        msg = {
            "id": str(uuid.uuid4())[:8],
            "role": role,
            "persona_id": persona_id,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        session["messages"].append(msg)
        self._save_session(session_id)
        return msg

    def generate_member_response_stream(self, session_id, persona_id, trigger_message=None):
        session = self.sessions.get(session_id)
        if not session:
            yield "data: [ERROR] セッションが見つかりません\n\n"
            return
        persona = self.persona_manager.get_persona(persona_id)
        if not persona:
            yield "data: [ERROR] ペルソナが見つかりません\n\n"
            return
        messages = self._build_conversation_history(session, persona_id, trigger_message)
        system_prompt = self.persona_manager.build_system_prompt(
            persona, session["topic"], session["members"]
        )
        try:
            full_response = ""
            with self._stream_with_retry(512, system_prompt, messages) as stream:
                for text in stream.text_stream:
                    full_response += text
                    yield f"data: {_dumps({'type': 'chunk', 'text': text, 'persona_id': persona_id})}\n\n"
            msg = self.add_message(session_id, "member", persona_id, full_response)
            yield f"data: {_dumps({'type': 'done', 'persona_id': persona_id, 'message': msg})}\n\n"
        except Exception as e:
            yield f"data: {_dumps({'type': 'error', 'message': str(e)})}\n\n"

    def generate_facilitator_response_stream(self, session_id):
        session = self.sessions.get(session_id)
        if not session:
            yield "data: [ERROR] セッションが見つかりません\n\n"
            return
        discussion_text = self._format_discussion(session)
        system_prompt = self.persona_manager.build_facilitator_prompt(
            session["facilitator"], session["topic"], discussion_text
        )
        try:
            full_response = ""
            with self._stream_with_retry(400, system_prompt, [{"role": "user", "content": "議論を整理して、次のステップを示してください。"}]) as stream:
                for text in stream.text_stream:
                    full_response += text
                    yield f"data: {_dumps({'type': 'chunk', 'text': text, 'persona_id': 'facilitator'})}\n\n"
            msg = self.add_message(session_id, "facilitator", "facilitator", full_response)
            yield f"data: {_dumps({'type': 'done', 'persona_id': 'facilitator', 'message': msg})}\n\n"
        except Exception as e:
            err_msg = str(e)
            if '401' in err_msg or 'authentication_error' in err_msg.lower() or 'invalid' in err_msg.lower() and 'key' in err_msg.lower():
                err_msg = "AIサービスの認証エラーです。APIキーをご確認ください。"
            elif 'overloaded' in err_msg.lower():
                err_msg = "AIサーバーが混雑しています。しばらく待ってから再試行してください。"
            yield f"data: {_dumps({'type': 'error', 'message': err_msg})}\n\n"

    def generate_auto_discussion_stream(self, session_id, rounds=1):
        session = self.sessions.get(session_id)
        if not session:
            yield "data: [ERROR] セッションが見つかりません\n\n"
            return
        for member in session["members"]:
            yield f"data: {_dumps({'type': 'speaking_start', 'persona_id': member['id']})}\n\n"
            yield from self.generate_member_response_stream(session_id, member["id"])

    def _build_conversation_history(self, session, current_persona_id, trigger=None):
        messages = []
        for msg in session["messages"][-10:]:
            persona = self.persona_manager.get_persona(msg["persona_id"])
            name = persona["name"] if persona else "参加者"
            if msg["persona_id"] == current_persona_id:
                messages.append({"role": "assistant", "content": msg["content"]})
            else:
                messages.append({"role": "user", "content": f"【{name}】{msg['content']}"})
        if trigger:
            messages.append({"role": "user", "content": trigger})
        elif not messages:
            messages.append({"role": "user", "content": f"議題「{session['topic']}」について、あなたの意見を述べてください。"})
        if messages and messages[-1]["role"] == "assistant":
            messages.append({"role": "user", "content": "続けて意見を述べてください。"})
        return messages

    def _format_discussion(self, session):
        lines = []
        for msg in session["messages"]:
            persona = self.persona_manager.get_persona(msg["persona_id"])
            name = persona["name"] if persona else msg["persona_id"]
            lines.append(f"{name}: {msg['content']}")
        return "\n".join(lines) if lines else "（まだ議論はありません）"

    def _save_session(self, session_id):
        session = self.sessions.get(session_id)
        if not session:
            return
        path = os.path.join(self.data_dir, f"{session_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session, f, ensure_ascii=False, indent=2, default=_json_serial)

    def get_session_summary(self, session_id):
        session = self.sessions.get(session_id)
        if not session:
            return {}
        return {
            "session_id": session["session_id"],
            "topic": session["topic"],
            "members": session["members"],
            "facilitator": session["facilitator"],
            "message_count": len(session["messages"]),
            "messages": session["messages"],
            "status": session["status"]
        }