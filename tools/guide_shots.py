"""產生操作說明用的截圖（示範模式、時間固定在 2026-10-05 週一 09:50），自動畫紅框與編號。
用法：python tools/guide_shots.py   → 輸出到 guide/"""
import io
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "guide"
OUT.mkdir(exist_ok=True)
URL = (ROOT / "index.html").as_uri()
FONT = ImageFont.truetype(r"C:\Windows\Fonts\msjhbd.ttc", 22)
RED = (220, 38, 38)
NOW = datetime(2026, 10, 5, 9, 50)


def box(page, sels):
    if isinstance(sels, str):
        sels = [sels]
    bs = []
    for s in sels:
        loc = page.locator(s)
        for i in range(loc.count()):
            b = loc.nth(i).bounding_box()
            if b and b["width"] > 0:
                bs.append(b)
    if not bs:
        raise RuntimeError("找不到元素：%s" % sels)
    return [min(b["x"] for b in bs), min(b["y"] for b in bs),
            max(b["x"] + b["width"] for b in bs), max(b["y"] + b["height"] for b in bs)]


def shot(page, name, marks, clip=None, pad=16):
    rects = [(box(page, s), n, pos) for s, n, pos in marks]
    img = Image.open(io.BytesIO(page.screenshot(full_page=True))).convert("RGB")
    ox = oy = 0
    if clip:
        c = box(page, clip)
        ox, oy = max(0, c[0] - pad), max(0, c[1] - pad)
        img = img.crop((ox, oy, min(img.width, c[2] + pad), min(img.height, c[3] + pad)))
    d = ImageDraw.Draw(img)
    for (x1, y1, x2, y2), n, pos in rects:
        x1, y1, x2, y2 = x1 - ox - 4, y1 - oy - 4, x2 - ox + 4, y2 - oy + 4
        d.rounded_rectangle([x1, y1, x2, y2], radius=8, outline=RED, width=3)
        r = 16
        cx, cy = {"tl": (x1, y1), "tr": (x2, y1), "l": (x1 - r - 4, (y1 + y2) / 2),
                  "r": (x2 + r + 4, (y1 + y2) / 2), "bl": (x1, y2), "br": (x2, y2)}[pos]
        cx = min(max(cx, r + 2), img.width - r - 2)
        cy = min(max(cy, r + 2), img.height - r - 2)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=RED, outline="white", width=2)
        d.text((cx, cy), str(n), font=FONT, fill="white", anchor="mm")
    img.save(OUT / (name + ".png"), optimize=True)
    print("saved", name)


def cell(date, pid, slot):
    return f'td.cell[data-date="{date}"][data-pid="{pid}"][data-slot="{slot}"]'


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1500, "height": 950}, device_scale_factor=1)
    ctx.route("**/*gstatic.com/**", lambda r: r.abort())
    page = ctx.new_page()
    page.clock.set_fixed_time(NOW)
    page.on("dialog", lambda d: d.accept())

    # 01 登入畫面（非示範模式）
    page.goto(URL); page.wait_for_timeout(500)
    page.evaluate("document.getElementById('login-msg').textContent = ''")
    shot(page, "01-login", [("#btn-login", 1, "r")], clip=".login-card", pad=50)

    page.goto(URL + "?demo"); page.wait_for_timeout(500)
    page.evaluate("localStorage.clear()"); page.reload(); page.wait_for_timeout(600)
    D = "2026-10-05"
    # 多放幾筆讓畫面像真的
    page.evaluate("""d => store.update({
      ['bk/'+d+'/e155/p3']: {title:'一年級認識師長活動', by:'guide@lsps.tp.edu.tw', name:'輔導組長', unit:'輔導室', status:'ok', at: Date.now()},
      ['bk/'+d+'/e159/nap']: {title:'糾察隊訓練', by:'guard@lsps.tp.edu.tw', name:'蔡老師', unit:'學務處', status:'wait', at: Date.now()},
      ['bk/'+d+'/e156/p6']: {title:'學年會議', by:'teacher-a@lsps.tp.edu.tw', name:'王小明老師', unit:'教務處', status:'ok', at: Date.now()},
      ['bk/'+d+'/e176/aft']: {title:'劇團排練', by:'drama@lsps.tp.edu.tw', name:'林老師', unit:'學務處', status:'ok', at: Date.now(), time:'16:00-17:30'},
    })""", D)
    page.wait_for_timeout(200)

    # 02 每日總覽
    shot(page, "02-day", [
        (["#view-day .toolbar > button:first-child", "#day-chips"], 1, "tl"),
        ("#view-day .legend", 2, "tl"),
        ("#day-grid tbody tr:nth-child(4) th", 3, "l"),
        ("#day-grid thead th.now", 4, "tr"),
        (cell(D, "e155", "p3"), 5, "bl"),
    ], clip=["header", "#day-grid tbody tr:nth-child(9)"], pad=0)

    # 03 點空格 → 借用對話框
    page.click(cell(D, "e155", "p6")); page.wait_for_timeout(150)
    page.fill("#book-title", "四年級閱讀講座"); page.fill("#book-unit", "教務處設備組")
    shot(page, "03-book", [("#book-sum", 1, "l"), ("#book-slots", 2, "l"), ("#book-title", 3, "l"),
                           ("#book-ov .radio", 4, "l"), ("#book-ok", 5, "l")], clip="#book-ov .modal")
    page.evaluate("closeOv('book-ov')")

    # 04 拖曳一次選多格
    a = page.locator(cell(D, "e176", "p5")).bounding_box(); z = page.locator(cell(D, "e177", "p7")).bounding_box()
    page.mouse.move(a["x"] + 30, a["y"] + 20); page.mouse.down(); page.mouse.move(z["x"] + 60, z["y"] + 30, steps=8)
    shot(page, "04-drag", [(["td.sel"], 1, "tl")], clip=["#day-grid tbody tr:nth-child(5) th", "#day-grid tbody tr:nth-child(9)"], pad=4)
    page.mouse.up(); page.wait_for_timeout(150)
    page.evaluate("closeOv('book-ov')")

    # 05 場地週表＋每週重複（先放一筆兩週後的衝突）
    page.evaluate("""() => store.update({['bk/2026-10-20/e150/p1']: {title:'教師研習', by:'x@lsps.tp.edu.tw', name:'教學組', status:'ok', at: Date.now()}})""")
    page.evaluate("setView('week')"); page.select_option("#week-place", "e150"); page.wait_for_timeout(150)
    shot(page, "05-week", [("#week-place", 1, "tl"), ("#week-notes", 2, "l"), (cell("2026-10-06", "e150", "p1"), 3, "l")],
         clip=["header", "#week-grid tbody tr:nth-child(5)"], pad=0)
    page.click(cell("2026-10-06", "e150", "p1")); page.wait_for_timeout(100)
    page.fill("#book-title", "資訊社團"); page.check("input[name=rep][value=weekly]"); page.wait_for_timeout(100)
    shot(page, "06-weekly", [("#book-ov .radio label:nth-child(2)", 1, "l"), ("#book-check > div:nth-last-child(2)", 2, "l"),
                             ("#book-check .conf", 3, "l")], clip="#book-ov .modal")
    page.click("#book-ok"); page.wait_for_timeout(200)

    # 07 看別人的預約
    page.evaluate("d => { setView('day'); gotoDay(d); openDetail({date:d, pid:'e155', slot:'p3'}); }", D); page.wait_for_timeout(150)
    shot(page, "07-detail", [("#detail-kv", 1, "l")], clip="#detail-ov .modal")
    page.evaluate("closeOv('detail-ov')")

    # 老師借一個需審核的場地；審核人退回 → 老師收到通知
    page.evaluate("""d => store.create({['bk/'+d+'/e159/aft']: {title:'班親會場布', by:'teacher-a@lsps.tp.edu.tw', name:'王小明老師', unit:'303導師', status:'wait', at: Date.now()}})""", "2026-10-07")
    page.select_option("#demo-user", "approver"); page.wait_for_timeout(150)
    page.evaluate("setView('approve')"); page.wait_for_timeout(150)
    shot(page, "09-approve", [("#nav-approve", 1, "br"), ("#approve-list .card:nth-of-type(1) .tb-btn.ok", 2, "l"),
                              ("#approve-list .card:nth-of-type(1) .tb-btn.danger", 3, "r")],
         clip=["header", "#approve-list .card:nth-of-type(3)"], pad=0)
    card = page.locator("#approve-list .card", has_text="班親會場布").first
    card.locator("button", has_text="退回").click(); page.wait_for_timeout(100)
    page.fill("#ask-text", "當天穿堂有校慶預演，請改借 2樓會議室"); page.click("#ask-ok"); page.wait_for_timeout(200)

    # 08 我的預約（含退回通知）
    page.select_option("#demo-user", "teacher"); page.wait_for_timeout(150)
    page.evaluate("setView('mine')"); page.wait_for_timeout(150)
    shot(page, "08-mine", [("nav button[data-v=mine]", 1, "br"), ("#mine-notices .notice", 2, "l"),
                           ("#mine-list .card:nth-of-type(1) .pill", 3, "r"), ("#mine-list .card:nth-of-type(1) .acts button", 4, "l")],
         clip=["header", "#mine-list .card:nth-of-type(3)"], pad=0)

    # 10 場地管理
    page.select_option("#demo-user", "admin"); page.wait_for_timeout(150)
    page.evaluate("setView('admin')"); page.wait_for_timeout(150)
    shot(page, "10-admin", [("#cfg-semend", 1, "l"), ('#admin-table tr[data-pid="e156"] .a-need', 2, "tl"),
                            ('#admin-table tr[data-pid="e156"] .a-appr', 3, "tl"), ('#admin-table tr[data-pid="e156"] button', 4, "l")],
         clip=["header", '#admin-table tr[data-pid="e175"]'], pad=0)

    # 11 手機
    page.select_option("#demo-user", "teacher")
    page.set_viewport_size({"width": 390, "height": 760}); page.wait_for_timeout(3500)
    page.evaluate("scrolledFor = null; setView('day')"); page.wait_for_timeout(300)
    img = Image.open(io.BytesIO(page.screenshot())).convert("RGB"); img.save(OUT / "11-mobile.png", optimize=True); print("saved 11-mobile")
    b.close()
