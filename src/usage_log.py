"""
AI-PERSONA会議室 - API使用量ログ（COST-1 計測用・一時的）

Anthropic APIの全呼び出しについて、トークン数・処理時間・文脈情報を
機械可読な1行形式でログ出力する。追加のAPI課金は発生しない
（usageはレスポンスに元から含まれている値を読むだけ）。

出力形式（key=value のスペース区切り）：
  [USAGE] tag=persona model=claude-sonnet-4-6 in=1328 out=424 cache_w=0 cache_r=0
          stop=end_turn sid=ab12 ms=3200 n_msg=2 n_mem=4 cat=strategy pid=koumei

【重要】COST-1の計測完了後、本ファイルと各呼び出し箇所の log_usage() 行は
       すべて削除すること。恒久的な機能ではない。
（2026年8月8日 COST-1 にて新設）
"""


def log_usage(tag, resp, sid="", **extra):
    """API使用量と文脈情報を1行でログ出力する。

    Args:
        tag:   呼び出し箇所の識別子（例 "layer1", "persona"）
        resp:  messages.create() の戻り値、または final message
        sid:   session_id
        extra: 解析用の追加項目。ms(処理時間ミリ秒) / n_msg(その時点の発言数)
               / n_mem(参加ペルソナ数) / cat(カテゴリ) / pid(ペルソナID)
               / mode(ファシリテータのmode) / out_chars(出力文字数)

    ログ出力の失敗が本処理を止めてはならないため、全体をtryで囲む。
    SDKのバージョンによって属性が無い場合があるため getattr() を使う
    （Stripe SDK 7.x と同様、.get() は使わない）。
    """
    try:
        u = getattr(resp, "usage", None) or resp
        parts = [
            "tag={}".format(tag),
            "model={}".format(getattr(resp, "model", "?")),
            "in={}".format(getattr(u, "input_tokens", None)),
            "out={}".format(getattr(u, "output_tokens", None)),
            "cache_w={}".format(getattr(u, "cache_creation_input_tokens", None)),
            "cache_r={}".format(getattr(u, "cache_read_input_tokens", None)),
            "stop={}".format(getattr(resp, "stop_reason", None)),
            "sid={}".format(sid),
        ]
        for k, v in extra.items():
            # 値に空白・改行が混ざると集計が壊れるため除去する
            s = str(v).replace(" ", "_").replace("\n", "").replace("\t", "")
            parts.append("{}={}".format(k, s))
        print("[USAGE] " + " ".join(parts), flush=True)
    except Exception as e:
        print("[USAGE] log failed tag={} err={}".format(tag, e), flush=True)


def log_ext_usage(tag, provider, **kw):
    """Anthropic以外の外部API（OpenAI等）の使用量をログ出力する。

    Args:
        tag:      呼び出し箇所の識別子（例 "embedding", "tts", "whisper"）
        provider: "openai" など
        kw:       model / tokens(埋め込み) / chars(TTS) / sec(音声長)
                  / ms(処理時間) / pid(ペルソナID) など

    Anthropic側と区別するため接頭辞は [EXTUSAGE] とする。
    ログ出力の失敗が本処理を止めてはならないため、全体をtryで囲む。
    """
    try:
        parts = ["tag={}".format(tag), "provider={}".format(provider)]
        for k, v in kw.items():
            s = str(v).replace(" ", "_").replace("\n", "").replace("\t", "")
            parts.append("{}={}".format(k, s))
        print("[EXTUSAGE] " + " ".join(parts), flush=True)
    except Exception as e:
        print("[EXTUSAGE] log failed tag={} err={}".format(tag, e), flush=True)
