"""
persona_manager.py - ペルソナ管理（ユーザー認証 + RAG対応版）
"""
import uuid
import os
from src.database import (
    get_connection, rows_to_dicts, row_to_dict,
    save_learn_data, search_learn_data, get_learn_data_simple,
    get_learn_data_count, get_all_learn_data, delete_learn_data,
    save_persona_pattern, get_persona_patterns,
    increment_meeting_count, get_meeting_count
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


    # ===== Phase 1: 会話ログ自動学習 =====

    def save_meeting_log(self, session_summary, user_id):
        """Phase 1: 会議ログを各ペルソナの学習データとして保存"""
        # ゲスト（user_id=None）はNULLのまま保存（外部キー制約のため0は使えない）
        topic = session_summary.get('topic', '')
        messages = session_summary.get('messages', [])
        saved_count = 0
        MAX_LOGS_PER_PERSONA = 100
        for msg in messages:
            persona_id = msg.get('persona_id', '')
            if persona_id in ['user', 'facilitator', '']:
                continue
            content_text = msg.get('content', '').strip()
            if len(content_text) < 30:
                continue
            current_count = get_learn_data_count(persona_id, user_id)
            if current_count >= MAX_LOGS_PER_PERSONA:
                continue
            log_content = "[議題]" + topic + "\n[発言]" + content_text + "\n[出典]会議ログ"
            self.add_learn_data(
                persona_id, log_content,
                source="会議ログ_" + topic[:20],
                user_id=user_id
            )
            saved_count += 1
        print("Phase 1: " + str(saved_count) + "件の会議ログを保存")
        return saved_count

    # ===== Phase 2: 発言パターン抽出・保存 =====

    def extract_and_save_patterns(self, session_summary, user_id):
        """Phase 2: 発言パターンを抽出して保存"""
        topic = session_summary.get('topic', '')
        messages = session_summary.get('messages', [])
        business_kw = ['ビジネス', '事業', '経営', '戦略', '市場', '売上', '顧客']
        social_kw = ['少子化', '人口', '社会', '政策', '環境', '教育']
        topic_category = 'business' if any(k in topic for k in business_kw)                         else 'social' if any(k in topic for k in social_kw)                         else 'general'
        for msg in messages:
            persona_id = msg.get('persona_id', '')
            if persona_id in ['user', 'facilitator', '']:
                continue
            text = msg.get('content', '')
            if len(text) < 50:
                continue
            opening_kw = ['天下', '古より', '孫子', 'かつて', '余の', '研究によれば', '歴史的に']
            objection_kw = ['しかし', 'されど', '一方', 'ただし', '懸念', 'リスク', '問題点']
            conclusion_kw = ['ゆえに', '結論', 'まとめ', '愚考', '提案', '推奨', '総じて']
            if any(k in text[:50] for k in opening_kw):
                save_persona_pattern(persona_id, user_id, 'opening', text[:100], topic_category)
            if any(k in text for k in objection_kw):
                save_persona_pattern(persona_id, user_id, 'objection', text[:100], topic_category)
            if any(k in text[-100:] for k in conclusion_kw):
                save_persona_pattern(persona_id, user_id, 'conclusion', text[-100:], topic_category)
        print("Phase 2: パターン保存完了（カテゴリ: " + topic_category + "）")

    # ===== Phase 3: 成長レベル判定 =====

    def get_evolution_level(self, persona_id, user_id):
        """Phase 3: 会議回数に基づく成長レベルを返す (level, count)"""
        if user_id is None:
            return 0, 0
        count = get_meeting_count(persona_id, user_id)
        if count == 0:
            return 0, count
        elif count < 4:
            return 1, count
        elif count < 10:
            return 2, count
        else:
            return 3, count

    # ===== Phase 3: 会議カウント =====

    def increment_persona_meeting_count(self, persona_id, user_id):
        """Phase 3: 会議参加回数をインクリメント"""
        if not user_id:
            return 0
        return increment_meeting_count(persona_id, user_id)

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
        if openai_key:
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

        # Phase 2: 発言パターンをプロンプトに反映
        if user_id:
            patterns = get_persona_patterns(persona['id'], user_id, limit=6)
            if patterns:
                opening = [p['pattern_text'] for p in patterns if p['pattern_type'] == 'opening']
                objection = [p['pattern_text'] for p in patterns if p['pattern_type'] == 'objection']
                conclusion = [p['pattern_text'] for p in patterns if p['pattern_type'] == 'conclusion']
                pattern_note = ''
                if opening:
                    pattern_note += '\n・発言冒頭の例：「' + opening[0][:60] + '…」'
                if objection:
                    pattern_note += '\n・反論時の例：「' + objection[0][:60] + '…」'
                if conclusion:
                    pattern_note += '\n・締めの例：「' + conclusion[0][:60] + '…」'
                if pattern_note:
                    prompt += '\n[あなたの発言スタイル（過去の会議から学習）]' + pattern_note + '\n'

        # Phase 3: 会議経験に応じた発言深度
        if user_id:
            meeting_count = get_meeting_count(persona['id'], user_id)
            if meeting_count == 0:
                evolution_note = '初めての会議です。基本的な立場と考えを丁寧に説明してください。'
            elif meeting_count < 3:
                evolution_note = 'これまで' + str(meeting_count) + '回の会議を経験しています。自分の立場を明確にしながら、他のメンバーの意見にも反応してください。'
            elif meeting_count < 10:
                evolution_note = 'これまで' + str(meeting_count) + '回の会議を経験しています。具体的な根拠や事例を示しながら、より深みのある発言をしてください。'
            else:
                evolution_note = 'これまで' + str(meeting_count) + '回の会議を経験したベテランです。他のメンバーの思考パターンを熟知した上で、過去の議論の積み重ねを踏まえた深い洞察を示してください。'
            prompt += '\n[あなたの経験値]\n' + evolution_note + '\n'

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
