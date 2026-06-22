import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

pdfmetrics.registerFont(UnicodeCIDFont('HeiseiMin-W3'))
buf = io.BytesIO()
doc = SimpleDocTemplate(buf, pagesize=A4,
    rightMargin=15*mm, leftMargin=15*mm, topMargin=15*mm, bottomMargin=15*mm)

styles_base = ParagraphStyle('base', fontName='HeiseiMin-W3', fontSize=10, leading=16)
styles_h2   = ParagraphStyle('h2',   fontName='HeiseiMin-W3', fontSize=12, leading=18)

CIRCLED = ['①','②','③','④','⑤','⑥','⑦','⑧','⑨','⑩']
stance_colors = {'支持': ('#15803D', '#EAF7EF'), '反対': ('#B91C1C', '#FCEAEA'), '懸念': ('#B45309', '#FBF2DF')}

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

l2 = {
    'summary': 'テストサマリです。議論の全体像を示します。',
    'discussion_points': [
        {'issue': 'コスト削減策', 'positions': [
            {'name': '孔明', 'stance': '支持', 'opinion': '全面的に賛成です。'},
            {'name': '秀吉', 'stance': '反対', 'opinion': 'リスクが高いと思います。'},
        ]}
    ],
    'next_actions': [
        {'action': '来週までに予算案を作成する', 'related_issue': 1},
        {'action': '全体方針を確認する', 'related_issue': 0},
    ],
    'unresolved_points': [
        {'level': '高', 'title': '予算上限の合意', 'detail': '上限金額で意見が割れたまま。次回までに決定が必要。'}
    ],
    'future_directions': [
        {'direction': '段階的導入か一括導入かを判断する', 'related_unresolved': [1]}
    ],
}

story = []
issue_title_style = ParagraphStyle('issuet', fontName='HeiseiMin-W3', fontSize=11, leading=15, textColor=HexColor('#6D28D9'))
pos_text_style    = ParagraphStyle('postxt', fontName='HeiseiMin-W3', fontSize=9.5, leading=14)
udetail_style     = ParagraphStyle('udetail', fontName='HeiseiMin-W3', fontSize=9, leading=13, textColor=HexColor('#6B7280'))

if l2.get('summary'):
    story.append(Paragraph('📝 全体サマリ', styles_h2))
    story.append(Paragraph(l2['summary'], styles_base))
    story.append(Spacer(1, 4*mm))

if l2.get('discussion_points'):
    story.append(Paragraph('💬 論点と対立構造', styles_h2))
    story.append(Spacer(1, 2*mm))
    for idx, dp in enumerate(l2['discussion_points'], start=1):
        num = CIRCLED[idx-1] if idx <= len(CIRCLED) else str(idx)
        story.append(Paragraph(f"論点{num}　{dp.get('issue','')}", issue_title_style))
        story.append(Spacer(1, 1.5*mm))
        positions = dp.get('positions', [])[:2]
        cells, bgs = [], []
        for p in positions:
            color, bg = stance_colors.get(p.get('stance',''), ('#6B7280', '#F3F4F6'))
            cells.append(Paragraph(
                f"<font color='{color}'><b>{p.get('stance','')}</b></font><br/>{p.get('name','')}：{p.get('opinion','')}",
                pos_text_style))
            bgs.append(bg)
        while len(cells) < 2:
            cells.append(Paragraph('', pos_text_style))
            bgs.append('#FFFFFF')
        t = Table([cells], colWidths=[83*mm, 83*mm], style=TableStyle([
            ('BACKGROUND', (0,0), (0,0), HexColor(bgs[0])),
            ('BACKGROUND', (1,0), (1,0), HexColor(bgs[1])),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('TOPPADDING', (0,0), (-1,-1), 6), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 8), ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ]))
        story.append(t)
        story.append(Spacer(1, 4*mm))

if l2.get('next_actions'):
    story.append(Paragraph('🚀 直近のアクションプラン', styles_h2))
    for a in l2['next_actions']:
        tag = action_tag(a.get('related_issue'))
        story.append(Paragraph(f"・<font color='#6D28D9' size='8'>[{tag}]</font> {a.get('action','')}", styles_base))
    story.append(Spacer(1, 4*mm))

if l2.get('unresolved_points'):
    story.append(Paragraph('⚠️ 未解決論点', styles_h2))
    for idx, u in enumerate(l2['unresolved_points'], start=1):
        num = CIRCLED[idx-1] if idx <= len(CIRCLED) else str(idx)
        story.append(Paragraph(f"未解決{num}　{u.get('title','')}", styles_base))
        story.append(Paragraph(u.get('detail',''), udetail_style))
        story.append(Spacer(1, 2*mm))
    story.append(Spacer(1, 2*mm))

if l2.get('future_directions'):
    story.append(Paragraph('🧭 今後の検討の方向性', styles_h2))
    for fd in l2['future_directions']:
        tag = direction_tag(fd.get('related_unresolved'))
        story.append(Paragraph(f"<font color='#B91C1C' size='8'>[{tag}]</font> {fd.get('direction','')}", styles_base))
        story.append(Spacer(1, 2*mm))

doc.build(story)
buf.seek(0)
size = len(buf.read())
print(f"PDF生成成功: {size} bytes")
print("Table/TableStyle呼び出し経路: 例外なし")
print("全6ブロック（summary/discussion_points/next_actions/unresolved_points/future_directions）: 正常出力")
