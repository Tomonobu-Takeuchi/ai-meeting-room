"""
persona_manager.py - ペルソナ管理（PostgreSQL永続化版）
"""
import uuid
from src.database import get_connection


class PersonaManager:
    """ペルソナのCRUD操作をPostgreSQLで管理"""

    # ===== 取得系 =====

    def get_all_members(self):
        """全ペルソナを取得（facilitator含む）"""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM personas ORDER BY role DESC, created_at ASC")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]

    def get_members_only(self):
        """memberロールのペルソナのみ取得"""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM personas WHERE role = 'member' ORDER BY created_at ASC"
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]

    def get_facilitator(self):
        """ファシリテータを取得"""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM personas WHERE role = 'facilitator' ORDER BY created_at ASC LIMIT 1"
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return dict(row) if row else None

    def get_persona_by_id(self, persona_id):
        """IDでペルソナを取得"""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM personas WHERE id = %s", (persona_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return dict(row) if row else None

    def get_personas_by_ids(self, ids):
        """複数IDでペルソナを取得"""
        if not ids:
            return []
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM personas WHERE id = ANY(%s) ORDER BY created_at ASC",
            (ids,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        # ids の順番に並べ替え
        id_order = {pid: i for i, pid in enumerate(ids)}
        return sorted([dict(r) for r in rows], key=lambda p: id_order.get(p['id'], 999))

    # ===== 追加・更新・削除 =====

    def add_persona(self, data):
        """新規ペルソナを追加"""
        persona_id = data.get('id') or str(uuid.uuid4())[:8]
        persona = {
            'id':            persona_id,
            'name':          data.get('name', '').strip(),
            'avatar':        data.get('avatar', '👤').strip() or '👤',
            'description':   data.get('description', '').strip(),
            'personality':   data.get('personality', '').strip(),
            'speaking_style': data.get('speaking_style', '').strip(),
            'background':    data.get('background', '').strip(),
            'color':         data.get('color', '#8B5CF6'),
            'role':          data.get('role', 'member'),
        }
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO personas (id, name, avatar, description, personality,
                speaking_style, background, color, role)
            VALUES (%(id)s, %(name)s, %(avatar)s, %(description)s, %(personality)s,
                %(speaking_style)s, %(background)s, %(color)s, %(role)s)
            ON CONFLICT (id) DO UPDATE SET
                name=EXCLUDED.name, avatar=EXCLUDED.avatar,
                description=EXCLUDED.description, personality=EXCLUDED.personality,
                speaking_style=EXCLUDED.speaking_style, background=EXCLUDED.background,
                color=EXCLUDED.color, role=EXCLUDED.role
            RETURNING *
        """, persona)
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return dict(row)

    def update_persona(self, persona_id, data):
        """ペルソナ情報を更新"""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE personas SET
                name           = %(name)s,
                avatar         = %(avatar)s,
                description    = %(description)s,
                personality    = %(personality)s,
                speaking_style = %(speaking_style)s,
                background     = %(background)s,
                color          = %(color)s
            WHERE id = %(id)s
            RETURNING *
        """, {
            'id':            persona_id,
            'name':          data.get('name', '').strip(),
            'avatar':        data.get('avatar', '👤').strip() or '👤',
            'description':   data.get('description', '').strip(),
            'personality':   data.get('personality', '').strip(),
            'speaking_style': data.get('speaking_style', '').strip(),
            'background':    data.get('background', '').strip(),
            'color':         data.get('color', '#8B5CF6'),
        })
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return dict(row) if row else None

    def delete_persona(self, persona_id):
        """ペルソナを削除（デフォルトペルソナは削除不可）"""
        protected = {'koumei', 'hideyoshi', 'professor', 'facilitator'}
        if persona_id in protected:
            return False, 'デフォルトペルソナは削除できません'
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM personas WHERE id = %s RETURNING id", (persona_id,))
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if row:
            return True, '削除しました'
        return False, 'ペルソナが見つかりません'

    # ===== プロンプト生成 =====

    def build_system_prompt(self, persona, topic, history_text='', learn_data=''):
        """ペルソナのシステムプロンプトを生成"""
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
        """ファシリテータのプロンプトを生成"""
        if mode == 'summarize':
            instruction = "議論全体を振り返り、各メンバーの主な意見・共通点・相違点・結論を整理してください。"
        else:
            instruction = "議論の進行を促し、次の論点や深掘りすべき点を提示してください。"

        prompt = f"""あなたは会議のファシリテータ「{facilitator['name']}」です。

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
        return prompt
