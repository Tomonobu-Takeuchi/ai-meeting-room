"""
persona_manager.py - ペルソナ管理（ユーザー認証 + RAG対応版）
"""
import uuid
import os
import random
import threading
from src.database import (
    get_connection, rows_to_dicts, row_to_dict,
    encrypt_value, decrypt_value,
    save_learn_data, update_learn_data_embedding,
    search_learn_data, get_learn_data_simple,
    get_learn_data_count, get_learn_data_counts_batch, get_all_learn_data, delete_learn_data,
    save_persona_pattern, get_persona_patterns,
    increment_meeting_count, get_meeting_count,
    ensure_growth_record, update_growth_conversation,
    update_growth_knowledge, calculate_and_save_maturity,
    get_growth_record, save_feedback_record, update_growth_c_axis
)

COLUMNS = ['id','user_id','name','avatar','description','personality',
           'speaking_style','background','color','role','is_default','created_at','voice_id',
           'source_persona_id','category','base_created_at']

def serialize_persona(d):
    """datetimeをstrに変換・不要フィールドを整理"""
    if not d:
        return d
    if 'created_at' in d and d['created_at'] is not None:
        d['created_at'] = str(d['created_at'])
    if 'base_created_at' in d and d['base_created_at'] is not None:
        d['base_created_at'] = str(d['base_created_at'])
    return d


_PERSONA_ENC_FIELDS = ['name', 'avatar', 'description', 'personality', 'speaking_style', 'background']


def _decrypt_persona(conn, d):
    """ペルソナdictの暗号化フィールドを復号する（平文はそのまま返す）"""
    for f in _PERSONA_ENC_FIELDS:
        if d.get(f):
            d[f] = decrypt_value(conn, d[f])
    return d


class PersonaManager:

    # ===== ペルソナ取得（user_id対応） =====

    def get_members_only(self, user_id=None):
        """memberロールのペルソナ取得（ユーザー固有のみ。T-02: デフォルト共有廃止）"""
        conn = get_connection()
        if user_id:
            rows = conn.run("""
                SELECT p.id, p.user_id, p.name, p.avatar, p.description, p.personality,
                       p.speaking_style, p.background, p.color, p.role, p.is_default,
                       p.created_at, p.voice_id, p.source_persona_id, p.category,
                       COALESCE(base.created_at, p.created_at) as base_created_at
                FROM personas p
                LEFT JOIN personas base ON p.source_persona_id = base.id
                WHERE p.role='member'
                  AND (
                    p.user_id = :user_id
                    OR (
                      p.user_id IS NULL
                      AND p.id NOT IN (
                        SELECT source_persona_id FROM personas
                        WHERE user_id = :user_id AND source_persona_id IS NOT NULL
                      )
                    )
                  )
                ORDER BY p.is_default DESC, p.created_at ASC
            """, user_id=user_id)
        else:
            rows = conn.run("""
                SELECT p.id, p.user_id, p.name, p.avatar, p.description, p.personality,
                       p.speaking_style, p.background, p.color, p.role, p.is_default,
                       p.created_at, p.voice_id, p.source_persona_id, p.category,
                       p.created_at as base_created_at
                FROM personas p
                WHERE p.role='member' AND p.user_id IS NULL
                ORDER BY p.created_at ASC
            """)
        result = []
        for r in rows:
            d = _decrypt_persona(conn, row_to_dict(COLUMNS, r))
            result.append(serialize_persona(d))
        conn.close()
        if result:
            counts = get_learn_data_counts_batch([p['id'] for p in result], user_id)
            for p in result:
                p['learn_count'] = counts.get(p['id'], 0)
        return result

    def get_facilitator(self, user_id=None):
        """ファシリテータ取得（T-02: user_id指定時はユーザー固有のみ）"""
        conn = get_connection()
        if user_id:
            rows = conn.run("""
                SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at, voice_id, source_persona_id, category FROM personas
                WHERE role='facilitator'
                  AND (user_id=:user_id OR user_id IS NULL)
                ORDER BY is_default DESC, created_at ASC LIMIT 1
            """, user_id=user_id)
        else:
            rows = conn.run("""
                SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at, voice_id, source_persona_id, category FROM personas
                WHERE role='facilitator' AND user_id IS NULL
                ORDER BY created_at ASC LIMIT 1
            """)
        if rows:
            d = _decrypt_persona(conn, row_to_dict(COLUMNS, rows[0]))
            conn.close()
            return serialize_persona(d)
        conn.close()
        return None

    def get_all_personas(self, user_id=None):
        conn = get_connection()
        if user_id:
            rows = conn.run("""
                SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at, voice_id, source_persona_id, category FROM personas
                WHERE (
                    user_id = :user_id
                    OR (
                      user_id IS NULL
                      AND id NOT IN (
                        SELECT source_persona_id FROM personas
                        WHERE user_id = :user_id AND source_persona_id IS NOT NULL
                      )
                    )
                  )
                ORDER BY role DESC, is_default DESC, created_at ASC
            """, user_id=user_id)
        else:
            rows = conn.run("""
                SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at, voice_id, source_persona_id, category FROM personas WHERE user_id IS NULL
                ORDER BY role DESC, created_at ASC
            """)
        result = []
        for r in rows:
            d = _decrypt_persona(conn, row_to_dict(COLUMNS, r))
            result.append(serialize_persona(d))
        conn.close()
        return result

    def get_persona_by_id(self, persona_id, user_id=None):
        conn = get_connection()
        if user_id:
            rows = conn.run("""
                SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at, voice_id, source_persona_id, category FROM personas
                WHERE id=:id AND user_id=:user_id
            """, id=persona_id, user_id=user_id)
        else:
            rows = conn.run("SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at, voice_id, source_persona_id, category FROM personas WHERE id=:id", id=persona_id)
        if rows:
            d = _decrypt_persona(conn, row_to_dict(COLUMNS, rows[0]))
            conn.close()
            return serialize_persona(d)
        conn.close()
        return None

    # meeting_room.py との互換性
    def get_persona(self, persona_id, user_id=None):
        return self.get_persona_by_id(persona_id, user_id)

    def get_personas_by_ids(self, ids, user_id=None):
        if not ids:
            return []
        conn = get_connection()
        if user_id:
            rows = conn.run("""
                SELECT id, user_id, name, avatar, description, personality,
                       speaking_style, background, color, role, is_default, created_at, voice_id, source_persona_id, category
                FROM personas
                WHERE id = ANY(:ids) AND (user_id=:user_id OR user_id IS NULL)
            """, ids=list(ids), user_id=user_id)
        else:
            rows = conn.run("""
                SELECT id, user_id, name, avatar, description, personality,
                       speaking_style, background, color, role, is_default, created_at, voice_id, source_persona_id, category
                FROM personas
                WHERE id = ANY(:ids)
            """, ids=list(ids))
        by_id = {}
        for r in rows:
            d = _decrypt_persona(conn, row_to_dict(COLUMNS, r))
            by_id[r[0]] = serialize_persona(d)
        conn.close()
        return [by_id[i] for i in ids if i in by_id]

    # ===== ペルソナ追加・更新・削除 =====

    def add_persona(self, data, user_id=None):
        persona_id = data.get('id') or str(uuid.uuid4())[:8]
        avatar_raw = data.get('avatar', '👤').strip() or '👤'
        # base64画像はそのまま保持、絵文字のみ4文字制限
        avatar_val = avatar_raw if avatar_raw.startswith('data:') else avatar_raw[:4]
        conn = get_connection()
        _enc = (lambda v: encrypt_value(conn, v)) if user_id is not None else (lambda v: v)
        conn.run("""
            INSERT INTO personas (id, user_id, name, avatar, description, personality,
                speaking_style, background, color, role, is_default, voice_id, is_deceased_confirmed)
            VALUES (:id, :user_id, :name, :avatar, :description, :personality,
                :speaking_style, :background, :color, :role, FALSE, :voice_id, :is_deceased_confirmed)
            ON CONFLICT DO NOTHING
        """,
        id=persona_id, user_id=user_id,
        name=_enc(data.get('name','').strip()),
        avatar=_enc(avatar_val),
        description=_enc(data.get('description','').strip()),
        personality=_enc(data.get('personality','').strip()),
        speaking_style=_enc(data.get('speaking_style','').strip()),
        background=_enc(data.get('background','').strip()),
        color=data.get('color','#8B5CF6'),
        role=data.get('role','member'),
        voice_id=data.get('voice_id') or None,
        is_deceased_confirmed=bool(data.get('is_deceased_confirmed', False)))
        if user_id is not None:
            rows = conn.run("""
                SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at, voice_id, source_persona_id, category FROM personas WHERE id=:id AND user_id=:user_id
            """, id=persona_id, user_id=user_id)
        else:
            rows = conn.run("""
                SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at, voice_id, source_persona_id, category FROM personas WHERE id=:id AND user_id IS NULL
            """, id=persona_id)
        if rows:
            d = _decrypt_persona(conn, row_to_dict(COLUMNS, rows[0]))
            conn.close()
            return serialize_persona(d)
        conn.close()
        return None

    def update_persona(self, persona_id, data, user_id=None):
        avatar_raw = data.get('avatar', '👤').strip() or '👤'
        # base64画像はそのまま保持、絵文字のみ4文字制限
        avatar_val = avatar_raw if avatar_raw.startswith('data:') else avatar_raw[:4]
        conn = get_connection()
        if user_id:
            _enc = lambda v: encrypt_value(conn, v)
            conn.run("""
                UPDATE personas SET
                    name=:name, avatar=:avatar, description=:description,
                    personality=:personality, speaking_style=:speaking_style,
                    background=:background, color=:color, voice_id=:voice_id
                WHERE id=:id AND user_id=:user_id
            """,
            id=persona_id, user_id=user_id,
            name=_enc(data.get('name','').strip()),
            avatar=_enc(avatar_val),
            description=_enc(data.get('description','').strip()),
            personality=_enc(data.get('personality','').strip()),
            speaking_style=_enc(data.get('speaking_style','').strip()),
            background=_enc(data.get('background','').strip()),
            color=data.get('color','#8B5CF6'),
            voice_id=data.get('voice_id') or None)
            rows = conn.run("""
                SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at, voice_id, source_persona_id, category FROM personas WHERE id=:id AND user_id=:user_id
            """, id=persona_id, user_id=user_id)
        else:
            conn.run("""
                UPDATE personas SET
                    name=:name, avatar=:avatar, description=:description,
                    personality=:personality, speaking_style=:speaking_style,
                    background=:background, color=:color, voice_id=:voice_id
                WHERE id=:id
            """,
            id=persona_id,
            name=data.get('name','').strip(),
            avatar=avatar_val,
            description=data.get('description','').strip(),
            personality=data.get('personality','').strip(),
            speaking_style=data.get('speaking_style','').strip(),
            background=data.get('background','').strip(),
            color=data.get('color','#8B5CF6'),
            voice_id=data.get('voice_id') or None)
            rows = conn.run("SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at, voice_id, source_persona_id, category FROM personas WHERE id=:id", id=persona_id)
        if rows:
            d = _decrypt_persona(conn, row_to_dict(COLUMNS, rows[0]))
            conn.close()
            return serialize_persona(d)
        conn.close()
        return None

    def copy_default_persona(self, default_persona_id, user_id):
        """
        デフォルトペルソナ(user_id=NULL)をユーザー専用コピーとして複製する。
        すでにコピーが存在する場合はそのコピーを返す。
        """
        conn = get_connection()
        existing = conn.run(
            "SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at, voice_id, source_persona_id, category FROM personas WHERE source_persona_id=:src AND user_id=:uid",
            src=default_persona_id, uid=user_id
        )
        if existing:
            d = _decrypt_persona(conn, row_to_dict(COLUMNS, existing[0]))
            conn.close()
            return serialize_persona(d)

        rows = conn.run(
            "SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at, voice_id, source_persona_id, category FROM personas WHERE id=:id AND user_id IS NULL",
            id=default_persona_id
        )
        if not rows:
            conn.close()
            return None
        # デフォルトペルソナは平文のためそのまま使用
        src = row_to_dict(COLUMNS, rows[0])

        new_id = f"{default_persona_id}_{str(user_id)[-6:]}"
        _enc = lambda v: encrypt_value(conn, v)
        conn.run(
            """INSERT INTO personas
               (id, user_id, name, avatar, description, personality,
                speaking_style, background, color, role, is_default,
                voice_id, source_persona_id, extra_settings)
               VALUES
               (:id, :user_id, :name, :avatar, :description, :personality,
                :speaking_style, :background, :color, :role, false,
                :voice_id, :source_persona_id, '{}')
               ON CONFLICT DO NOTHING
            """,
            id=new_id, user_id=user_id,
            name=_enc(src['name']),
            avatar=_enc(src.get('avatar', '')),
            description=_enc(src.get('description', '')),
            personality=_enc(src.get('personality', '')),
            speaking_style=_enc(src.get('speaking_style', '')),
            background=_enc(src.get('background', '')),
            color=src.get('color', '#667eea'),
            role=src.get('role', ''),
            voice_id=src.get('voice_id') or None,
            source_persona_id=default_persona_id
        )

        copied = conn.run(
            "SELECT id, user_id, name, avatar, description, personality, speaking_style, background, color, role, is_default, created_at, voice_id, source_persona_id, category FROM personas WHERE id=:id AND user_id=:uid",
            id=new_id, uid=user_id
        )
        if copied:
            d = _decrypt_persona(conn, row_to_dict(COLUMNS, copied[0]))
            conn.close()
            return serialize_persona(d)
        conn.close()
        return None

    def delete_persona(self, persona_id, user_id=None):
        protected = {'koumei', 'hideyoshi', 'professor', 'facilitator', 'elizabeth1'}
        if persona_id in protected:
            return False, 'デフォルトペルソナは削除できません'
        conn = get_connection()
        if user_id:
            rows = conn.run(
                "DELETE FROM personas WHERE id=:id AND user_id=:user_id RETURNING id",
                id=persona_id, user_id=user_id)
            conn.close()
            if not rows:
                return False, '該当するペルソナが見つかりません'
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

    # ===== Growth: 成熟度スコア管理 =====

    def ensure_growth(self, persona_id, user_id, app_type='meeting'):
        """persona_growthの初期レコードを作成（なければ）"""
        if user_id is None:
            return
        try:
            ensure_growth_record(persona_id, user_id, app_type)
        except Exception as e:
            print(f"Growth初期化エラー（無視）: {e}")

    def on_conversation_end(self, session_summary, user_id, app_type='meeting'):
        """会話終了時にgrowthレコードを更新（conversation_count + maturity再計算）"""
        if user_id is None:
            return
        members = session_summary.get('members', [])
        topic = session_summary.get('topic', '')
        for member in members:
            persona_id = member.get('id', '')
            if not persona_id or persona_id == 'facilitator':
                continue
            try:
                ensure_growth_record(persona_id, user_id, app_type)
                update_growth_conversation(persona_id, user_id, topic, app_type)
                # C軸：avg_session_length・profile_completeness更新
                from datetime import datetime as _dt
                created_at_str = session_summary.get('created_at')
                duration_min = None
                if created_at_str:
                    try:
                        started = _dt.fromisoformat(created_at_str)
                        duration_min = (_dt.now() - started).total_seconds() / 60
                    except Exception:
                        pass
                persona_data = self.get_persona(persona_id)
                if persona_data:
                    fields = [str(persona_data.get(f, '') or '') for f in
                              ['name', 'description', 'personality', 'speaking_style', 'background']]
                    filled = sum(1 for f in fields if f.strip())
                    profile_comp = (filled / len(fields)) * 40
                else:
                    profile_comp = None
                update_growth_c_axis(persona_id, user_id,
                                     profile_completeness=profile_comp,
                                     avg_session_minutes=duration_min,
                                     app_type=app_type)
                calculate_and_save_maturity(persona_id, user_id, app_type)
            except Exception as e:
                print(f"Growth更新エラー（無視）: {e}")

    def on_learn_data_added(self, persona_id, user_id, content, app_type='meeting'):
        """学習データ追加時にdoc_token_countを更新"""
        if user_id is None:
            return
        try:
            ensure_growth_record(persona_id, user_id, app_type)
            token_count = len(content) // 4  # 簡易トークン数推定
            update_growth_knowledge(persona_id, user_id, token_count, app_type)
            calculate_and_save_maturity(persona_id, user_id, app_type)
        except Exception as e:
            print(f"Growth知識更新エラー（無視）: {e}")

    def get_growth(self, persona_id, user_id, app_type='meeting'):
        """成熟度レコードを取得"""
        if user_id is None:
            return None
        try:
            return get_growth_record(persona_id, user_id, app_type)
        except Exception as e:
            print(f"Growth取得エラー（無視）: {e}")
            return None

    # 成熟度レベル名（引き継ぎ資料の10段階）
    MATURITY_LEVEL_NAMES = {
        1: "入門", 2: "見習い", 3: "研究生", 4: "助手", 5: "同僚",
        6: "専門家", 7: "論客", 8: "賢者", 9: "師匠", 10: "覚醒"
    }

    def save_feedback(self, persona_id, user_id, session_id, rating, detail_category, correct_response, add_to_learn=False, app_type='meeting'):
        """フィードバックを保存し、必要に応じてpersona_learnにも追加"""
        if user_id is None:
            return
        try:
            save_feedback_record(persona_id, user_id, session_id, rating, detail_category, correct_response, app_type)
            calculate_and_save_maturity(persona_id, user_id, app_type)
            if add_to_learn:
                update_growth_c_axis(persona_id, user_id,
                                     increment_tuning=True, app_type=app_type)
                if correct_response and correct_response.strip():
                    self.add_learn_data(persona_id, correct_response, 'feedback', user_id)
        except Exception as e:
            print(f"フィードバック保存エラー（無視）: {e}")

    def get_maturity_label(self, level):
        return self.MATURITY_LEVEL_NAMES.get(level, "入門")

    # ===== RAG学習データ =====

    def add_learn_data(self, persona_id, content, source='', user_id=None):
        # テキストをDBに即時保存（embedding=NULL）
        save_learn_data(persona_id, user_id, content, source, embedding_vector=None)

        # Embedding生成はバックグラウンドスレッドで非同期実行
        openai_key = os.environ.get('OPENAI_API_KEY', '')
        if openai_key:
            def _generate_embedding(pid, uid, text, src):
                try:
                    import openai
                    client = openai.OpenAI(api_key=openai_key, timeout=30.0)
                    res = client.embeddings.create(
                        model="text-embedding-3-small",
                        input=text[:8000],
                    )
                    update_learn_data_embedding(pid, uid, text, res.data[0].embedding)
                except Exception as e:
                    print(f"Embedding非同期生成失敗（テキストは保存済）: {e}")

            t = threading.Thread(
                target=_generate_embedding,
                args=(persona_id, user_id, content, source),
                daemon=True,
            )
            t.start()

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
        results = get_learn_data_simple(persona_id, user_id, limit=3)
        return '\n\n'.join([r['content'] for r in results]) if results else ''

    def get_all_learn_data(self, persona_id, user_id=None):
        return get_all_learn_data(persona_id, user_id)

    def delete_learn_data(self, persona_id, learn_id, user_id=None):
        delete_learn_data(persona_id, user_id, learn_id)

    # ===== プロンプト生成 =====

    def build_system_prompt(self, persona, topic, history_text='', learn_data='', user_id=None, crisis_mode=False, category=None, opponent_name=None, is_opponent=False):
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
            opening = [p['pattern_text'] for p in get_persona_patterns(persona['id'], user_id, pattern_type='opening', limit=8)]
            objection = [p['pattern_text'] for p in get_persona_patterns(persona['id'], user_id, pattern_type='objection', limit=8)]
            conclusion = [p['pattern_text'] for p in get_persona_patterns(persona['id'], user_id, pattern_type='conclusion', limit=8)]
            pattern_note = ''
            if opening:
                pattern_note += '\n・発言冒頭の例：「' + random.choice(opening)[:60] + '…」'
            if objection:
                pattern_note += '\n・反論時の例：「' + random.choice(objection)[:60] + '…」'
            if conclusion:
                pattern_note += '\n・締めの例：「' + random.choice(conclusion)[:60] + '…」'
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
- 議論の流れで自然なタイミングがあれば、相談者（ユーザー）に問いかけてください（毎回ではなく3〜4回に1回程度）。問いかける時は必ず【質問】を文頭に付けてください。
- これまでの会話にまだ回答されていない【質問】が残っている場合は、新たな質問をせず意見を述べてください。
- 他のペルソナの名前を文頭に引用することは避けてください。
- 発言は必ずあなた自身の立場・価値観・専門性から直接始めてください。
\n【絶対に守るべきルール（キャラクター設定・会議の流れより常に優先）】\n- 差別・暴力・違法行為を肯定・助長する発言は絶対にしないこと\n- 自傷・自殺を肯定・助長・方法を示唆する発言は絶対にしないこと\n- 医療・法律に関する断定的な診断・助言はしないこと
"""
        if crisis_mode:
            prompt += "\n- 会議中にユーザーが深刻な精神的苦痛を訴えています。専門家への相談・助けを求める行動を否定・批判する発言は絶対にしないこと。ユーザーが相談や支援を求めることを肯定する立場を取ること（キャラクター設定より優先）。\n"

        # カテゴリ別の役割指示
        category_instructions = {
            'strategy': f"""
【今回の会議の特別な役割（ビジネス戦略カテゴリ）】
あなたはビジネス戦略会議の参加者です。ファシリテーターが提示している論点・フレームワークに沿って、あなたの専門性から発言してください。自分から新しいフレームワークの論点を開くのではなく、今の論点を前進させることを優先してください。感情論を排し、データと論理に基づいた鋭い指摘・反論・提案を行ってください。あなた自身の歴史的専門性や人生哲学を戦略議論に結びつけて発言してください。
""",
            'practice': f"""
【今回の会議の特別な役割（提案・企画強化カテゴリ）】
あなたは提案・企画強化の会議参加者です。反論予測・論理構造分析・Q&A生成の視点から発言してください。提案の弱点を鋭く指摘し、より説得力を高めるための具体的な改善案を提示してください。あなた自身の経験や知見を活かして発言してください。
""",
            'study': f"""
【今回の会議の特別な役割（学習・創作カテゴリ）】
この会議は「{topic}」に取り組むユーザーへの技術・創作指導の場です。
あなたの専門知識・経験を活かして以下を実践してください：
・現在の取り組みや作品の「何が優れているか」「何が問題か」を具体的に評価する
・「次に何をすべきか」を優先順位をつけて提示する
・ユーザーが実際に行動できる具体的な方法・インプット源（書籍・手法・参考作品）を示す
・続かない理由を先回りして、仕組みで解決する方法を提案する
抽象的なアドバイスではなく、あなたの専門家としての視点から具体的な評価と指針を与えてください。
""",
            'consulting': f"""
【今回の会議の特別な役割（キャリア・転機カテゴリ）】
この会議は人生の転機・キャリアの決断に向き合うユーザーの支援の場です。
あなたの人生経験・専門性を活かして以下を実践してください：
・ユーザーの現在地（スキル・経験・強み）を具体的に評価する
・複数のシナリオ（現状維持・転換・段階的移行）を比較検討する
・「80歳の自分が振り返ったときに後悔しないか」という問いを軸に判断を促す
・感情と論理の両面から寄り添いながら、最終的にはユーザー自身が決断できるよう支援する
""",
            'relationship': f"""
【今回の会議の特別な役割（人間関係・交渉カテゴリ）】
この会議は人間関係の課題に向き合うユーザーへの支援の場です。
・問題の本質を「相手の性格の問題」と「役割構造の問題」に切り分けて整理する
・ユーザーの立場・感情・ニーズと、相手の立場・感情・ニーズの両方を推定する
・「境界線の設定」「対話と理解」「適切な距離の確保」の3つのアプローチから助言する
・深刻なハラスメント・精神的苦痛を感じている場合は専門家への相談を促す
""",
        }
        if category and category in category_instructions:
            prompt += category_instructions[category]

        # 相手役の特別な役割ブロック
        if is_opponent and opponent_name:
            prompt += f"""
【今回の特別な役割（相手役）】
あなたは「{opponent_name}役」として発言してください。
ユーザーの状況：{topic}
相手の立場から、あなたのキャラクターで自然に応答してください。

守るべき制約：
・ユーザーを過度に攻撃・否定し続けるのではなく、「相手の言い分がある人物」として振る舞うこと
・自傷・自殺・逃避を肯定する発言は絶対にしないこと
・会議の最後には必ず1つ「理解できる点」を認めること
"""

        if history_text:
            prompt += f"\n【これまでの会話】\n{history_text}"
        return prompt

    def build_facilitator_prompt(self, facilitator, topic, history_text, mode='guide', member_ids=None, crisis_mode=False, category=None, phase='diverge'):
        if mode == 'opening':
            instruction = (
                "【質問】と冒頭に必ず付けて、相談者（ユーザー）に直接語りかけてください。\n"
                "「今の状況」と「特に気になっていること」の2点を、\n"
                "1〜2文のシンプルな言葉で聞いてください。100字以内で。\n"
                "例：【質問】まず現状を教えてください。特に気になっていることは何ですか？"
            )
        elif mode == 'closing':
            instruction = (
                "議論が深まってきました。ここで相談者（ユーザー）に確認してください。\n"
                "出てきた方向性・選択肢を簡潔に整理した上で、「どちらを優先したいですか？」"
                "または「この方向性で進めてよいですか？」と問いかけてください。200字以内で。"
            )
        elif mode == 'nominate':
            member_ids_str = ', '.join(member_ids) if member_ids else '（参加者から選択）'
            instruction = (
                "議論を一言で整理した上で、次に発言すべき参加者を1人指名してください。\n"
                + ("議論が議題の本筋から逸れている場合は、一言で本筋に戻してから指名してください。\n" if phase == 'converge' else "")
                + f"必ず「【指名:persona_id】」の形式でIDを文中に含めてください。\n"
                f"指名できるpersona_idは以下から選んでください：{member_ids_str}\n"
                "例：【指名:koumei】孔明殿、戦略的な観点からご意見をお聞かせください。\n"
                "100字以内で。"
            )
        elif mode == 'summarize':
            instruction = "議論全体を振り返り、各メンバーの主な意見・共通点・相違点・結論を整理してください。"
        else:
            # カテゴリ別の進行指示
            question_rule = "ユーザーへの質問がある場合は、必ず発言の末尾に【質問】〇〇〇〇 という形式で質問を記述してください。"
            category_guide = {
                'strategy': (
                    "SWOT・4P・OKR・競合分析のフレームワークを活用し、戦略議論を深化させる質問を投げかけてください。参加者の発言を戦略的視点で整理・統合してください。\n"
                    "議論の進行を促し、次の論点や深掘りすべき点を提示してください。\n"
                    + question_rule
                ),
                'practice': (
                    "反論予測・論理構造・Q&A生成の観点から議論を促進してください。提案の説得力を高めるための具体的な問いを参加者に投げかけてください。\n"
                    "議論の進行を促し、次の論点や深掘りすべき点を提示してください。\n"
                    + question_rule
                ),
                'study': (
                    "この会議は学習・創作支援の場です。以下の流れで進行してください。\n"
                    "序盤：「まず現在どこまで取り組んでいるか教えてください」と現在地確認から入る。\n"
                    "中盤：賢人たちの評価・改善点が出てきたら「では具体的にどう進めるか考えましょう」と行動計画に誘導する。\n"
                    "終盤：「続けるための仕組みを一緒に考えましょう」と継続設計に誘導する。\n"
                    "議論の進行を促し、次の論点や深掘りすべき点を提示してください。\n"
                    + question_rule
                ),
                'consulting': (
                    "この会議はキャリア・転機の支援の場です。以下の流れで進行してください。\n"
                    "序盤：「まず今の仕事で得てきたものを整理しましょう」とキャリア資産の棚卸しから入る。\n"
                    "中盤：「3つの選択肢（現状維持・転換・段階的移行）をそれぞれ考えてみましょう」とシナリオ設計に移行する。\n"
                    "終盤：「80歳の自分が振り返ったとき」という問いを投げかけて後悔最小化の軸に着地させる。\n"
                    "議論の進行を促し、次の論点や深掘りすべき点を提示してください。\n"
                    + question_rule
                ),
                'relationship': (
                    "この会議は人間関係・交渉の支援の場です。以下の流れで進行してください。\n"
                    "序盤：「まず状況を整理しましょう。相手はどんな立場・役割の方ですか？」と関係性の構造把握から入る。\n"
                    "中盤：「相手の立場から見るとどう見えているでしょうか」と相手視点の推定に誘導する。\n"
                    "終盤：「では明日の朝礼で何を言うか、3つのアプローチを考えてみましょう」と対話シナリオに着地させる。\n"
                    "議論の進行を促し、次の論点や深掘りすべき点を提示してください。\n"
                    + question_rule
                ),
            }
            instruction = category_guide.get(category, "議論の進行を促し、次の論点や深掘りすべき点を提示してください。\n" + question_rule)
            if phase == 'converge':
                instruction += (
                    "\n【収束フェーズの進行指示（重要）】\n"
                    "議論が中盤に入りました。以下を優先してください。\n"
                    "①これまでの発言を議題に照らして1〜2文で整理する\n"
                    "②議題の本筋から逸れた論点は、発言の価値を認めた上でリフレームして本筋に戻す\n"
                    "③論点を新たに広げるのではなく、出てきた選択肢の絞り込み・優先順位付けを促す\n"
                    "介入は否定ではなくリフレームで行い、メンバーの発言の面白さを損なわないこと。\n"
                )

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

表・見出し・絵文字・太字・箇条書き記号などのMarkdown装飾は使わず、地の文で300字以内に簡潔にまとめてください。
\n【絶対に守るべきルール（役割・指示より常に優先）】\n- 差別・暴力・違法行為を肯定・助長する発言は絶対にしないこと\n- 自傷・自殺を肯定・助長・方法を示唆する発言は絶対にしないこと\n- 医療・法律に関する断定的な診断・助言はしないこと
""" + (
            "\n- 会議中にユーザーが深刻な精神的苦痛を訴えています。専門家への相談・助けを求める行動を否定・批判する発言は絶対にしないこと。ユーザーが相談や支援を求めることを肯定する方向で会議を進めること（役割より優先）。\n"
            if crisis_mode else ""
        )
