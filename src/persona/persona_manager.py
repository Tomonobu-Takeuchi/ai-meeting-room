"""
persona_manager.py - ペルソナ管理（ユーザー認証 + RAG対応版）
"""
import uuid
import os
from src.database import (
    get_connection, rows_to_dicts, row_to_dict,
    save_learn_data, search_learn_data, get_learn_data_simple,
    get_learn_data_count, get_all_learn_data, delete_learn_data
)

COLUMNS = ['id','user_id','name','avatar','description','personality',
           'speaking_style','background','color','role','is_default','created_at']

def serialize_persona(d):
    """datetimeをstrに変換・不要フィールドを整理"""
    if not d:
        return d
    if 'created_at' in d and d['created_at'] is not None:
        d['created_at'] = str(d['created_at'])
    return d


class PersonaManager:

    # ===== ペルソナ取得（user_id対応） =====

    def get_members_only(self, user_id=None):
        """memberロールのペルソナ取得（デフォルト＋ユーザー固有）"""
        conn = get_connection()
        if user_id:
            rows = conn.run("""
                SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at FROM personas
                WHERE role='member'
                  AND (user_id=:user_id OR user_id IS NULL)
                ORDER BY is_default DESC, created_at ASC
            """, user_id=user_id)
        else:
            rows = conn.run("""
                SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at FROM personas
                WHERE role='member' AND user_id IS NULL
                ORDER BY created_at ASC
            """)
        conn.close()
        result = [serialize_persona(row_to_dict(COLUMNS, r)) for r in rows]
        for p in result:
            p['learn_count'] = get_learn_data_count(p['id'], user_id)
        return result

    def get_facilitator(self, user_id=None):
        """ファシリテータ取得"""
        conn = get_connection()
        if user_id:
            rows = conn.run("""
                SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at FROM personas
                WHERE role='facilitator'
                  AND (user_id=:user_id OR user_id IS NULL)
                ORDER BY is_default DESC, created_at ASC LIMIT 1
            """, user_id=user_id)
        else:
            rows = conn.run("""
                SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at FROM personas
                WHERE role='facilitator' AND user_id IS NULL
                ORDER BY created_at ASC LIMIT 1
            """)
        conn.close()
        return serialize_persona(row_to_dict(COLUMNS, rows[0])) if rows else None

    def get_all_personas(self, user_id=None):
        conn = get_connection()
        if user_id:
            rows = conn.run("""
                SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at FROM personas
                WHERE user_id=:user_id OR user_id IS NULL
                ORDER BY role DESC, is_default DESC, created_at ASC
            """, user_id=user_id)
        else:
            rows = conn.run("""
                SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at FROM personas WHERE user_id IS NULL
                ORDER BY role DESC, created_at ASC
            """)
        conn.close()
        return [serialize_persona(row_to_dict(COLUMNS, r)) for r in rows]

    def get_persona_by_id(self, persona_id, user_id=None):
        conn = get_connection()
        if user_id:
            rows = conn.run("""
                SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at FROM personas
                WHERE id=:id AND (user_id=:user_id OR user_id IS NULL)
            """, id=persona_id, user_id=user_id)
        else:
            rows = conn.run("SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at FROM personas WHERE id=:id", id=persona_id)
        conn.close()
        return serialize_persona(row_to_dict(COLUMNS, rows[0])) if rows else None

    # meeting_room.py との互換性
    def get_persona(self, persona_id, user_id=None):
        return self.get_persona_by_id(persona_id, user_id)

    def get_personas_by_ids(self, ids, user_id=None):
        return [p for p in [self.get_persona_by_id(pid, user_id) for pid in ids] if p]

    # ===== ペルソナ追加・更新・削除 =====

    def add_persona(self, data, user_id=None):
        persona_id = data.get('id') or str(uuid.uuid4())[:8]
        conn = get_connection()
        conn.run("""
            INSERT INTO personas (id, user_id, name, avatar, description, personality,
                speaking_style, background, color, role, is_default)
            VALUES (:id, :user_id, :name, :avatar, :description, :personality,
                :speaking_style, :background, :color, :role, FALSE)
            ON CONFLICT DO NOTHING
        """,
        id=persona_id, user_id=user_id,
        name=data.get('name','').strip(),
        avatar=data.get('avatar','👤').strip() or '👤',
        description=data.get('description','').strip(),
        personality=data.get('personality','').strip(),
        speaking_style=data.get('speaking_style','').strip(),
        background=data.get('background','').strip(),
        color=data.get('color','#8B5CF6'),
        role=data.get('role','member'))
        rows = conn.run("""
            SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at FROM personas WHERE id=:id AND (user_id=:user_id OR user_id IS NULL)
        """, id=persona_id, user_id=user_id)
        conn.close()
        return serialize_persona(row_to_dict(COLUMNS, rows[0])) if rows else None

    def update_persona(self, persona_id, data, user_id=None):
        conn = get_connection()
        if user_id:
            conn.run("""
                UPDATE personas SET
                    name=:name, avatar=:avatar, description=:description,
                    personality=:personality, speaking_style=:speaking_style,
                    background=:background, color=:color
                WHERE id=:id AND (user_id=:user_id OR user_id IS NULL)
            """,
            id=persona_id, user_id=user_id,
            name=data.get('name','').strip(),
            avatar=data.get('avatar','👤').strip() or '👤',
            description=data.get('description','').strip(),
            personality=data.get('personality','').strip(),
            speaking_style=data.get('speaking_style','').strip(),
            background=data.get('background','').strip(),
            color=data.get('color','#8B5CF6'))
            rows = conn.run("""
                SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at FROM personas WHERE id=:id AND (user_id=:user_id OR user_id IS NULL)
            """, id=persona_id, user_id=user_id)
        else:
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
            rows = conn.run("SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at FROM personas WHERE id=:id", id=persona_id)
        conn.close()
        return serialize_persona(row_to_dict(COLUMNS, rows[0])) if rows else None

    def delete_persona(self, persona_id, user_id=None):
        protected = {'koumei', 'hideyoshi', 'professor', 'facilitator'}
        if persona_id in protected:
            return False, 'デフォルトペルソナは削除できません'
        conn = get_connection()
        if user_id:
            conn.run("DELETE FROM personas WHERE id=:id AND user_id=:user_id",
                     id=persona_id, user_id=user_id)
        else:
            conn.run("DELETE FROM personas WHERE id=:id", id=persona_id)
        conn.close()
        return True, '削除しました'

    def to_dict_list(self, user_id=None):
        return self.get_all_personas(user_id)

    def add_custom_persona(self, data, user_id=None):
        return self.add_persona(data, user_id)

    # ===== RAG学習データ =====

    def add_learn_data(self, persona_id, content, source='', user_id=None):
        embedding = None
        openai_key = os.environ.get('OPENAI_API_KEY', '')
        if openai_key:
            try:
                import openai
                client = openai.OpenAI(api_key=openai_key)
                res = client.embeddings.create(
                    model="text-embedding-3-small",
                    input=content[:8000]
                )
                embedding = res.data[0].embedding
            except Exception as e:
                print(f"Embedding失敗: {e}")
        save_learn_data(persona_id, user_id, content, source, embedding)
        return get_learn_data_count(persona_id, user_id)

    def get_relevant_learn_data(self, persona_id, topic, user_id=None):
        openai_key = os.environ.get('OPENAI_API_KEY', '')
        if openai_key and user_id:
            try:
                import openai
                client = openai.OpenAI(api_key=openai_key)
                res = client.embeddings.create(
                    model="text-embedding-3-small",
                    input=topic
                )
                results = search_learn_data(persona_id, user_id, res.data[0].embedding, limit=3)
                if results:
                    return '\n\n'.join([r['content'] for r in results])
            except Exception as e:
                print(f"RAG検索失敗: {e}")
        results = get_learn_data_simple(persona_id, user_id or 0, limit=3)
        return '\n\n'.join([r['content'] for r in results]) if results else ''

    def get_all_learn_data(self, persona_id, user_id=None):
        return get_all_learn_data(persona_id, user_id or 0)

    def delete_learn_data(self, persona_id, learn_id, user_id=None):
        delete_learn_data(persona_id, user_id or 0, learn_id)

    # ===== プロンプト生成 =====

    def build_system_prompt(self, persona, topic, history_text='', learn_data='', user_id=None):
        rag_data = self.get_relevant_learn_data(persona['id'], topic, user_id)
        combined_learn = ''
        if rag_data:
            combined_learn += rag_data
        if learn_data:
            combined_learn += '\n\n' + learn_data

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
        if combined_learn:
            prompt += f"\n【この人物に関する学習データ・参考情報】\n{combined_learn[:3000]}\n"
            prompt += "\n※上記の学習データをもとに、この人物らしく発言してください。\n"

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

        if isinstance(facilitator, dict):
            facilitator_name = facilitator.get('name', 'ファシリテータ')
        else:
            facilitator_name = str(facilitator)

        return f"""あなたは会議のファシリテータ「{facilitator_name}」です。

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
