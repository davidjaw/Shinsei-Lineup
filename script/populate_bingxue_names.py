"""One-off: populate CHT `name` + `cht_direction` fields in data/bingxue.yaml
for every option, from a hand-maintained JP→CHT mapping.

The mapping is authoritative — it comes from the user who plays the game and
knows the CHT localization (including the 臨戦↔機略 direction swap).

Usage:
    uv run script/populate_bingxue_names.py
"""
import sys

import yaml

from paths import BINGXUE_CANONICAL, BINGXUE_JP_TO_CHT_DIR

# JP option name → CHT name
# Majors: hand-confirmed by user.
# Minors: direct ideograph substitution (気→氣, 胆→膽, 靭→韌, etc.)
NAME_MAP = {
    # ----- MAJOR -----
    # JP 武略 → CHT 武略 (red)
    "兵勢連鎖": "兵勢連鎖",
    "舟中敵国": "舟中敵國",
    "当意即妙": "剛柔相濟",
    "冷静沈着": "冷靜沉著",
    "表裏一体": "虛實自在",
    "智勇兼備": "智勇兼備",
    # JP 陣立 → CHT 陣立 (brown/orange)
    "生々流転": "生生不息",
    "気勢崩し": "氣勢崩摧",
    "陽動の策": "佯動之策",
    "返り討ちの計": "反討之計",
    "勇猛果敢": "勇猛果敢",
    "先陣誘導": "先陣誘敵",
    "右往左往": "挫其銳氣",
    # JP 臨戦 → CHT 機略 (purple) — direction swap
    "破陣の勢い": "破陣之勢",
    "離間の計": "離間之計",
    "軍律擾乱": "軍律擾亂",
    "詭計百出": "詭計百出",
    "臨機応変": "臨機應變",
    "七転八起": "七轉八起",
    # JP 機略 → CHT 臨戰 (green) — direction swap
    "搦手の策": "搦手之策",
    "達人大観": "達人大觀",
    "手当の心得": "救援心得",
    "心頭滅却": "心頭滅卻",
    "鼓舞激励": "鼓舞奮迅",
    "脱兎の如し": "動如脫兔",
    "殿軍救護": "殿軍援護",

    # ----- MINOR ----- (direct ideograph substitution)
    # JP 武略 / CHT 武略
    "胆力": "膽力",
    "活路": "活路",
    "突貫": "突貫",
    "妙策": "妙策",
    "豪勇": "豪勇",
    "剛力": "剛力",
    "奇謀": "奇謀",
    "警戒": "警戒",
    # JP 陣立 / CHT 陣立
    "慧眼": "慧眼",
    "兵心": "兵心",
    "不敵": "不敵",
    "逆境": "逆境",
    "才気": "才氣",
    "俊才": "俊才",
    "乱戦": "亂戰",
    "恩顧": "恩顧",
    # JP 臨戦 / CHT 機略
    "強靭": "強韌",
    "神秘": "神秘",
    "早駆": "早驅",
    "大勇": "大勇",
    "鬼気": "鬼氣",
    "神算": "神算",
    "多謀": "多謀",
    "練磨": "練磨",
    # JP 機略 / CHT 臨戰
    "不惑": "不惑",
    "明鏡": "明鏡",
    "天時": "天時",
    "機動": "機動",
    "地利": "地利",
    "協同": "協同",
    "仁愛": "仁愛",
    "果敢": "果敢",
    "兵家": "兵家",
    "内助": "內助",
}


def main():
    path = BINGXUE_CANONICAL
    data = yaml.safe_load(path.read_text("utf-8"))

    jp_in_data = set(data.keys())
    jp_in_map = set(NAME_MAP.keys())
    missing = jp_in_data - jp_in_map
    extra = jp_in_map - jp_in_data
    if missing:
        print(f"WARN: {len(missing)} JP options in yaml but NOT in mapping: {sorted(missing)}")
    if extra:
        print(f"WARN: {len(extra)} mapping entries have no matching JP option: {sorted(extra)}")

    updated = 0
    for jp_name, entry in data.items():
        raw = entry.get("raw", {})
        jp_dir = raw.get("direction")
        if jp_name in NAME_MAP:
            entry["name"] = NAME_MAP[jp_name]
            entry["cht_direction"] = BINGXUE_JP_TO_CHT_DIR.get(jp_dir, jp_dir)
            updated += 1

    path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    print(f"Updated {updated}/{len(data)} entries in {path}")


if __name__ == "__main__":
    sys.exit(main() or 0)
