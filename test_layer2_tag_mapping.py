CIRCLED = ['①','②','③','④','⑤','⑥','⑦','⑧','⑨','⑩']

def action_tag(related_issue):
    ri = related_issue or 0
    if not ri:
        return "全体"
    if ri <= len(CIRCLED):
        return f"論点{CIRCLED[ri-1]}"
    return f"論点{ri}"

def direction_tag(related_unresolved):
    refs = related_unresolved or []
    if not refs:
        return ""
    return "未解決" + "".join(CIRCLED[r-1] if r <= len(CIRCLED) else str(r) for r in refs)

def run():
    cases = [
        ("ケース1：related_issue=1（通常）", action_tag(1), "論点①"),
        ("ケース2：related_issue=0（全体）", action_tag(0), "全体"),
        ("ケース3：related_issueキー自体が無い（None想定）", action_tag(None), "全体"),
        ("ケース4：related_issue=11（CIRCLED範囲外）", action_tag(11), "論点11"),
        ("ケース5：related_unresolved=[1,2]（複数参照）", direction_tag([1, 2]), "未解決①②"),
        ("ケース6：related_unresolved=[]（空配列）", direction_tag([]), ""),
        ("ケース7：related_unresolved=[3]（単一参照）", direction_tag([3]), "未解決③"),
        ("ケース8：related_unresolvedキー自体が無い（None想定）", direction_tag(None), ""),
    ]
    print("\n=== Layer2タグ変換ロジック検証結果 ===")
    all_pass = True
    for name, actual, expected in cases:
        status = "OK" if actual == expected else "NG"
        if actual != expected:
            all_pass = False
        print(f"[{status}] {name}: actual={actual!r} expected={expected!r}")
    print(f"\n総合結果: {'全件PASS' if all_pass else '失敗あり（要修正）'}")
    return all_pass

if __name__ == "__main__":
    import sys
    sys.exit(0 if run() else 1)
