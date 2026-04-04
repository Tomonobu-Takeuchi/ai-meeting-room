"""
persona_manager.py - ペルソナ管理（PostgreSQL pg8000版）
"""
import uuid
from src.database import get_connection, rows_to_dicts, row_to_dict

COLUMNS = ['id','name','avatar','description','personality',
           'speaking_style','background','color','role','created_at']

class PersonaManager:

    def get_members_only(self):
        conn = get_connection()
        rows = conn.run("SELECT * FROM personas WHERE role='member' ORDER BY created_at ASC")
        conn.close()
        return rows_to_dicts(COLUMNS, rows)

    def get_facilitator(self):
        conn = get_connection()
        rows = conn.run("SELECT * FROM personas WHERE role='facilitator' ORDER BY created_at ASC LIMIT 1")
        conn.close()
        return row_to_dict(COLUMNS, rows[0]) if rows else None

    def get_all_personas(self):
        conn = get_connection()
        rows = conn.run("SELECT * FROM personas ORDER BY role DESC, created_at ASC")
        conn.close()
        return rows_to_dicts(COLUMNS, rows)

    def get_persona_by_id(self, persona_id):
        conn = get_connection()
        rows = conn.run("SELECT * FROM personas WHERE id=:id", id=persona_id)
        conn.close()
        return row_to_dict(COLUMNS, rows[0]) if rows else None

    def get_personas_by_ids(self, ids):
        if not ids:
            return []
        result = []
        for pid in ids:
            p = self.get_persona_by_id(pid)
            if p:
                result.append(p)
        return result

    def add_persona(self, data):
        persona_id = data.get('id') or str(uuid.uuid4())[:8]
        conn = get_connection()
        conn.run("""
            INSERT INTO personas (id, name, avatar, description, personality,
                speaking_style, background, color, role)
            VALUES (:id, :name, :avatar, :description, :personality,
                :speaking_style, :background, :color, :role)
            ON CONFLICT (id) DO UPDATE SET
                name=EXCLUDED.name, avatar=EXCLUDED.avatar,
                description=EXCLUDED.description, personality=EXCLUDED.personality,
                speaking_style=EXCLUDED.speaking_style, background=EXCLUDED.background,
                color=EXCLUDED.color, role=EXCLUDED.role
        """,
        id=persona_id,
        name=data.get('name','').strip(),
        avatar=data.get('avatar','👤').strip() or '👤',
        description=data.get('description','').strip(),
        personality=data.get('personality','').strip(),
        speaking_style=data.get('speaking_style','').strip(),
        background=data.get('background','').strip(),
        color=data.get('color','#8B5CF6'),
        role=data.get('role','member'))
        rows = conn.run("SELECT * FROM personas WHERE id=:id", id=persona_id)
        conn.close()
        return row_to_dict(COLUMNS, rows[0]) if rows else None

    def update_persona(self, persona_id, data):
        conn = get_connection()
        conn.run("""
            UPDATE personas SET
                name=:name, avatar=:avatar, description=:description,
                personality=:personality, speaking_style=:speaking_style,
                background=:background, color=:color
            WHERE id=:id
        """,
        id=persona_id,
        name=data.get('name','').strip(),
        avatar=data.get('avatar','👤').strip() or '👤',
        description=data.get('description','').strip(),
        personality=data.get('personality','').strip(),
        speaking_style=data.get('speaking_style','').strip(),
        background=data.get('background','').strip(),
        color=data.get('color','#8B5CF6'))
        rows = conn.run("SELECT * FROM personas WHERE id=:id", id=persona_id)
        conn.close()
        return row_to_dict(COLUMNS, rows[0]) if rows else None

    def delete_persona(self, persona_id):
        protected = {'koumei', 'hideyoshi', 'professor', 'facilitator'}
        if persona_id in protected:
            return False, 'デフォルトペルソナは削除できません'
        conn = get_connection()
        conn.run("DELETE FROM personas WHERE id=:id", id=persona_id)
        conn.close()
        return True, '削除しました'

    def to_dict_list(self):
        return self.get_all_personas()

    def add_custom_persona(self, data):
        return self.add_persona(data)

    def build_system_prompt(self, persona, topic, history_text='', learn_data=''):
        prompt = f"""あなたは「{persona['name']}」です。

【キャラクター設定】
{persona['description']}

【性格・思考スタイル】
{persona['personality']}

【話し方の特徴】
{persona['speaking_style']}

【バックグラウンド】
{persona.get('background', '')}
"""
        if learn_data:
            prompt += f"\n【学習データ・参考情報】\n{learn_data[:2000]}\n"

        prompt += f"""
【会議のルール】
- 議題：「{topic}」について議論しています
- あなた自身の立場・価値観・専門性から意見を述べてください
- 他のメンバーの発言を踏まえて発言してください
- 200〜400字程度で簡潔に発言してください
- キャラクターとして一貫して振る舞ってください
"""
        if history_text:
            prompt += f"\n【これまでの会話】\n{history_text}"
        return prompt

    def build_facilitator_prompt(self, facilitator, topic, history_text, mode='guide'):
        if mode == 'summarize':
            instruction = "議論全体を振り返り、各メンバーの主な意見・共通点・相違点・結論を整理してください。"
        else:
            instruction = "議論の進行を促し、次の論点や深掘りすべき点を提示してください。"

        return f"""あなたは会議のファシリテータ「{facilitator['name']}」です。

【役割】
中立的な立場で議論を整理・促進する進行役です。

【議題】
{topic}

【これまでの議論】
{history_text}

【指示】
{instruction}

300字以内で簡潔にまとめてください。
"""
