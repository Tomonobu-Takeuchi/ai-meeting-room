"""
persona_manager.py - ペルソナ管理（pg8000 + RAG対応版）
"""
import uuid
import os
from src.database import (
    get_connection, rows_to_dicts, row_to_dict,
    save_learn_data, search_learn_data, get_learn_data_simple,
    get_learn_data_count, get_all_learn_data, delete_learn_data
)

COLUMNS = ['id','name','avatar','description','personality',
           'speaking_style','background','color','role','created_at']

class PersonaManager:

    # ===== ペルソナCRUD =====

    def get_members_only(self):
        conn = get_connection()
        rows = conn.run("SELECT * FROM personas WHERE role='member' ORDER BY created_at ASC")
        conn.close()
        result = rows_to_dicts(COLUMNS, rows)
        # 各ペルソナの学習データ件数を追加
        for p in result:
            p['learn_count'] = get_learn_data_count(p['id'])
        return result

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

    # ===== RAG学習データ管理 =====

    def add_learn_data(self, persona_id, content, source=''):
        """学習データを保存（ベクトル化はフォールバック）"""
        # OpenAI APIキーがあればベクトル化、なければテキストのみ保存
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
                print(f"Embedding失敗（テキストのみ保存）: {e}")
        save_learn_data(persona_id, content, source, embedding)
        return get_learn_data_count(persona_id)

    def get_relevant_learn_data(self, persona_id, topic):
        """議題に関連する学習データを取得（RAG）"""
        openai_key = os.environ.get('OPENAI_API_KEY', '')
        if openai_key:
            try:
                import openai
                client = openai.OpenAI(api_key=openai_key)
                res = client.embeddings.create(
                    model="text-embedding-3-small",
                    input=topic
                )
                query_embedding = res.data[0].embedding
                results = search_learn_data(persona_id, query_embedding, limit=3)
                if results:
                    return '\n\n'.join([r['content'] for r in results])
            except Exception as e:
                print(f"RAG検索失敗（フォールバック）: {e}")

        # フォールバック：最新の学習データを返す
        results = get_learn_data_simple(persona_id, limit=3)
        return '\n\n'.join([r['content'] for r in results]) if results else ''

    def get_all_learn_data(self, persona_id):
        return get_all_learn_data(persona_id)

    def delete_learn_data(self, persona_id, learn_id):
        delete_learn_data(persona_id, learn_id)

    # ===== プロンプト生成 =====

    def build_system_prompt(self, persona, topic, history_text='', learn_data=''):
        """RAG学習データを含むシステムプロンプトを生成"""
        # RAGから関連データを取得
        rag_data = self.get_relevant_learn_data(persona['id'], topic)
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

        # facilitatorがdictの場合とstrの場合に対応
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
