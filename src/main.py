"""
AI-PERSONA会議室 - メインサーバー（ユーザー認証対応版）
"""
import io
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, Response, jsonify, request, send_from_directory, send_file, session
from dotenv import load_dotenv
import anthropic
import bcrypt

from src.persona.persona_manager import PersonaManager
from src.meeting.meeting_room import MeetingRoom
from src.database import init_db, get_user_by_email, get_user_by_id, create_user

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web"),
    static_url_path=""
)
app.secret_key = os.environ.get('SECRET_KEY', 'ai-persona-secret-key-2026')
app.json.ensure_ascii = False  # 日本語をUnicodeエスケープしない（Flask 2.2以降）

init_db()
persona_manager = PersonaManager()
meeting_room = MeetingRoom(persona_manager)


def get_current_user_id():
    """現在ログイン中のユーザーIDを返す（未ログインはNone）"""
    return session.get('user_id')

def login_required(f):
    """ログイン必須デコレータ"""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not get_current_user_id():
            return jsonify({"error": "ログインが必要です", "code": "UNAUTHORIZED"}), 401
        return f(*args, **kwargs)
    return decorated


# ===== 静的ファイル =====

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ===== ユーザー認証API =====

@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.json
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    name = data.get("name", "").strip()

    if not email or not password:
        return jsonify({"error": "メールアドレスとパスワードを入力してください"}), 400
    if len(password) < 6:
        return jsonify({"error": "パスワードは6文字以上にしてください"}), 400

    existing = get_user_by_email(email)
    if existing:
        return jsonify({"error": "このメールアドレスはすでに登録されています"}), 400

    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    try:
        user = create_user(email, password_hash, name)
        session['user_id'] = user['id']
        session['user_email'] = user['email']
        session['user_name'] = user['name']
        return jsonify({"message": "登録完了", "user": {"id": user['id'], "email": user['email'], "name": user['name'], "plan": user['plan']}})
    except Exception as e:
        return jsonify({"error": f"登録エラー: {str(e)}"}), 500

@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.json
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    user = get_user_by_email(email)
    if not user:
        return jsonify({"error": "メールアドレスまたはパスワードが違います"}), 401

    if not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        return jsonify({"error": "メールアドレスまたはパスワードが違います"}), 401

    session['user_id'] = user['id']
    session['user_email'] = user['email']
    session['user_name'] = user['name']
    return jsonify({"message": "ログイン成功", "user": {"id": user['id'], "email": user['email'], "name": user['name'], "plan": user['plan']}})

@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "ログアウトしました"})

@app.route("/api/auth/me", methods=["GET"])
def me():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"user": None})
    user = get_user_by_id(user_id)
    if not user:
        session.clear()
        return jsonify({"user": None})
    return jsonify({"user": {"id": user['id'], "email": user['email'], "name": user['name'], "plan": user['plan']}})


# ===== ペルソナAPI =====

@app.route("/api/personas", methods=["GET"])
def get_personas():
    user_id = get_current_user_id()
    return jsonify({"personas": persona_manager.get_all_personas(user_id)})

@app.route("/api/personas/members", methods=["GET"])
def get_members():
    user_id = get_current_user_id()
    members = persona_manager.get_members_only(user_id)
    facilitator = persona_manager.get_facilitator(user_id)
    return jsonify({"members": members, "facilitator": facilitator})

@app.route("/api/personas/add", methods=["POST"])
def add_persona():
    user_id = get_current_user_id()
    data = request.json
    if not data:
        return jsonify({"error": "データがありません"}), 400
    data.setdefault("role", "member")
    data.setdefault("avatar", "👤")
    data.setdefault("color", "#6B7280")
    data.setdefault("background", "")
    persona = persona_manager.add_persona(data, user_id)
    return jsonify({"persona": persona})

@app.route("/api/personas/<persona_id>", methods=["PUT"])
def update_persona(persona_id):
    user_id = get_current_user_id()
    data = request.json
    if not data:
        return jsonify({"error": "データがありません"}), 400
    updated = persona_manager.update_persona(persona_id, data, user_id)
    if updated is None:
        return jsonify({"error": "ペルソナが見つかりません"}), 404
    return jsonify({"persona": updated})

@app.route("/api/personas/<persona_id>", methods=["DELETE"])
def delete_persona(persona_id):
    user_id = get_current_user_id()
    success, message = persona_manager.delete_persona(persona_id, user_id)
    if not success:
        return jsonify({"error": message}), 400
    return jsonify({"message": message})


# ===== 学習データAPI =====

@app.route("/api/personas/<persona_id>/learn", methods=["GET"])
def get_learn_data(persona_id):
    user_id = get_current_user_id()
    data = persona_manager.get_all_learn_data(persona_id, user_id)
    return jsonify({"learn_data": data, "count": len(data)})

@app.route("/api/personas/<persona_id>/learn", methods=["POST"])
def add_learn_data(persona_id):
    user_id = get_current_user_id()
    data = request.json
    content = data.get("content", "").strip()
    source = data.get("source", "")
    if not content:
        return jsonify({"error": "コンテンツが空です"}), 400
    count = persona_manager.add_learn_data(persona_id, content, source, user_id)
    # Growth: 知識量スコア更新
    try:
        persona_manager.on_learn_data_added(persona_id, user_id, content)
    except Exception as e:
        print(f"Growth知識更新エラー（無視）: {e}")
    return jsonify({"message": "学習データを保存しました", "total_count": count})

@app.route("/api/personas/<persona_id>/learn/<int:learn_id>", methods=["DELETE"])
def delete_learn_data(persona_id, learn_id):
    user_id = get_current_user_id()
    persona_manager.delete_learn_data(persona_id, learn_id, user_id)
    return jsonify({"message": "削除しました"})

@app.route("/api/learn/fetch-url", methods=["POST"])
def fetch_learn_url():
    data = request.json
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URLを入力してください"}), 400
    try:
        import requests as req
        from bs4 import BeautifulSoup
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        res = req.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
            tag.decompose()
        lines = [l.strip() for l in soup.get_text(separator='\n').split('\n') if l.strip()]
        text = '\n'.join(lines)[:4000]
        return jsonify({"text": text, "url": url})
    except Exception as e:
        return jsonify({"error": f"取得エラー: {str(e)}"}), 500

@app.route("/api/learn/fetch-youtube", methods=["POST"])
def fetch_learn_youtube():
    data = request.json
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "YouTube URLを入力してください"}), 400
    try:
        import re
        from youtube_transcript_api import YouTubeTranscriptApi
        match = re.search(r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})', url)
        if not match:
            return jsonify({"error": "YouTube URLが正しくありません"}), 400
        video_id = match.group(1)
        # まず字幕APIを試みる
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript = None
            for lang in ['ja', 'en']:
                try:
                    t = transcript_list.find_transcript([lang])
                    transcript = t.fetch()
                    break
                except Exception:
                    try:
                        t = transcript_list.find_generated_transcript([lang])
                        transcript = t.fetch()
                        break
                    except Exception:
                        continue
            if transcript is None:
                for t in transcript_list:
                    transcript = t.fetch()
                    break
            if transcript:
                text = ' '.join([t['text'] for t in transcript])[:4000]
                return jsonify({"text": text, "url": url})
        except Exception:
            pass
        # 字幕なし → yt-dlp + Whisper APIで音声から文字起こし（自動圧縮+チャンク対応）
        try:
            import tempfile, yt_dlp, openai, math, subprocess, glob
            client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            with tempfile.TemporaryDirectory() as tmpdir:
                ydl_opts = {
                    # iOSクライアントを優先するとBot検知を回避できる
                    'format': 'bestaudio/best',
                    'outtmpl': f'{tmpdir}/audio.%(ext)s',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '32',
                    }],
                    'extractor_args': {'youtube': {'player_client': ['ios', 'web']}},
                    'quiet': True,
                    'ignoreerrors': False,
                    'no_warnings': True,
                    'extractor_retries': 3,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])

                # 変換済み音声ファイルを探す（postprocessor成功時）
                converted_files = glob.glob(f'{tmpdir}/audio.mp3') + glob.glob(f'{tmpdir}/audio.m4a')
                if converted_files:
                    audio_path = converted_files[0]
                else:
                    # postprocessorが失敗した場合、元ファイルをffmpegで直接変換
                    raw_files = [f for f in glob.glob(f'{tmpdir}/audio.*') if not f.endswith('.m4a')]
                    if not raw_files:
                        raise Exception("動画のダウンロードに失敗しました。非公開・地域制限の動画の可能性があります。")
                    converted_path = f'{tmpdir}/audio_conv.m4a'
                    conv = subprocess.run(
                        ["ffmpeg", "-i", raw_files[0], "-vn", "-acodec", "aac",
                         "-b:a", "32k", "-ar", "16000", "-ac", "1", converted_path, "-y"],
                        capture_output=True, timeout=180
                    )
                    if conv.returncode != 0 or not os.path.exists(converted_path):
                        raise Exception("音声の変換に失敗しました。ffmpegが利用できない可能性があります。")
                    audio_path = converted_path

                # Whisper送信前：ファイルサイズ確認 + 安全な再エンコード
                if os.path.getsize(audio_path) == 0:
                    raise Exception("音声ファイルが空です。動画に音声トラックがない可能性があります。")
                safe_path = f'{tmpdir}/audio_safe.m4a'
                re_enc = subprocess.run(
                    ["ffmpeg", "-i", audio_path, "-acodec", "aac",
                     "-b:a", "32k", "-ar", "16000", "-ac", "1", safe_path, "-y"],
                    capture_output=True, timeout=180
                )
                if re_enc.returncode == 0 and os.path.exists(safe_path) and os.path.getsize(safe_path) > 0:
                    audio_path = safe_path

                file_size = os.path.getsize(audio_path)
                MAX_SIZE = 24 * 1024 * 1024

                if file_size <= MAX_SIZE:
                    with open(audio_path, 'rb') as af:
                        transcription = client.audio.transcriptions.create(
                            model="whisper-1", file=af, language="ja"
                        )
                    full_text = transcription.text
                else:
                    # チャンク分割
                    probe = subprocess.run(["ffmpeg", "-i", audio_path],
                        capture_output=True, text=True)
                    duration = 0
                    for line in probe.stderr.split("\n"):
                        if "Duration" in line:
                            parts = line.strip().split("Duration:")[1].split(",")[0].strip()
                            h, m, s = parts.split(":")
                            duration = int(h)*3600 + int(m)*60 + float(s)
                            break
                    chunk_duration = 600
                    num_chunks = math.ceil(duration / chunk_duration)
                    full_text = ""
                    for i in range(num_chunks):
                        start = i * chunk_duration
                        chunk_path = f'{tmpdir}/chunk_{i}.m4a'
                        subprocess.run(
                            ["ffmpeg", "-i", audio_path, "-ss", str(start),
                             "-t", str(chunk_duration), "-acodec", "copy",
                             chunk_path, "-y"], capture_output=True, timeout=60
                        )
                        if os.path.exists(chunk_path):
                            with open(chunk_path, 'rb') as af:
                                result = client.audio.transcriptions.create(
                                    model="whisper-1", file=af, language="ja"
                                )
                            full_text += result.text + " "
            return jsonify({"text": full_text.strip()[:6000], "url": url})
        except Exception as e2:
            return jsonify({"error": f"音声文字起こしエラー: {str(e2)}"}), 500
    except Exception as e:
        return jsonify({"error": f"取得エラー: {str(e)}"}), 500

@app.route("/api/learn/transcribe-audio", methods=["POST"])
def transcribe_audio():
    audio_file = request.files.get("audio")
    if not audio_file:
        return jsonify({"error": "音声ファイルが見つかりません"}), 400
    try:
        import tempfile, subprocess, math, openai
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        suffix = os.path.splitext(audio_file.filename)[1].lower() or '.mp3'
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            audio_file.save(f.name)
            raw_path = f.name

        # 32kbpsモノラルに圧縮（1時間20分のmp3でも約19MBになる）
        with tempfile.TemporaryDirectory() as tmpdir:
            compressed_path = f'{tmpdir}/audio_compressed.m4a'
            proc = subprocess.run(
                ["ffmpeg", "-i", raw_path, "-vn", "-acodec", "aac",
                 "-b:a", "32k", "-ar", "16000", "-ac", "1", compressed_path, "-y"],
                capture_output=True, timeout=300
            )
            os.unlink(raw_path)
            if proc.returncode != 0 or not os.path.exists(compressed_path) or os.path.getsize(compressed_path) == 0:
                raise Exception("音声の変換に失敗しました。対応していない形式の可能性があります。")

            file_size = os.path.getsize(compressed_path)
            MAX_SIZE = 24 * 1024 * 1024

            if file_size <= MAX_SIZE:
                with open(compressed_path, 'rb') as af:
                    result = client.audio.transcriptions.create(
                        model="whisper-1", file=af, language="ja"
                    )
                return jsonify({"text": result.text})
            else:
                # 25MB超（極端に長い音声）→ チャンク分割
                probe = subprocess.run(["ffmpeg", "-i", compressed_path],
                    capture_output=True, text=True)
                duration = 0
                for line in probe.stderr.split("\n"):
                    if "Duration" in line:
                        parts = line.strip().split("Duration:")[1].split(",")[0].strip()
                        h, m, s = parts.split(":")
                        duration = int(h)*3600 + int(m)*60 + float(s)
                        break
                chunk_duration = 600
                num_chunks = math.ceil(duration / chunk_duration)
                full_text = ""
                for i in range(num_chunks):
                    start = i * chunk_duration
                    chunk_path = f'{tmpdir}/chunk_{i}.m4a'
                    subprocess.run(
                        ["ffmpeg", "-i", compressed_path, "-ss", str(start),
                         "-t", str(chunk_duration), "-acodec", "copy",
                         chunk_path, "-y"], capture_output=True, timeout=60
                    )
                    if os.path.exists(chunk_path):
                        with open(chunk_path, 'rb') as af:
                            result = client.audio.transcriptions.create(
                                model="whisper-1", file=af, language="ja"
                            )
                        full_text += result.text + " "
                return jsonify({"text": full_text.strip()[:8000]})
    except Exception as e:
        return jsonify({"error": f"文字起こしエラー: {str(e)}"}), 500


@app.route("/api/learn/transcribe-video", methods=["POST"])
def transcribe_video():
    video_file = request.files.get("video")
    if not video_file:
        return jsonify({"error": "動画ファイルが見つかりません"}), 400
    try:
        import tempfile, subprocess, math, openai
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        suffix = os.path.splitext(video_file.filename)[1].lower() or ".mp4"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            video_file.save(f.name)
            video_path = f.name

        # 音声抽出（32kbps モノラルで圧縮）
        # ★ suffixを単純replace→入力と同じパスになるバグを修正。splitextで安全に生成
        audio_path = os.path.splitext(video_path)[0] + "_audio.m4a"
        proc = subprocess.run(
            ["ffmpeg", "-i", video_path, "-vn", "-acodec", "aac",
             "-b:a", "32k", "-ar", "16000", "-ac", "1", audio_path, "-y"],
            capture_output=True, timeout=300
        )
        os.unlink(video_path)
        if proc.returncode != 0 or not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            raise Exception("音声の変換に失敗しました。動画に音声トラックがないか、対応していない形式の可能性があります。")

        file_size = os.path.getsize(audio_path)
        MAX_SIZE = 24 * 1024 * 1024  # 24MB（余裕を持って）

        if file_size <= MAX_SIZE:
            # 25MB以内：そのままWhisper APIへ
            with open(audio_path, "rb") as af:
                transcription = client.audio.transcriptions.create(
                    model="whisper-1", file=af, language="ja"
                )
            os.unlink(audio_path)
            return jsonify({"text": transcription.text})
        else:
            # 25MB超：チャンク分割して文字起こし
            # 動画の長さを取得
            probe = subprocess.run(
                ["ffmpeg", "-i", audio_path],
                capture_output=True, text=True
            )
            duration = 0
            for line in probe.stderr.split("\n"):
                if "Duration" in line:
                    parts = line.strip().split("Duration:")[1].split(",")[0].strip()
                    h, m, s = parts.split(":")
                    duration = int(h)*3600 + int(m)*60 + float(s)
                    break

            chunk_duration = 600  # 10分ごとに分割
            num_chunks = math.ceil(duration / chunk_duration)
            full_text = ""

            with tempfile.TemporaryDirectory() as tmpdir:
                for i in range(num_chunks):
                    start = i * chunk_duration
                    chunk_path = f"{tmpdir}/chunk_{i}.m4a"
                    subprocess.run(
                        ["ffmpeg", "-i", audio_path, "-ss", str(start),
                         "-t", str(chunk_duration), "-acodec", "copy",
                         chunk_path, "-y"],
                        capture_output=True, timeout=60
                    )
                    if os.path.exists(chunk_path):
                        with open(chunk_path, "rb") as af:
                            result = client.audio.transcriptions.create(
                                model="whisper-1", file=af, language="ja"
                            )
                        full_text += result.text + " "

            os.unlink(audio_path)
            return jsonify({"text": full_text.strip()[:8000]})

    except Exception as e:
        return jsonify({"error": f"動画文字起こしエラー: {str(e)}"}), 500


# ===== 会議API =====

@app.route("/api/meeting/start", methods=["POST"])
def start_meeting():
    user_id = get_current_user_id()
    data = request.json
    topic = data.get("topic", "").strip()
    member_ids = data.get("member_ids", [])
    if not topic:
        return jsonify({"error": "議題を入力してください"}), 400
    if not member_ids:
        member_ids = [p["id"] for p in persona_manager.get_members_only(user_id)]
    session_data = meeting_room.create_session(topic, member_ids, user_id)
    return jsonify({
        "session_id": session_data["session_id"],
        "topic": session_data["topic"],
        "members": session_data["members"],
        "facilitator": session_data["facilitator"]
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
以下のJSON形式のみで出力してください：
{{
  "conclusion": "会議の結論を2〜3文で記述",
  "opinions": {{"参加者名": "主な意見を1〜2文で"}},
  "next_steps": "今後の進め方（改行区切り、各行を・で始める）"
}}
JSONのみ出力してください。"""

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

        def make_style(size=11, color=None):
            s = ParagraphStyle('s', fontName=FONT, fontSize=size,
                leading=size * 1.8, wordWrap='CJK')
            if color:
                s.textColor = HexColor(color)
            return s

        story = []
        story.append(Paragraph('AI-PERSONA 会議議事録', make_style(18, '#1a1a2e')))
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
        story.append(Paragraph('■ 結論', make_style(13, '#2563EB')))
        story.append(HRFlowable(width='100%', thickness=0.5, color=HexColor('#cccccc')))
        story.append(Spacer(1, 2*mm))
        story.append(Paragraph(minutes_data.get('conclusion', ''), make_style(10)))
        story.append(Spacer(1, 5*mm))
        story.append(Paragraph('■ 参加者の主な意見', make_style(13, '#2563EB')))
        story.append(HRFlowable(width='100%', thickness=0.5, color=HexColor('#cccccc')))
        story.append(Spacer(1, 2*mm))
        for name, opinion in minutes_data.get('opinions', {}).items():
            story.append(Paragraph(f'<b>{name}：</b>{opinion}', make_style(10)))
            story.append(Spacer(1, 1*mm))
        story.append(Spacer(1, 5*mm))
        story.append(Paragraph('■ 今後の進め方', make_style(13, '#2563EB')))
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

        # ===== Phase 1-3: 会議ログ学習・パターン保存・カウント更新 =====
        _uid = get_current_user_id()  # ゲストはNone（NULLとして保存）
        try:
            persona_manager.save_meeting_log(summary, _uid)
        except Exception as e:
            print(f"Phase1エラー（無視）: {e}")
        try:
            persona_manager.extract_and_save_patterns(summary, _uid)
        except Exception as e:
            print(f"Phase2エラー（無視）: {e}")
        try:
            for member in summary.get('members', []):
                persona_manager.increment_persona_meeting_count(member['id'], _uid)
        except Exception as e:
            print(f"Phase3エラー（無視）: {e}")
        # ===== Growth: 成熟度スコア更新 =====
        try:
            persona_manager.on_conversation_end(summary, _uid)
        except Exception as e:
            print(f"Growthエラー（無視）: {e}")

        return send_file(buf, as_attachment=True, download_name=filename, mimetype='application/pdf')
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===== ストリーミングAPI =====

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


# ===== ヘルスチェック =====

@app.route("/api/personas/<persona_id>/evolution", methods=["GET"])
def get_persona_evolution(persona_id):
    """Phase 3: ペルソナの成長状況を返す"""
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"level": 0, "meeting_count": 0})
    level, count = persona_manager.get_evolution_level(persona_id, user_id)
    level_names = {0: "初回", 1: "見習い", 2: "熟練", 3: "達人"}
    return jsonify({
        "persona_id": persona_id,
        "level": level,
        "level_name": level_names.get(level, "初回"),
        "meeting_count": count,
        "next_level_at": [4, 10, None][min(level, 2)]
    })


@app.route("/api/personas/<persona_id>/feedback", methods=["POST"])
def post_persona_feedback(persona_id):
    """フィードバックを保存する"""
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"error": "ログインが必要です"}), 401
    data = request.json or {}
    rating = data.get("rating")           # True=良かった / False=良くなかった
    detail_category = data.get("detail_category", "")
    correct_response = data.get("correct_response", "")
    add_to_learn = data.get("add_to_learn", False)
    session_id = data.get("session_id", "")
    if rating is None:
        return jsonify({"error": "ratingは必須です"}), 400
    try:
        # 保存前のmaturity_levelを取得
        growth_before = persona_manager.get_growth(persona_id, user_id) or {}
        level_before = growth_before.get("maturity_level", 0)

        persona_manager.save_feedback(
            persona_id, user_id, session_id,
            bool(rating), detail_category, correct_response,
            add_to_learn=add_to_learn
        )

        # 保存後のmaturity_levelを取得してレベルアップ判定
        growth_after = persona_manager.get_growth(persona_id, user_id) or {}
        level_after = growth_after.get("maturity_level", 0)

        resp = {"message": "フィードバックを保存しました"}
        if level_after > level_before:
            resp["level_up"] = True
            resp["new_level"] = level_after
            resp["level_name"] = persona_manager.get_maturity_label(level_after)
        return jsonify(resp)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/personas/<persona_id>/growth", methods=["GET"])
def get_persona_growth(persona_id):
    """成熟度スコアを返す"""
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"growth": None})
    growth = persona_manager.get_growth(persona_id, user_id)
    if growth:
        growth["level_name"] = persona_manager.get_maturity_label(growth["maturity_level"])
    return jsonify({"growth": growth})


@app.route("/api/health")
def health():
    user_id = get_current_user_id()
    return jsonify({
        "status": "ok",
        "api_key_set": bool(os.getenv("ANTHROPIC_API_KEY")),
        "user_id": user_id,
        "version": "v0.9-auth"
    })


if __name__ == "__main__":
    print("=" * 50)
    print("  AI-PERSONA会議室 起動中...")
    print("  http://localhost:5000")
    print("=" * 50)
    port = int(os.getenv("PORT", 8765))
    app.run(debug=False, host="0.0.0.0", port=port, threaded=True)
