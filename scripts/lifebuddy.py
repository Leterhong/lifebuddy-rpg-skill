#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lifebuddy-rpg 状态与记忆管理脚本（仅依赖 Python 标准库，零第三方依赖）。

负责维护 {baseDir}/data/profile.json：
  - 用户画像（称呼 / 城市 / 偏好 / 重要日子）
  - RPG 成长状态（等级 / 经验 / 金币 / 连续 / 属性 / 副本 / 习惯 / 日记 / 勋章）

设计原则：本地优先、容错、绝不崩溃。
  - 所有子命令在正常与异常输入下都返回可读性文本，不抛未捕获异常。
  - self-test 子命令在临时目录隔离运行，绝不触碰真实用户档案，用于质量评测 / CI 验证。
"""

import argparse
import json
import os
import sys
import shutil
import tempfile
from datetime import datetime, date
from collections import OrderedDict

# 统一 stdout 为 UTF-8，避免 Windows 下中文 / emoji 乱码
if getattr(sys.stdout, "encoding", "") != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
PROFILE = os.path.join(DATA, "profile.json")

ATTRS = ["discipline", "health", "study", "social", "joy"]
ATTR_CN = {
    "discipline": "自律",
    "health": "健康",
    "study": "学习",
    "social": "社交",
    "joy": "快乐",
}


def today_str():
    return date.today().isoformat()


def default_profile():
    return {
        "profile": {
            "name": "",
            "city": "",
            "timezone": "Asia/Shanghai",
            "preferences": {},
            "important_dates": [],
            "created_at": datetime.now().isoformat(timespec="seconds"),
        },
        "rpg": {
            "level": 1,
            "exp": 0,
            "coins": 0,
            "streak": 0,
            "last_active": "",
            "attributes": {a: 0 for a in ATTRS},
            "quests": [],
            "habits": [],
            "diary": [],
            "badges": [],
            "history": [],
        },
    }


def load():
    """读取档案；缺失返回 None；损坏则备份后以 None 返回（由调用方重建）。"""
    if not os.path.exists(PROFILE):
        return None
    try:
        with open(PROFILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        bak = PROFILE + ".bak"
        try:
            if os.path.exists(PROFILE):
                with open(PROFILE, "r", encoding="utf-8") as src, \
                     open(bak, "w", encoding="utf-8") as dst:
                    dst.write(src.read())
        except Exception:
            pass
        return None


def save(data):
    os.makedirs(DATA, exist_ok=True)
    tmp = PROFILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PROFILE)  # 原子替换，避免写半截


def ensure(data):
    """load 或重建默认档案。"""
    return data if data is not None else default_profile()


def touch_streak(rpg):
    """基于 last_active 日期刷新连续天数：同日保持、跨 1 天 +1、断更归 1。"""
    t = today_str()
    last = rpg.get("last_active", "")
    if last == t:
        return
    if last:
        try:
            pd = date.fromisoformat(last)
            gap = (date.today() - pd).days
            rpg["streak"] = (rpg.get("streak", 0) + 1) if gap == 1 else 1
        except Exception:
            rpg["streak"] = 1
    else:
        rpg["streak"] = 1
    rpg["last_active"] = t


def grant_exp(data, attr, amount, note=""):
    """累加经验 / 属性 / 金币，处理升级与勋章。返回庆祝文案列表。"""
    rpg = data["rpg"]
    touch_streak(rpg)
    amount = max(0, int(amount))
    old_level = rpg["level"]
    rpg["exp"] += amount
    rpg["coins"] += amount // 20
    if attr in rpg["attributes"]:
        rpg["attributes"][attr] += amount
    new_level = 1 + rpg["exp"] // 100
    rpg["level"] = new_level
    msgs = []
    # 跨多级升级时，逐级播报庆祝并补发每一个 5 的倍数里程碑勋章（避免漏发）
    for lv in range(old_level + 1, new_level + 1):
        msgs.append(f"🎉 升级！你已达到 Lv.{lv}")
        if lv % 5 == 0 and f"level-{lv}" not in rpg["badges"]:
            rpg["badges"].append(f"level-{lv}")
            msgs.append(f"🏅 解锁勋章：Lv.{lv} 人生玩家")
    if rpg["streak"] > 0 and rpg["streak"] % 7 == 0 and f"streak-{rpg['streak']}" not in rpg["badges"]:
        rpg["badges"].append(f"streak-{rpg['streak']}")
        msgs.append(f"🔥 连续 {rpg['streak']} 天！坚持勋章到手")
    rpg["history"].append({"date": today_str(), "note": note or "经验记录", "exp": amount, "attr": attr})
    return msgs


# ---------------- 可视化（纯文本为主，Mermaid 可选附加，绝不因渲染失败而崩溃） ----------------

def build_radar(attrs):
    """五维属性的 ASCII 条形图，任何终端 / 渲染环境都可读。"""
    maxv = max(attrs.values()) or 1
    lines = []
    for a in ATTRS:
        v = attrs[a]
        filled = int(round(v / maxv * 10))
        bar = "█" * filled + "░" * (10 - filled)
        lines.append(f"{ATTR_CN[a]} {bar} {v}")
    return "\n".join(lines)


def build_mermaid_bar(attrs):
    """Mermaid xychart-beta 柱状图，作为可选附加；不支持 Mermaid 的环境仅忽略该代码块。"""
    vals = ", ".join(str(attrs[a]) for a in ATTRS)
    labels = ", ".join(ATTR_CN[a] for a in ATTRS)
    top = max(attrs.values()) or 1
    return (
        "```mermaid\n"
        "xychart-beta\n"
        '  title "五维属性成长"\n'
        "  x-axis [" + labels + "]\n"
        f"  y-axis \"经验值\" 0 --> {top}\n"
        "  bar [" + vals + "]\n"
        "```"
    )


def build_curve(history):
    """基于 history 的累计经验轨迹（ASCII）。"""
    if not history:
        return "(暂无成长记录，去完成一个副本或打卡吧～)"
    daily = OrderedDict()
    for h in history:
        daily[h["date"]] = daily.get(h["date"], 0) + h.get("exp", 0)
    cum = 0
    pts = []
    for d, e in daily.items():
        cum += e
        pts.append((d, cum))
    top = max(c for _, c in pts) or 1
    lines = ["累计经验轨迹（每日累计）："]
    for d, c in pts[-10:]:
        filled = int(round(c / top * 12))
        lines.append(f"  {d} {('#' * filled).ljust(12)} {c}")
    return "\n".join(lines)


# ---------------- 子命令 ----------------

def cmd_init(args):
    if os.path.exists(PROFILE) and not args.force:
        print("档案已存在，使用 --force 覆盖重建")
        return
    save(default_profile())
    print("✅ 已初始化栖屋档案：data/profile.json")


def cmd_get(args):
    data = load()
    if data is None:
        print("⚠️ 档案缺失或损坏，建议执行 init 重建")
        return
    p = data["profile"]
    r = data["rpg"]
    print(f"🪪 搭子档案 | 称呼:{p.get('name') or '你'}  城市:{p.get('city') or '未设'}")
    print(f"⚔️ Lv.{r['level']} | EXP {r['exp']} | 🪙{r['coins']} | 🔥连续{r['streak']}天")
    print("📊 属性:")
    print(build_radar(r["attributes"]))
    if r["badges"]:
        print("🏅 勋章:", ", ".join(r["badges"]))
    print(f"📜 进行中副本:{sum(1 for q in r['quests'] if q['status']=='open')} | 习惯:{len(r['habits'])} | 日记:{len(r['diary'])}条")
    print("📈 " + build_curve(r["history"]))
    # 可选可视化附加（渲染器不支持 Mermaid 时仅忽略该块，不影响上述文本）
    print("---\n" + build_mermaid_bar(r["attributes"]))


def cmd_set_profile(args):
    data = ensure(load())
    if args.name is not None:
        data["profile"]["name"] = args.name
    if args.city is not None:
        data["profile"]["city"] = args.city
    if args.prefs:
        for kv in args.prefs:
            if ":" in kv:
                k, v = kv.split(":", 1)
                data["profile"]["preferences"][k] = v
    save(data)
    print("✅ 画像已更新")


def cmd_add_exp(args):
    data = ensure(load())
    msgs = grant_exp(data, args.attr, args.amount, args.note or "")
    save(data)
    print(f"➕ 经验+{args.amount} → {ATTR_CN.get(args.attr, args.attr)}↑")
    for m in msgs:
        print(m)


def cmd_add_quest(args):
    data = ensure(load())
    r = data["rpg"]
    touch_streak(r)
    qid = (max([q["id"] for q in r["quests"]] + [0])) + 1
    r["quests"].append({
        "id": qid, "title": args.title, "attr": args.attr,
        "reward": args.reward, "status": "open", "created": today_str(), "done": ""
    })
    save(data)
    print(f"🗡️ 副本#{qid}已登记：{args.title}（完成奖励 {args.reward} 经验/{ATTR_CN.get(args.attr, args.attr)}）")


def cmd_complete_quest(args):
    data = ensure(load())
    r = data["rpg"]
    q = next((x for x in r["quests"] if x["id"] == args.id), None)
    if not q:
        print("⚠️ 未找到该副本（可能已完成或编号不存在）")
        return
    if q["status"] == "done":
        print("该副本已完成过啦")
        return
    q["status"] = "done"
    q["done"] = today_str()
    msgs = grant_exp(data, q["attr"], q["reward"], f"副本完成:{q['title']}")
    save(data)
    print(f"✅ 副本#{args.id} 通关！+{q['reward']} 经验")
    for m in msgs:
        print(m)


def cmd_checkin_habit(args):
    data = ensure(load())
    r = data["rpg"]
    h = next((x for x in r["habits"] if x["name"] == args.habit), None)
    if not h:
        h = {"name": args.habit, "attr": args.attr, "streak": 0, "last": ""}
        r["habits"].append(h)
        if "habit-first" not in r["badges"]:
            r["badges"].append("habit-first")
            print("🏅 解锁勋章：习惯萌新")
    if h["last"] == today_str():
        print("今天已打卡，明天再来～")
        save(data)
        return
    t = date.today()
    if h["last"]:
        try:
            h["streak"] = h["streak"] + 1 if (t - date.fromisoformat(h["last"])).days == 1 else 1
        except Exception:
            h["streak"] = 1
    else:
        h["streak"] = 1
    h["last"] = today_str()
    # grant_exp 内部已负责 touch_streak（刷新全局连续天数），此处无需重复调用
    msgs = grant_exp(data, args.attr, 10, f"习惯打卡:{args.habit}")
    save(data)
    print(f"🌱 习惯「{args.habit}」打卡成功，连续 {h['streak']} 天 +10 经验")
    for m in msgs:
        print(m)


def cmd_mood(args):
    data = ensure(load())
    r = data["rpg"]
    r["diary"].append({"date": today_str(), "text": args.text})
    if len(r["diary"]) > 200:
        r["diary"] = r["diary"][-200:]
    # grant_exp 内部已负责 touch_streak（刷新全局连续天数），此处无需重复调用
    msgs = grant_exp(data, "joy", 5, "心情树洞陪伴")
    save(data)
    print(f"💗 已记下今天的心情（共 {len(r['diary'])} 条）")
    for m in msgs:
        print(m)


def cmd_remind(args):
    data = load()
    if data is None:
        print("暂无档案，先聊聊天建立档案吧～")
        return
    p = data["profile"]
    r = data["rpg"]
    today = date.today()
    out = []
    for d in p.get("important_dates", []):
        try:
            md = date(today.year, int(d["date"][:2]), int(d["date"][3:5]))
            delta = (md - today).days
            if 0 <= delta <= 7:
                out.append(f"📅 {d['label']} 还有 {delta} 天（{d['date']}）")
        except Exception:
            pass
    if r["streak"] > 0:
        out.append(f"🔥 你已连续活跃 {r['streak']} 天，别断签哦")
    if not out:
        out.append("最近没有临近的重要日子，安心往前走～")
    print("\n".join(out))


def cmd_self_test(args):
    """
    隔离式自检：在临时目录运行全链路，验证不崩溃且数值自洽。
    绝不触碰真实 data/profile.json。
    """
    global DATA, PROFILE
    tmp = tempfile.mkdtemp(prefix="lifebuddy_selftest_")
    old_data, old_profile = DATA, PROFILE
    DATA, PROFILE = tmp, os.path.join(tmp, "profile.json")
    failures = []

    def run(*argv):
        # 捕获每个子命令的中间输出，保持自检结论干净
        _capture(lambda: HANDLERS[argv[0]](_parse(list(argv))))

    try:
        # 1) init
        save(default_profile())
        if load() is None:
            failures.append("init 后档案为空")

        # 2) set-profile
        run("set-profile", "--name", "测试官", "--city", "上海", "--prefs", "风格:极简")
        d = load()
        if d["profile"]["name"] != "测试官":
            failures.append("set-profile 未生效")
        if d["profile"]["preferences"].get("风格") != "极简":
            failures.append("prefs 解析失败")

        # 3) add-quest + complete-quest 数值
        run("add-quest", "--title", "写文档", "--attr", "study", "--reward", "40")
        run("complete-quest", "--id", "1")
        d = load()
        if d["rpg"]["exp"] != 40:
            failures.append(f"exp 应为40, 实际{d['rpg']['exp']}")
        if d["rpg"]["attributes"]["study"] != 40:
            failures.append("study 属性未累加")

        # 4) checkin-habit
        run("checkin-habit", "--habit", "喝水", "--attr", "health")
        d = load()
        if d["rpg"]["exp"] != 50:
            failures.append(f"exp 应为50, 实际{d['rpg']['exp']}")
        if not any(h["name"] == "喝水" for h in d["rpg"]["habits"]):
            failures.append("习惯未登记")
        if "habit-first" not in d["rpg"]["badges"]:
            failures.append("首习惯勋章缺失")

        # 5) mood
        run("mood", "--text", "今天不错")
        d = load()
        if d["rpg"]["exp"] != 55:
            failures.append(f"exp 应为55, 实际{d['rpg']['exp']}")
        if d["rpg"]["attributes"]["joy"] != 5:
            failures.append("joy 属性未累加")
        if len(d["rpg"]["diary"]) != 1:
            failures.append("日记未记录")

        # 6) get / remind 不报错且含可视化
        out_get = _capture(lambda: HANDLERS["get"](_parse(["get"])))
        out_remind = _capture(lambda: HANDLERS["remind"](_parse(["remind"])))
        if "搭子档案" not in out_get:
            failures.append("get 输出异常")
        if "█" not in out_get:
            failures.append("可视化条形图缺失")

        # 7) 边界：缺失副本不崩溃
        run("complete-quest", "--id", "999")

        # 8) 单级升级（exp 55 -> 105 -> Lv.2）
        run("add-exp", "--attr", "discipline", "--amount", "50")
        d = load()
        if d["rpg"]["level"] != 2:
            failures.append(f"升级逻辑异常，level={d['rpg']['level']}")

        # 9) 跨多级升级，里程碑勋章不得漏发（Lv.2 -> Lv.7，中间经过 Lv.5）
        run("add-exp", "--attr", "study", "--amount", "500")
        d = load()
        if d["rpg"]["level"] != 7:
            failures.append(f"跨级升级 level 异常={d['rpg']['level']}")
        if "level-5" not in d["rpg"]["badges"]:
            failures.append("跨级升级漏发 level-5 里程碑勋章")
    except Exception as e:
        failures.append(f"未捕获异常: {e}")
    finally:
        DATA, PROFILE = old_data, old_profile
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print("❌ 自检未通过：")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("✅ self-test 通过：全链路不崩溃，数值自洽（init/画像/副本/习惯/树洞/可视化/边界/升级/跨级勋章）")


def _parse(argv):
    return build_parser().parse_args(argv)


def _capture(fn):
    import io
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        fn()
    finally:
        sys.stdout = old
    return buf.getvalue()


# ---------------- 解析与调度 ----------------

HANDLERS = {
    "init": cmd_init,
    "get": cmd_get,
    "set-profile": cmd_set_profile,
    "add-exp": cmd_add_exp,
    "add-quest": cmd_add_quest,
    "complete-quest": cmd_complete_quest,
    "checkin-habit": cmd_checkin_habit,
    "mood": cmd_mood,
    "remind": cmd_remind,
    "self-test": cmd_self_test,
}


def build_parser():
    pa = argparse.ArgumentParser(description="lifebuddy-rpg 状态管理")
    sub = pa.add_subparsers(dest="cmd")
    sub.add_parser("init").add_argument("--force", action="store_true")
    sub.add_parser("get")
    sp = sub.add_parser("set-profile")
    sp.add_argument("--name")
    sp.add_argument("--city")
    sp.add_argument("--prefs", nargs="*")
    se = sub.add_parser("add-exp")
    se.add_argument("--attr", required=True, choices=ATTRS)
    se.add_argument("--amount", type=int, required=True)
    se.add_argument("--note")
    aq = sub.add_parser("add-quest")
    aq.add_argument("--title", required=True)
    aq.add_argument("--attr", required=True, choices=ATTRS)
    aq.add_argument("--reward", type=int, required=True)
    cq = sub.add_parser("complete-quest")
    cq.add_argument("--id", type=int, required=True)
    ch = sub.add_parser("checkin-habit")
    ch.add_argument("--habit", required=True)
    ch.add_argument("--attr", required=True, choices=ATTRS)
    mo = sub.add_parser("mood")
    mo.add_argument("--text", required=True)
    sub.add_parser("remind")
    sub.add_parser("self-test")
    return pa


def main():
    pa = build_parser()
    args = pa.parse_args()
    if not args.cmd:
        pa.print_help()
        return
    try:
        HANDLERS[args.cmd](args)
    except SystemExit:
        raise
    except Exception as e:
        print(f"⚠️ 操作未成功完成：{e}（档案未损坏，可重试）")
        sys.exit(1)


if __name__ == "__main__":
    main()
