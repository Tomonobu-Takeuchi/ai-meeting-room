"""
AI-PERSONA会議室 - メインサーバー
"""
import io
import os
import sys
import json
 
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
 
from flask import Flask, Response, jsonify, request, send_from_directory, send_file
from dotenv import load_dotenv
import anthropic
 
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
    return jsonify({"members": persona_manager.get_all_personas()})
 
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
        member_ids = [p["id"] for p in persona_manager.get_all_personas()]
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
 
@app.route("/api/meeting/<session_id>/minutes", methods=["POST"])
def generate_minutes(session_id):
    summary = meeting_room.get_session_summary(session_id)
    if not summary:
        return jsonify({"error": "セッションが見つかりません"}), 404
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.lib.colors import HexColor
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from datetime import datetime
 
        pdfmetrics.registerFont(UnicodeCIDFont('HeiseiKakuGo-W5'))
        FONT = 'HeiseiKakuGo-W5'
 
        discussion = ""
        for msg in summary.get("messages", []):
            if msg["persona_id"] == "user":
                name = "ユーザー"
            elif msg["persona_id"] == "facilitator":
                name = "ファシリテータ"
            else:
                persona = next((m for m in summary["members"] if m["id"] == msg["persona_id"]), None)
                name = persona["name"] if persona else msg["persona_id"]
            discussion += f"{name}: {msg['content']}\n\n"
 
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        member_names = ", ".join([m["name"] for m in summary["members"]])
 
        prompt = f"""以下の会議の議論から議事録を作成してください。
 
議題：{summary['topic']}
参加者：{member_names}
 
議論内容：
{discussion if discussion else "（議論なし）"}
 
以下のJSON形式のみで出力してください（マークダウン記号なし）：
{{
  "conclusion": "会議の結論を2〜3文で記述",
  "opinions": {{
    "参加者名": "その参加者の主な意見を1〜2文で"
  }},
  "next_steps": "今後の進め方（改行区切り、各行を・で始める）"
}}
 
opinionsには全参加者分を含めてください。JSONのみ出力してください。"""
 
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
 
        text = response.content[0].text.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        minutes_data = json.loads(text)
 
        now = datetime.now()
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
            leftMargin=20*mm, rightMargin=20*mm,
            topMargin=20*mm, bottomMargin=20*mm)
 
        def make_style(size=11, bold=False, color=None):
            s = ParagraphStyle('s', fontName=FONT, fontSize=size,
                leading=size * 1.8, wordWrap='CJK')
            if color:
                s.textColor = HexColor(color)
            return s
 
        story = []
        story.append(Paragraph('AI-PERSONA 会議議事録', make_style(18, color='#1a1a2e')))
        story.append(Spacer(1, 6*mm))
        story.append(HRFlowable(width='100%', thickness=1, color=HexColor('#7C3AED')))
        story.append(Spacer(1, 4*mm))
 
        for label, value in [
            ('日時', now.strftime('%Y年%m月%d日 %H:%M')),
            ('場所', 'AI仮想会議室'),
            ('議題', summary['topic']),
            ('参加メンバー', member_names),
        ]:
            story.append(Paragraph(f'<b>{label}：</b>{value}', make_style(10)))
            story.append(Spacer(1, 1*mm))
 
        story.append(Spacer(1, 5*mm))
        story.append(Paragraph('■ 結論', make_style(13, color='#2563EB')))
        story.append(HRFlowable(width='100%', thickness=0.5, color=HexColor('#cccccc')))
        story.append(Spacer(1, 2*mm))
        story.append(Paragraph(minutes_data.get('conclusion', ''), make_style(10)))
 
        story.append(Spacer(1, 5*mm))
        story.append(Paragraph('■ 参加者の主な意見', make_style(13, color='#2563EB')))
        story.append(HRFlowable(width='100%', thickness=0.5, color=HexColor('#cccccc')))
        story.append(Spacer(1, 2*mm))
        for name, opinion in minutes_data.get('opinions', {}).items():
            story.append(Paragraph(f'<b>{name}：</b>{opinion}', make_style(10)))
            story.append(Spacer(1, 1*mm))
 
        story.append(Spacer(1, 5*mm))
        story.append(Paragraph('■ 今後の進め方', make_style(13, color='#2563EB')))
        story.append(HRFlowable(width='100%', thickness=0.5, color=HexColor('#cccccc')))
        story.append(Spacer(1, 2*mm))
        for step in minutes_data.get('next_steps', '').split('\n'):
            step = step.strip().lstrip('・').strip()
            if step:
                story.append(Paragraph(f'・{step}', make_style(10)))
                story.append(Spacer(1, 1*mm))
 
        doc.build(story)
        buf.seek(0)
 
        topic_short = summary['topic'][:20].replace('/', '_').replace('\\', '_')
        filename = f'議事録_{topic_short}_{now.strftime("%Y%m%d")}.pdf'
 
        return send_file(buf, as_attachment=True, download_name=filename,
            mimetype='application/pdf')
    except Exception as e:
        return jsonify({"error": str(e)}), 500
 
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
        "personas": len(persona_manager.get_all_personas()),
        "version": "Phase1-MVP"
    })
 
if __name__ == "__main__":
    print("=" * 50)
    print("  AI-PERSONA会議室 起動中...")
    print("  http://localhost:5000")
    print("=" * 50)
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        print("\n⚠️  警告: ANTHROPIC_API_KEY が設定されていません\n")
    port = int(os.getenv("PORT", 8765))
    app.run(debug=False, host="0.0.0.0", port=port, threaded=True)
 