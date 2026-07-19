"""
CONT-1 リファレンス実装（Chat側オラクル）
DBに依存しない純粋ロジックのみを抽出。Codeの実装はこれと同じ入出力になることを確認する。
"""

def fifo_pick_oldest_meeting_log(rows_created_asc):
    """
    rows_created_asc: [(id, decrypted_source), ...]  created_at昇順（最古が先頭）
    戻り値: 削除すべき最古の「会議ログ_」由来レコードのid。無ければNone。
    手動登録データ（source が '会議ログ_' で始まらない）はスキップして次を見る。
    """
    for row_id, source in rows_created_asc:
        if source and source.startswith('会議ログ_'):
            return row_id
    return None


def aggregate_speeches_by_persona(messages, min_len=30):
    """
    messages: [{'persona_id':.., 'content':..}, ...]
    戻り値: {persona_id: [content1, content2, ...]}
    user/facilitator/空persona_idは除外。30字未満の発言は除外。
    """
    result = {}
    for msg in messages:
        pid = msg.get('persona_id', '')
        if pid in ('user', 'facilitator', ''):
            continue
        text = (msg.get('content') or '').strip()
        if len(text) < min_len:
            continue
        result.setdefault(pid, []).append(text)
    return result


def build_summary_log(topic, speeches, max_chars=500):
    """1会議1件分の要約ログ本文を組み立てる"""
    joined = '\n'.join(speeches)
    truncated = joined[:max_chars]
    return f"[議題]{topic}\n[発言要約]{truncated}\n[出典]会議ログ"


def diversify_candidates(candidates, limit):
    """
    candidates: [{'content':.., 'source':.., 'similarity':float}, ...] 類似度降順で渡される想定
    資料由来・会議ログ由来を両方含むよう再配分し、類似度降順でlimit件返す。
    """
    def is_meeting_log(c):
        return bool(c['source']) and c['source'].startswith('会議ログ_')

    meeting_log = [c for c in candidates if is_meeting_log(c)]
    resource = [c for c in candidates if not is_meeting_log(c)]
    per_bucket = max(1, limit // 2)
    picked = resource[:per_bucket] + meeting_log[:per_bucket]
    picked_ids = {id(c) for c in picked}
    for c in candidates:
        if len(picked) >= limit:
            break
        if id(c) not in picked_ids:
            picked.append(c)
            picked_ids.add(id(c))
    picked.sort(key=lambda c: c['similarity'], reverse=True)
    return picked[:limit]


def category_fallback_query(query_fn, topic_category):
    """
    query_fn(use_category: bool) -> list
    topic_categoryが指定されていてカテゴリ一致が0件ならフォールバックで無条件取得する。
    """
    if topic_category:
        results = query_fn(True)
        if results:
            return results
    return query_fn(False)
