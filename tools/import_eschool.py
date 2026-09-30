"""把校務行政系統（eschool）已通過的場地預約匯入新系統。

資料來源是校務系統的公開查詢 API（不需登入，只含「已通過」的預約，申請人姓名會被遮罩成「楊Ｏ祥」）。
時間對應到新系統的節次：與哪幾節有重疊就佔哪幾節，原始時間另存在 time 欄位。
同場地、同活動名稱、同星期、同節次出現兩次以上 → 視為同一批（series），可以整批取消。

用法：
  python tools/import_eschool.py 2026-10-01 2027-01-31            # 試跑：只產生 import-preview.json 與摘要
  python tools/import_eschool.py 2026-10-01 2027-01-31 --write    # 寫入 Firebase（跳過新系統已有預約的格子）
寫入用 firebase CLI（需已登入 it@lsps.tp.edu.tw），安全規則不適用於 CLI，所以這裡自己檢查不覆蓋。"""
import hashlib, json, re, subprocess, sys, time, urllib.parse, urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = "award-seat"
API = "https://eschool.tp.edu.tw/c0203spublicdata.action"
SCH_NO = "383615"
SLOTS = [("m", "08:00", "08:40"), ("p1", "08:40", "09:20"), ("p2", "09:30", "10:10"), ("p3", "10:30", "11:10"),
         ("p4", "11:20", "12:00"), ("nap", "12:40", "13:20"), ("p5", "13:25", "14:05"), ("p6", "14:15", "14:55"),
         ("p7", "15:15", "15:55"), ("aft", "16:00", "18:00"), ("eve", "18:00", "21:00")]


def roc(d):  # 2026-10-01 → 115/10/01
    return f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"


def mins(hm):
    h, m = [int(x) for x in re.sub(r"\s", "", hm).split(":")]
    return h * 60 + m


def fetch(start, end):
    """一次抓一個月，避免單次回應太大"""
    out, cur = [], start
    while cur <= end:
        stop = min(end, (cur.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1))
        body = urllib.parse.urlencode({"schNo": SCH_NO, "id": "", "begin": roc(cur), "end": roc(stop), "word": ""}).encode()
        req = urllib.request.Request(API, data=body, headers={"User-Agent": "Mozilla/5.0"})
        data = json.load(urllib.request.urlopen(req, timeout=30))["data"]["data"]
        for day in data:
            for a in day["apply"]:
                out.append(dict(a, dt=day["dt"]))
        cur = stop + timedelta(days=1)
        time.sleep(0.5)
    return out


def norm(name):
    return re.sub(r"\s+", "", name or "")


def slots_for(beg, end):
    b, e = mins(beg), mins(end)
    if e <= b:            # 校務系統有人把 13:30 打成 01:30
        e += 12 * 60
    return [k for k, s, t in SLOTS if b < mins(t) and e > mins(s)], f"{b // 60:02d}:{b % 60:02d}-{e // 60:02d}:{e % 60:02d}"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    write = "--write" in sys.argv
    start = datetime.strptime(args[0], "%Y-%m-%d").date() if args else date.today()
    end = datetime.strptime(args[1], "%Y-%m-%d").date() if len(args) > 1 else start + timedelta(days=150)
    places = json.loads((ROOT / "seed-places.json").read_text(encoding="utf-8"))
    by_name = {norm(p["name"]): pid for pid, p in places.items()}

    rows = fetch(start, end)
    recs, skipped, clash = {}, [], []
    for a in rows:
        pid = by_name.get(norm(a["name"]))
        if not pid:
            skipped.append(f"{a['dt']} {a['name']}（新系統沒有這個場地）")
            continue
        ks, span = slots_for(a["beg"], a["end"])
        if not ks:
            skipped.append(f"{a['dt']} {a['name']} {span} {a['title']}（不在任何節次內）")
            continue
        d = f"{a['dt'][:4]}-{a['dt'][4:6]}-{a['dt'][6:]}"
        exact = any(span == f"{s}-{t}" for k, s, t in SLOTS)
        for k in ks:
            key = f"{d}/{pid}/{k}"
            if key in recs:
                clash.append(f"{key} {a['title']} 與 {recs[key]['title']} 重疊，保留先出現的「{recs[key]['title']}」")
                continue
            r = {"title": a["title"][:60], "by": "eschool", "name": (a["app"] or "")[:40], "unit": "", "status": "ok",
                 "at": int(time.time() * 1000), "src": "eschool"}
            if not exact:
                r["time"] = span
            recs[key] = r

    # 同場地＋同活動＋同星期＋同節次出現兩次以上 → 同一批
    groups = {}
    for key, r in recs.items():
        d, pid, k = key.split("/")
        g = (pid, r["title"], date.fromisoformat(d).weekday(), k)
        groups.setdefault(g, []).append(key)
    for g, keys in groups.items():
        if len(keys) > 1:
            sid = "es" + hashlib.md5(repr(g).encode()).hexdigest()[:10]
            for key in keys:
                recs[key]["series"] = sid

    per_place = {}
    for key in recs:
        n = places[key.split("/")[1]]["name"]
        per_place[n] = per_place.get(n, 0) + 1
    print(f"校務系統 {start}～{end}：{len(rows)} 筆預約 → 新系統 {len(recs)} 格")
    print("各場地：", per_place)
    print(f"成批（每週重複）：{sum(1 for k in groups.values() if len(k) > 1)} 批")
    for s in skipped:
        print("略過：", s)
    for c in clash:
        print("重疊：", c)
    preview = ROOT / "tools" / "import-preview.json"
    preview.write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
    print("預覽檔：", preview)

    if not write:
        print("（試跑，未寫入。確認無誤後加 --write）")
        return
    existing = json.loads(subprocess.run(["firebase", "database:get", "/venue/bk", "--project", PROJECT],
                                         capture_output=True, text=True, encoding="utf-8", shell=True, check=True).stdout or "null") or {}
    todo = {k: v for k, v in recs.items() if not (existing.get(k.split("/")[0], {}).get(k.split("/")[1], {}).get(k.split("/")[2]))}
    print(f"新系統已有 {len(recs) - len(todo)} 格被借用，跳過；實際寫入 {len(todo)} 格")
    if not todo:
        return
    f = ROOT / "tools" / "import-write.json"
    f.write_text(json.dumps(todo, ensure_ascii=False), encoding="utf-8")
    subprocess.run(["firebase", "database:update", "/venue/bk", str(f), "--project", PROJECT, "--force"], shell=True, check=True)
    print("匯入完成")


if __name__ == "__main__":
    main()
