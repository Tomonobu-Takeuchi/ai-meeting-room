"""
AI-PERSONA会議室 - メインサーバー
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, Response, jsonify, request, send_from_directory
from dotenv import load_dotenv

from src.persona.persona_manager import PersonaManager
from src.meeting.meeting_room import MeetingRoom

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web"),
    static_url_path=""
)

persona_manager = PersonaManager()
meeting_room = MeetingRoom(persona_manager)


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/api/personas", methods=["GET"])
def get_personas():
    return jsonify({"personas": persona_manager.to_dict_list()})

@app.route("/api/personas/members", methods=["GET"])
def get_members():
    return jsonify({"members": persona_manager.get_all_members()})

@app.route("/api/personas/add", methods=["POST"])
def add_persona():
    data = request.json
    if not data:
        return jsonify({"error": "データがありません"}), 400
    data.setdefault("role", "member")
    data.setdefault("avatar", "👤")
    data.setdefault("color", "#6B7280")
    data.setdefault("background", "")
    persona = persona_manager.add_custom_persona(data)
    return jsonify({"persona": persona})

@app.route("/api/personas/<persona_id>", methods=["PUT"])
def update_persona(persona_id):
    """ペルソナ情報を更新する"""
    data = request.json
    if not data:
        return jsonify({"error": "データがありません"}), 400
    updated = persona_manager.update_persona(persona_id, data)
    if updated is None:
        return jsonify({"error": "ペルソナが見つかりません"}), 404
    return jsonify({"persona": updated})

@app.route("/api/meeting/start", methods=["POST"])
def start_meeting():
    data = request.json
    topic = data.get("topic", "").strip()
    member_ids = data.get("member_ids", [])
    if not topic:
        return jsonify({"error": "議題を入力してください"}), 400
    if not member_ids:
        member_ids = [p["id"] for p in persona_manager.get_all_members()]
    session = meeting_room.create_session(topic, member_ids)
    return jsonify({
        "session_id": session["session_id"],
        "topic": session["topic"],
        "members": session["members"],
        "facilitator": session["facilitator"]
    })

@app.route("/api/meeting/<session_id>", methods=["GET"])
def get_session(session_id):
    summary = meeting_room.get_session_summary(session_id)
    if not summary:
        return jsonify({"error": "セッションが見つかりません"}), 404
    return jsonify(summary)

@app.route("/api/meeting/<session_id>/message", methods=["POST"])
def post_message(session_id):
    data = request.json
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"error": "メッセージを入力してください"}), 400
    msg = meeting_room.add_message(session_id, "user", "user", content)
    return jsonify({"message": msg})

@app.route("/api/stream/member/<session_id>/<persona_id>")
def stream_member(session_id, persona_id):
    trigger = request.args.get("trigger", None)
    def generate():
        yield from meeting_room.generate_member_response_stream(session_id, persona_id, trigger)
    return Response(generate(), mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/api/stream/facilitator/<session_id>")
def stream_facilitator(session_id):
    def generate():
        yield from meeting_room.generate_facilitator_response_stream(session_id)
    return Response(generate(), mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/api/stream/auto/<session_id>")
def stream_auto(session_id):
    def generate():
        yield from meeting_room.generate_auto_discussion_stream(session_id)
    return Response(generate(), mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.route("/api/health")
def health():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    return jsonify({
        "status": "ok",
        "api_key_set": bool(api_key and api_key != "your_api_key_here"),
        "personas": len(persona_manager.get_all_members()),
        "version": "Phase1-MVP"
    })

if __name__ == "__main__":
    print("=" * 50)
    print("  AI-PERSONA会議室 起動中...")
    print("  http://localhost:5000")
    print("=" * 50)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        print("\n⚠️  警告: ANTHROPIC_API_KEY が設定されていません")
        print("   .env ファイルに ANTHROPIC_API_KEY=your_key を設定してください\n")
    port = int(os.getenv("PORT", 8765))
    app.run(debug=False, host="0.0.0.0", port=port, threaded=True)