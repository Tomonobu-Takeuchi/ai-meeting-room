import json
import os

DEFAULT_PERSONAS = [
    {
        "id": "koumei",
        "name": "諸葛亮孔明",
        "role": "三国志の戦略家",
        "description": "三国志時代の天才軍師。卓越した戦略眼と先見の明を持ち、複雑な状況を俯瞰して最善策を導く。",
        "color": "#4A90D9",
        "icon": "⚔️",
        "avatar": "⚔️",
        "background": "",
        "prompt": "あなたは三国志の軍師・諸葛亮孔明です。卓越した戦略眼で物事を分析し、長期的視点から最善策を提案してください。故事や比喩を交えながら、論理的かつ格調高い言葉で語ってください。"
    },
    {
        "id": "hideyoshi",
        "name": "秀吉",
        "role": "戦国時代の武将",
        "description": "豊臣秀吉。農民から天下人へ。人たらしの才能と実行力で不可能を可能にする行動派リーダー。",
        "color": "#E85D4A",
        "icon": "🏯",
        "avatar": "🏯",
        "background": "",
        "prompt": "あなたは豊臣秀吉です。農民から天下人になった実行力と人たらしの才能を持ちます。前向きで豪快、庶民的な視点も忘れず、どんな困難も知恵と行動力で乗り越える姿勢で発言してください。"
    },
    {
        "id": "professor",
        "name": "教授",
        "role": "某国立大学の教授",
        "description": "某国立大学の教授。専門は経営学・組織論。データと理論に基づいた客観的分析が得意。",
        "color": "#27AE60",
        "icon": "🎓",
        "avatar": "🎓",
        "background": "",
        "prompt": "あなたは某国立大学の経営学・組織論の教授です。データと学術理論に基づいて客観的に分析し、実証研究の知見を活かしながら、論理的かつ丁寧な言葉で見解を述べてください。"
    }
]

class PersonaManager:
    def __init__(self, data_dir: str = "data/personas"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.personas = self._load_personas()

    def _load_personas(self):
        personas = []
        if os.path.exists(self.data_dir):
            for filename in sorted(os.listdir(self.data_dir)):
                if filename.endswith(".json"):
                    with open(os.path.join(self.data_dir, filename), "r", encoding="utf-8") as f:
                        personas.append(json.load(f))
        if not personas:
            personas = list(DEFAULT_PERSONAS)
        return personas

    def get_all_personas(self):
        return self.personas

    def to_dict_list(self):
        return self.personas

    def get_persona(self, persona_id: str):
        for p in self.personas:
            if p["id"] == persona_id:
                return p
        return None

    def get_personas_by_ids(self, ids: list):
        return [p for p in self.personas if p["id"] in ids]

    def add_custom_persona(self, persona: dict):
        self.personas.append(persona)
        filepath = os.path.join(self.data_dir, f"{persona['id']}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(persona, f, ensure_ascii=False, indent=2)
        return persona

    def add_persona(self, persona: dict):
        return self.add_custom_persona(persona)

    def update_persona(self, persona_id: str, data: dict):
        for i, p in enumerate(self.personas):
            if p["id"] == persona_id:
                self.personas[i].update(data)
                return self.personas[i]
        return None

    def get_default_personas(self):
        return DEFAULT_PERSONAS

    def get_facilitator(self):
        return {
            "id": "facilitator",
            "name": "ファシリテータ",
            "role": "会議の進行役",
            "color": "#9B59B6",
            "icon": "🎯",
            "avatar": "🎯"
        }

    def build_system_prompt(self, persona: dict, topic: str = "", members: list = None) -> str:
        base = persona.get("prompt", f"あなたは{persona['name']}です。{persona.get('description', '')}の立場で発言してください。")
        member_names = "、".join([m["name"] for m in (members or []) if m["id"] != persona["id"]])
        return f"{base}\n\n議題：「{topic}」\n参加者：{member_names}\n\n200文字以内で簡潔に発言してください。"

    def build_facilitator_prompt(self, topic: str = "", members: list = None, discussion: str = "") -> str:
        member_names = "、".join([m["name"] for m in (members or [])])
        return f"あなたは会議のファシリテータです。\n議題：「{topic}」\n参加者：{member_names}\n\n議論内容：\n{discussion}\n\n議論を整理し、次のステップを100文字以内で示してください。"