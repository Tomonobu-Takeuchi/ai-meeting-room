# test_is_earlybird_fallback.py
# is_earlybird取得部分（main.py L2466-2476）の単体テスト
# .get()失敗時のフォールバックが正しく機能することを検証する

class FakeStripeObjectGetFails:
    """.get()が例外を出すが[]記法は動く、本番で実際に発生したケースを模したダミー"""
    def __init__(self, data):
        self._data = data
    def get(self, key, default=None):
        raise AttributeError("get() is not supported on this object (simulated)")
    def __getitem__(self, key):
        return self._data[key]
    def __bool__(self):
        return bool(self._data)

class FakeStripeObjectNormal:
    """.get()が正常に動く既存の正常系ケース"""
    def __init__(self, data):
        self._data = data
    def get(self, key, default=None):
        return self._data.get(key, default)
    def __getitem__(self, key):
        return self._data[key]
    def __bool__(self):
        return bool(self._data)


def extract_is_earlybird(meta_raw):
    # ⚠️ main.py L2466-2476 と一字一句同じロジックをここに複製すること。
    # 複製後、必ずdiffでmain.pyの実コードと完全一致しているか確認してから実行すること。
    try:
        raw_eb = (meta_raw.get('is_earlybird') or '0') if meta_raw else '0'
    except Exception as e1:
        print(f"[test] is_earlybird meta.get失敗({e1}) → meta['is_earlybird']を試行")
        try:
            raw_eb = str(meta_raw['is_earlybird']) if meta_raw else '0'
        except Exception as e2:
            print(f"[test] meta['is_earlybird']も失敗: {e2}")
            raw_eb = '0'
    return (raw_eb == '1')


def run():
    cases = [
        ("ケース1：get()失敗・is_earlybird=1（本番で実際に発生したケース）",
         FakeStripeObjectGetFails({'user_id': '999', 'payment_type': 'pro', 'is_earlybird': '1'}), True),
        ("ケース2：get()失敗・is_earlybird=0",
         FakeStripeObjectGetFails({'user_id': '999', 'payment_type': 'standard', 'is_earlybird': '0'}), False),
        ("ケース3：get()正常・is_earlybird=1（既存正常系）",
         FakeStripeObjectNormal({'user_id': '999', 'payment_type': 'pro', 'is_earlybird': '1'}), True),
        ("ケース4：get()正常・is_earlybird=0（既存正常系）",
         FakeStripeObjectNormal({'user_id': '999', 'payment_type': 'standard', 'is_earlybird': '0'}), False),
        ("ケース5：get()失敗・is_earlybirdキー自体が存在しない",
         FakeStripeObjectGetFails({'user_id': '999', 'payment_type': 'pro'}), False),
    ]

    print("\n=== is_earlybird フォールバック検証結果 ===")
    all_pass = True
    for name, meta, expected in cases:
        actual = extract_is_earlybird(meta)
        status = "OK" if actual == expected else "NG"
        if actual != expected:
            all_pass = False
        print(f"[{status}] {name}: actual={actual} expected={expected}")

    print(f"\n総合結果: {'全件PASS' if all_pass else '失敗あり（要修正）'}")
    return all_pass


if __name__ == "__main__":
    import sys
    sys.exit(0 if run() else 1)
