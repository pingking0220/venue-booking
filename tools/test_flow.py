"""場地預約示範模式流程測試（Playwright）。用法：python tools/test_flow.py"""
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
URL = (ROOT / "index.html").as_uri() + "?demo"
results = []

def check(name, cond, extra=""):
    results.append(("PASS" if cond else "FAIL", name, str(extra)[:160]))

def bk(page, date, pid, slot):
    return page.evaluate("([d,p,s]) => getBk(d,p,s)", [date, pid, slot])

def cell(page, date, pid, slot):
    return page.locator(f'td.cell[data-date="{date}"][data-pid="{pid}"][data-slot="{slot}"]')

def as_user(page, k):
    page.select_option("#demo-user", k); page.wait_for_timeout(100)

def toast(page):
    return page.text_content("#toast")

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1600, "height": 1000})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("dialog", lambda d: d.accept())
    page.goto(URL); page.wait_for_timeout(500)
    page.evaluate("localStorage.clear()"); page.reload(); page.wait_for_timeout(600)

    # 下一個上課日（明天起、跳過週末），確保不會是「已過去」的節次
    D = page.evaluate("(() => { let d = addDays(todayStr(), 1); while ([0,6].includes(parseYmd(d).getDay())) d = addDays(d, 1); return d; })()")
    page.evaluate("d => gotoDay(d)", D); page.wait_for_timeout(100)

    # 1 點空格借用（免審核場地）
    cell(page, D, "e155", "p4").click(); page.wait_for_timeout(100)
    check("click free cell opens booking", page.is_visible("#book-ov .modal"))
    page.click("#book-ok"); page.wait_for_timeout(100)
    check("title required", "活動名稱" in toast(page), toast(page))
    page.fill("#book-title", "測試活動"); page.fill("#book-unit", "教務處教學組")
    page.click("#book-ok"); page.wait_for_timeout(150)
    r = bk(page, D, "e155", "p4")
    check("booked ok (no approval venue)", r and r["status"] == "ok" and r["by"] == "teacher-a@lsps.tp.edu.tw" and r["unit"] == "教務處教學組", r)
    check("cell shows mine", "mine" in (cell(page, D, "e155", "p4").get_attribute("class") or ""))

    # 2 拖曳一次借三節（需審核場地）
    a = cell(page, D, "e156", "p1").bounding_box(); z = cell(page, D, "e156", "p3").bounding_box()
    page.mouse.move(a["x"] + 20, a["y"] + 20); page.mouse.down(); page.mouse.move(z["x"] + 20, z["y"] + 20, steps=8); page.mouse.up()
    page.wait_for_timeout(150)
    chips_on = page.locator("#book-slots .chip.on").count()
    check("drag selects 3 slots", chips_on == 3, chips_on)
    page.fill("#book-title", "領域會議"); page.click("#book-ok"); page.wait_for_timeout(150)
    st = [ (bk(page, D, "e156", s) or {}).get("status") for s in ("p1", "p2", "p3") ]
    check("needApproval -> wait", st == ["wait", "wait", "wait"], st)
    check("drag booking shares one series", len({(bk(page, D, "e156", s) or {}).get("series") for s in ("p1","p2","p3")}) == 1)
    check("unit remembered", page.evaluate("localStorage.getItem('venue_unit')") == "教務處教學組")

    # 3 對話框裡點節次加借
    cell(page, D, "e159", "p1").click(); page.wait_for_timeout(100)
    page.locator("#book-slots .chip", has_text="第2節").click(); page.wait_for_timeout(50)
    check("chip adds slot", page.locator("#book-slots .chip.on").count() == 2)
    page.fill("#book-title", "電腦研習"); page.click("#book-ok"); page.wait_for_timeout(150)
    check("chip booking saved", bk(page, D, "e159", "p1") is not None and bk(page, D, "e159", "p2") is not None)

    # 4 每週重複＋衝突略過（209 下週二第1節；先塞一筆兩週後的衝突）
    W = page.evaluate("addDays(mondayOf(todayStr()), 8)")          # 下週二
    C = page.evaluate("d => addDays(d, 14)", W)
    page.evaluate("([c]) => store.create({['bk/'+c+'/e150/p1']: {title:'校內研習', by:'x@lsps.tp.edu.tw', name:'某老師', status:'ok', at: Date.now()}})", [C])
    page.click("nav button[data-v=week]"); page.select_option("#week-place", "e150"); page.evaluate("shiftWeek(1)"); page.wait_for_timeout(150)
    cell(page, W, "e150", "p1").click(); page.wait_for_timeout(100)
    page.check("input[name=rep][value=weekly]"); page.wait_for_timeout(100)
    expect = page.evaluate("([w]) => { let n=0, d=w; const end=semesterEnd(); while (d<=end) { if (!getBk(d,'e150','p1')) n++; d=addDays(d,7);} return n; }", [W])
    txt = page.text_content("#book-check")
    check("weekly shows conflict", "已被借走" in txt and "校內研習" in txt, txt)
    check("weekly count excludes conflict", f"共借 {expect} 格" in txt, (expect, txt))
    page.fill("#book-title", "社團資訊課"); page.click("#book-ok"); page.wait_for_timeout(200)
    got = page.evaluate("([w]) => { let n=0; eachBooking((d,p,s,b)=>{ if (b.title==='社團資訊課') n++; }); return n; }", [W])
    check("weekly created all non-conflicting", got == expect, (got, expect))
    check("conflict untouched", (bk(page, C, "e150", "p1") or {}).get("title") == "校內研習")

    # 5 別人的預約：老師只能看，不能取消
    page.evaluate("d => { setView('day'); gotoDay(d); }", C); page.wait_for_timeout(100)
    page.evaluate("d => openDetail({date:d, pid:'e150', slot:'p1'})", C); page.wait_for_timeout(100)
    btns = page.locator("#detail-btns button").all_text_contents()
    check("others' booking read-only for teacher", btns == ["關閉"], btns)
    page.evaluate("closeOv('detail-ov')")

    # 6a 搶位：對話框開著時格子被別人借走 → 對話框立刻更新、確認鈕停用
    page.evaluate("d => gotoDay(d)", D); page.wait_for_timeout(100)
    cell(page, D, "e159", "p5").click(); page.fill("#book-title", "搶位測試")
    page.evaluate("d => store.update({['bk/'+d+'/e159/p5']: {title:'別人先借', by:'y@lsps.tp.edu.tw', status:'wait', at: Date.now()}})", D)
    page.wait_for_timeout(100)
    check("live update shows conflict + disables submit", "別人先借" in page.text_content("#book-check") and page.is_disabled("#book-ok"))
    page.evaluate("closeOv('book-ov')")
    # 6b 送出前一瞬間被借走（畫面還沒更新）→ 整批失敗、不覆蓋
    cell(page, D, "e159", "p6").click(); page.fill("#book-title", "搶位測試2")
    page.evaluate("d => { demoData.bk[d] = demoData.bk[d] || {}; demoData.bk[d].e159 = demoData.bk[d].e159 || {}; demoData.bk[d].e159.p6 = {title:'更早一步', by:'z@lsps.tp.edu.tw', status:'wait', at: 1}; }", D)
    page.click("#book-ok"); page.wait_for_timeout(150)
    check("submit race -> friendly error, nothing overwritten", "剛被別人借走" in toast(page) and page.evaluate("d => demoData.bk[d].e159.p6.title", D) == "更早一步", toast(page))
    page.evaluate("closeOv('book-ov'); demoRefresh()")

    # 7 過去的節次不能借
    Y = page.evaluate("addDays(todayStr(), -1)")
    page.evaluate("d => gotoDay(d)", Y); page.wait_for_timeout(100)
    cls = cell(page, Y, "e157", "p1").get_attribute("class")
    check("past slot not bookable", "past" in cls and "free" not in cls, cls)

    # 8 我的預約：分組
    page.click("nav button[data-v=mine]"); page.wait_for_timeout(100)
    cards = page.locator("#mine-list .card").count()
    check("my bookings grouped", cards == 4, cards)   # 測試活動、領域會議(3格)、電腦研習(2格)、社團資訊課(每週)；國語領域會議是今天已過節次不列

    # 9 審核人：待審核、核准整批、退回整批
    as_user(page, "approver")
    check("approve tab visible for approver", page.is_visible("#nav-approve"))
    badge = page.text_content("#b-approve")
    page.click("#nav-approve"); page.wait_for_timeout(100)
    card = page.locator("#approve-list .card").filter(has=page.locator("h3", has_text=re.compile("^領域會議"))).first
    card.locator("button", has_text="核准").click(); page.wait_for_timeout(150)
    st = [ (bk(page, D, "e156", s) or {}).get("status") for s in ("p1", "p2", "p3") ]
    check("approve group", st == ["ok", "ok", "ok"], st)
    card = page.locator("#approve-list .card", has_text="電腦研習").first
    card.locator("button", has_text="退回").click(); page.wait_for_timeout(100)
    page.fill("#ask-text", "當天有電腦維修"); page.click("#ask-ok"); page.wait_for_timeout(200)
    check("reject removes", bk(page, D, "e159", "p1") is None and bk(page, D, "e159", "p2") is None)
    check("badge decreased", int(page.text_content("#b-approve") or 0) < int(badge or 0), (badge, page.text_content("#b-approve")))

    # 10 審核人取消別人的（免審核場地也可以，因為管理者/審核人）→ 老師只有自己的審核場地可管；這裡用管理者取消
    as_user(page, "admin")
    page.evaluate("d => { setView('day'); gotoDay(d); openDetail({date:d, pid:'e155', slot:'p4'}); }", D); page.wait_for_timeout(100)
    page.locator("#detail-btns button", has_text="取消這一格").click(); page.wait_for_timeout(100)
    page.fill("#ask-text", "校長臨時要用"); page.click("#ask-ok"); page.wait_for_timeout(200)
    check("admin cancels other's booking", bk(page, D, "e155", "p4") is None)

    # 11 老師看到通知
    as_user(page, "teacher")
    check("notice badge", page.text_content("#b-mine") == "2", page.text_content("#b-mine"))
    page.click("nav button[data-v=mine]"); page.wait_for_timeout(100)
    notes = page.locator("#mine-notices .notice").all_text_contents()
    check("reject notice with reason", any("退回" in n and "電腦維修" in n for n in notes), notes)
    check("cancel notice with reason", any("取消" in n and "校長臨時要用" in n for n in notes), notes)
    page.locator("#mine-notices .notice .x").first.click(); page.wait_for_timeout(100)
    check("dismiss notice", page.locator("#mine-notices .notice").count() == 1)

    # 12 取消整批每週
    card = page.locator("#mine-list .card", has_text="社團資訊課").first
    card.locator(".acts button").click(); page.wait_for_timeout(200)
    left = page.evaluate("(() => { let n=0; eachBooking((d,p,s,b)=>{ if (b.title==='社團資訊課') n++; }); return n; })()")
    check("cancel whole weekly series", left == 0, left)

    # 13 管理者：場地管理
    as_user(page, "admin")
    check("admin tab visible", page.is_visible("#nav-admin"))
    page.click("#nav-admin"); page.wait_for_timeout(100)
    row = page.locator('#admin-table tr[data-pid="e159"]')
    row.locator(".a-appr").fill("gmail@gmail.com"); row.locator("button").click(); page.wait_for_timeout(100)
    check("reject non-school approver", "不是學校帳號" in toast(page), toast(page))
    row.locator(".a-appr").fill("teacher-c@lsps.tp.edu.tw, Teacher-D@lsps.tp.edu.tw"); row.locator(".a-need").uncheck(); row.locator("button").click(); page.wait_for_timeout(150)
    pl = page.evaluate("places.e159")
    check("save place", pl["needApproval"] is False and set(pl["approvers"]) == {"teacher-c@lsps,tp,edu,tw", "teacher-d@lsps,tp,edu,tw"}, pl)
    page.fill("#cfg-semend", "2027-01-15"); page.click("text=儲存 >> nth=0"); page.wait_for_timeout(100)
    check("save semester end", page.evaluate("semesterEnd()") == "2027-01-15")
    page.evaluate("addPlace()"); page.wait_for_timeout(100)
    check("add place (inactive by default)", page.evaluate("Object.values(places).some(p => p.name === '新場地' && !p.active)"))

    # 14 一般老師看不到管理與審核
    as_user(page, "teacher")
    check("teacher has no admin/approve tabs", not page.is_visible("#nav-admin") and not page.is_visible("#nav-approve"))

    # 15 手機寬度：沒有水平捲出頁面、格子在容器內捲動
    page.set_viewport_size({"width": 390, "height": 800}); page.evaluate("setView('day')"); page.wait_for_timeout(200)
    check("mobile no page h-scroll", page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
    check("no page errors", not errors, errors)
    b.close()

for r in results:
    print(*r)
print("FAILED" if any(r[0] == "FAIL" for r in results) else "ALL PASSED")
