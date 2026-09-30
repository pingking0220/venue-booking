"""產生場地預約的安全規則，合併進 award-seating/database.rules.json 的 "venue" 節點。
兩個系統共用同一個 Firebase Realtime Database，規則只能有一份，所以一律在 award-seating 那邊部署：
  cd award-seating && firebase deploy --only database --project award-seat
用法：python tools/build_rules.py [rules 檔路徑]"""
import json, sys
from pathlib import Path

RULES = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "award-seating" / "database.rules.json"

SCHOOL = "auth != null && auth.token.email != null && auth.token.email_verified == true && auth.token.email.endsWith('@lsps.tp.edu.tw')"
EMAIL = "auth.token.email.toLowerCase()"
EK = "auth.token.email.toLowerCase().replace('.', ',')"
ADMIN = f"root.child('roles').child({EK}).val() == 'admin'"
PLACE = "root.child('venue').child('places').child($pid)"
APPROVER = f"{PLACE}.child('approvers').child({EK}).val() == true"
NEED = f"{PLACE}.child('needApproval').val() == true"
ACTIVE = f"{PLACE}.child('active').val() == true"

def s(maxlen):
    return {".validate": f"newData.isString() && newData.val().length <= {maxlen}"}

slot_write = (
    f"{SCHOOL} && ("
    f"{ADMIN}"
    # 新借用：格子原本是空的、申請人是自己、場地開放借用；需審核的場地只能送 wait，免審核的直接 ok
    f" || (!data.exists() && newData.exists() && newData.child('by').val() == {EMAIL} && {ACTIVE}"
    f" && (({NEED} && newData.child('status').val() == 'wait') || (!({NEED}) && newData.child('status').val() == 'ok')))"
    # 取消／退回：本人或該場地審核人
    f" || (data.exists() && !newData.exists() && (data.child('by').val() == {EMAIL} || {APPROVER}))"
    # 審核：審核人只能改狀態，不能改申請人與活動名稱
    f" || (data.exists() && newData.exists() && {APPROVER} && newData.child('by').val() == data.child('by').val() && newData.child('title').val() == data.child('title').val())"
    ")"
)

venue = {
    "places": {
        ".read": SCHOOL,
        ".write": f"{SCHOOL} && {ADMIN}",
        "$pid": {".validate": "newData.hasChildren(['name']) && newData.child('name').isString() && newData.child('name').val().length <= 30"},
    },
    "config": {".read": SCHOOL, ".write": f"{SCHOOL} && {ADMIN}"},
    "bk": {
        ".read": SCHOOL,
        "$date": {"$pid": {"$slot": {
            ".write": slot_write,
            ".validate": "newData.hasChildren(['title', 'by', 'status', 'at']) && $date.matches(/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/) && $slot.matches(/^(m|p[1-7]|nap|aft|eve)$/)",
            "title": {".validate": "newData.isString() && newData.val().length >= 1 && newData.val().length <= 60"},
            "by": s(80), "name": s(40), "unit": s(30), "series": s(40), "time": s(20), "note": s(200), "src": s(20),
            "status": {".validate": "newData.val() == 'ok' || newData.val() == 'wait'"},
            "at": {".validate": "newData.isNumber()"},
            "$other": {".validate": False},
        }}},
    },
    "notice": {"$ek": {
        ".read": f"{SCHOOL} && $ek == {EK}",
        "$nid": {
            # 任何校內帳號都能發通知（退回／取消時通知申請人）；只有本人能刪除自己的通知
            ".write": f"{SCHOOL} && ((!data.exists() && newData.exists()) || ($ek == {EK} && !newData.exists()))",
            ".validate": "newData.hasChildren(['text', 'at'])",
            "text": s(300),
            "at": {".validate": "newData.isNumber()"},
            "$other": {".validate": False},
        },
    }},
}

rules = json.loads(RULES.read_text(encoding="utf-8"))
rules["rules"]["venue"] = venue
RULES.write_text(json.dumps(rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("updated", RULES)
