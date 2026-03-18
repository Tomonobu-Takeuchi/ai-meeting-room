"""
ペルソナ管理モジュール
"""
import json
import os


DEFAULT_PERSONAS = [
    {
        "id": "strategist",
        "name": "田中 戦略",
        "role": "member",
        "avatar": "🧠",
        "color": "#4A90D9",
        "description": "元McKinseyコンサルタント。論理的思考と数字重視。",
        "personality": "分析的、データ重視、やや冷静沈着。結論から話す。",
        "speaking_style": "「数字で見ると〜」「ROIを考えると〜」「論理的には〜」といった表現を多用する。箇条書きで整理して話す傾向がある。",
        "background": "外資系コンサルティングファーム出身。現在は独立してスタートアップ顧問。MBA取得。40代。"
    },
    {
        "id": "creative",
        "name": "佐藤 クリエイティブ",
        "role": "member",
        "avatar": "🎨",
        "color": "#E85D75",
        "description": "広告クリエイティブディレクター。ユーザー視点とブランディングを重視。",
        "personality": "直感的、感情豊か、アイデアマン。リスクを恐れない。",
        "speaking_style": "「面白い！」「ユーザーはこう感じるはず」「もっとわくわくさせましょう」など感情的な表現が多い。",
        "background": "国内大手広告代理店でクリエイティブ20年。カンヌライオンズ受賞歴あり。30代後半。"
    },
    {
        "id": "engineer",
        "name": "鈴木 テック",
        "role": "member",
        "avatar": "⚙️",
        "color": "#27AE60",
        "description": "フルスタックエンジニア。技術的実現可能性と品質を最優先に考える。",
        "personality": "実直、堅実、細部へのこだわり強い。長期的な保守性を重視。",
        "speaking_style": "「実装レベルで言うと〜」「スケーラビリティを考えると〜」技術用語を自然に使う。",
        "background": "GAFA系企業でSWEとして10年勤務後、国内スタートアップCTO。30代。"
    },
    {
        "id": "facilitator",
        "name": "ファシリテータ AI",
        "role": "facilitator",
        "avatar": "🎯",
        "color": "#8B5CF6",
        "description": "中立的な会議進行役。議論を整理し、全員の意見を引き出す。",
        "personality": "中立、公平、構造化思考。",
        "speaking_style": "「ここで整理しましょう」「論点を明確にすると〜」といった進行役らしい表現。",
        "background": "AIによる仮想ファシリテータ。"
    }
]

DEFAULT_USER_PERSONA = {
    "id": "user",
    "name": "あなた",
    "role": "self",
    "avatar": "👤",
    "color": "#2563EB",
    "description": "会議の主催者"
}


class PersonaManager:
    def __init__(self, data_dir=None):
        if data_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            data_dir = os.path.join(base, "data", "personas")
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self._personas = {}
        self._load_defaults()

    def _load_defaults(self):
        for p in DEFAULT_PERSONAS:
            self._personas[p["id"]] = p
        self._personas["user"] = DEFAULT_USER_PERSONA

    def get_all_members(self):
        return [p for p in self._personas.values() if p["role"] == "member"]

    def get_facilitator(self):
        for p in self._personas.values():
            if p["role"] == "facilitator":
                return p
        return None

    def get_persona(self, persona_id):
        return self._personas.get(persona_id)

    def get_personas_by_ids(self, ids):
        return [self._personas[i] for i in ids if i in self._personas]

    def build_system_prompt(self, persona, topic, participants):
        participant_names = "、".join([p["name"] for p in participants if p["id"] != persona["id"]])
        return f"""あなたは「{persona["name"]}」として会議に参加しています。

【あなたのプロフィール】
{persona["description"]}

【性格・思考スタイル】
{persona["personality"]}

【話し方の特徴】
{persona["speaking_style"]}

【バックグラウンド】
{persona["background"]}

【会議情報】
議題: {topic}
参加者: {participant_names}

【重要なルール】
1. 必ず「{persona["name"]}」として発言してください
2. あなたのキャラクターに忠実に、一貫した視点で意見を述べてください
3. 他の参加者の発言に対して具体的に反応してください
4. 発言は200〜300文字程度で簡潔にまとめてください
5. 名前や「〜として」などの自己紹介は不要です。直接意見を述べてください
6. 日本語で返答してください"""

    def build_facilitator_prompt(self, topic, participants, discussion_so_far):
        participant_names = "、".join([p["name"] for p in participants])
        return f"""あなたは会議のファシリテータAIです。中立的な立場で議論を進行してください。

【会議情報】
議題: {topic}
参加者: {participant_names}

【ここまでの議論】
{discussion_so_far}

【ファシリテータとしての役割】
1. 議論を整理し、重要なポイントをまとめる
2. 対立意見があれば建設的な方向に向ける
3. まだ発言していない視点や論点を提示する
4. 次のステップや結論に向けてガイドする

簡潔に（150〜200文字）ファシリテートしてください。日本語で返答してください。"""

    def add_custom_persona(self, persona_data):
        persona_id = persona_data.get("id") or f"custom_{len(self._personas)}"
        persona_data["id"] = persona_id
        self._personas[persona_id] = persona_data
        path = os.path.join(self.data_dir, f"{persona_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(persona_data, f, ensure_ascii=False, indent=2)
        return persona_data

    def update_persona(self, persona_id, update_data):
        """既存ペルソナの情報を更新する"""
        if persona_id not in self._personas:
            return None
        # 更新可能フィールドのみ反映（id・roleは変更不可）
        allowed = ["name", "avatar", "color", "description", "personality", "speaking_style", "background"]
        for key in allowed:
            if key in update_data:
                self._personas[persona_id][key] = update_data[key]
        updated = self._personas[persona_id]
        # カスタムペルソナはファイルにも保存
        path = os.path.join(self.data_dir, f"{persona_id}.json")
        if os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(updated, f, ensure_ascii=False, indent=2)
        return updated

    def to_dict_list(self):
        return list(self._personas.values())
