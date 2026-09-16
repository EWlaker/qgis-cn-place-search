# -*- coding: utf-8 -*-
"""生成拼音表 ``pinyin_table.json``（需要 pypinyin）。

    pip install pypinyin
    python tools/build_pinyin_table.py [语料文件 ...]

语料文件可以是 GeoJSON / JSON / 纯文本，脚本会从中抽取中文字符并统计字频，
**按地名里的出现频率给同音字排序**——这直接决定容错搜索要试几次才能命中。
以「框河镇 → 匡河镇」为例，因为「匡」在地名语料里比「狂/筐」常见得多，
它排在候选第 2 位，两次请求就能命中。

不给语料文件时，退化为「全汉字区按 Unicode 顺序」，能用但命中率会低一些。

生成的表结构::

    {
        "char2py":  {"匡": "kuang", ...},
        "py2chars": {"kuang": ["矿", "匡", "况", ...], ...}
    }
"""

import json
import os
import re
import sys
from collections import Counter

try:
    from pypinyin import Style, lazy_pinyin
except ImportError:
    sys.stderr.write("需要 pypinyin：pip install pypinyin\n")
    sys.exit(1)

HANZI_START, HANZI_END = 0x4E00, 0x9FA6      # 常用汉字区
MAX_CHARS_PER_SYLLABLE = 20                   # 每个音节保留的字数上限

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = os.path.join(ROOT, "pinyin_table.json")

TEXT_KEYS = ("name", "standard_name", "NAME", "Name", "名称", "地名")

# 地名通名 / 方位 / 常见地貌用字：给它们高权重。
#
# 为什么需要：语料如果只来自村委会名，里面全是「村民委员会」这类字，
# 「县」「市」几乎不出现，统计上就会被「先 / 仙」「石 / 十」压过去，
# 于是拼音搜索 kuanghezhen 给出「罗田仙」而不是「罗田县」。
# 给通名加一个远高于自然频率的权重，「县·市·区·镇·乡·村」就能稳居各音节首位。
BUILTIN_TOKENS = (
    "省 市 县 区 镇 乡 村 社区 街道 办事处 居委会 村委会 "
    "自治区 自治县 自治州 盟 旗 苏木 "
    "东 南 西 北 中 新 老 大 小 上 下 前 后 左 右 里 外 "
    "江 河 湖 海 溪 泉 池 潭 湾 港 洲 岛 山 峰 岭 岩 洞 谷 坡 坪 畈 冲 塆 "
    "路 街 巷 道 桥 站 场 园 林 庄 寨 堡 铺 集 墟 "
    "城 关 门 口 头 尾 边 沿 底 顶 家 湾 坊 屯 "
).split()

BUILTIN_WEIGHT = 1000


def collect_names(path):
    """从文件里尽量抽取地名，抽不到就退回「全文当作文本」"""
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except Exception as exc:
        sys.stderr.write("跳过 %s：%s\n" % (path, exc))
        return []

    # GeoJSON / JSON
    try:
        data = json.loads(raw)
        names = []

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in TEXT_KEYS and isinstance(value, str):
                        names.append(value)
                    else:
                        walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(data)
        if names:
            return names
    except Exception:
        pass

    # 纯文本：每行当一个名称
    return [line.strip() for line in raw.splitlines() if line.strip()]


def char_frequency(names):
    counter = Counter()
    for token in BUILTIN_TOKENS:                 # 通名 / 方位 / 地貌：高权重
        for ch in token:
            if HANZI_START <= ord(ch) < HANZI_END:
                counter[ch] += BUILTIN_WEIGHT
    for name in names:                           # 语料：每出现一次记 1
        for ch in name:
            if HANZI_START <= ord(ch) < HANZI_END:
                counter[ch] += 1
    return counter


def gb_tier(ch):
    """汉字常用度分层：1 = GB2312 一级字库，2 = 二级，3 = 其他。

    拿 GB2312 一级字库（16-55 区，3755 个最常用汉字）当"常用"判据，
    比按 Unicode 码点排队靠谱得多——后者会让「儣」(U+513E) 压过
    「匡」(U+5321)，拼音搜索就给出怪字了。
    """
    try:
        raw = ch.encode("gb2312")
    except UnicodeEncodeError:
        return 3
    if len(raw) != 2:
        return 3
    qu = raw[0] - 0xA0
    if 16 <= qu <= 55:
        return 1
    if 56 <= qu <= 87:
        return 2
    return 3


def main():
    paths = sys.argv[1:]
    names = []
    for path in paths:
        got = collect_names(path)
        print("  %-52s %6d 条" % (os.path.basename(path), len(got)))
        names.extend(got)

    counter = char_frequency(names)
    if counter:
        print("语料共 %d 条地名，%d 个不同汉字" % (len(names), len(counter)))
    else:
        print("未提供有效语料，退化为全汉字区（Unicode 顺序）")

    chars = [chr(c) for c in range(HANZI_START, HANZI_END)]
    pinyins = lazy_pinyin("".join(chars), style=Style.NORMAL)

    char2py = {}
    for ch, py in zip(chars, pinyins):
        if py and py.isalpha():
            char2py[ch] = py.lower()
    print("char2py 覆盖 %d 字" % len(char2py))

    # 排序分四层：语料/通名 > GB2312 一级字 > 二级字 > 生僻字
    py2chars = {}
    seen = set()

    def push(ch):
        py = char2py.get(ch)
        if py and ch not in seen:
            py2chars.setdefault(py, []).append(ch)
            seen.add(ch)

    for ch, _ in counter.most_common():          # 0 层：语料 + 通名
        push(ch)
    for tier in (1, 2):                          # 1/2 层：GB2312 常用字
        for ch in chars:
            if ch not in seen and gb_tier(ch) == tier:
                push(ch)
    for ch in chars:                             # 3 层：其余生僻字
        push(ch)

    py2chars = {k: v[:MAX_CHARS_PER_SYLLABLE] for k, v in py2chars.items()}

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump({"char2py": char2py, "py2chars": py2chars},
                  f, ensure_ascii=False, separators=(",", ":"))

    print("写出 %s（%.0f KB，%d 个音节）"
          % (OUTPUT, os.path.getsize(OUTPUT) / 1024.0, len(py2chars)))


if __name__ == "__main__":
    main()
