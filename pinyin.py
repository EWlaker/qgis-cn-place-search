# -*- coding: utf-8 -*-
"""拼音工具：拼音表加载、同音字候选、拼音串切分。

拼音表 ``pinyin_table.json`` 由 ``tools/build_pinyin_table.py`` 生成，结构::

    {
        "char2py":  {"匡": "kuang", "河": "he", ...},
        "py2chars": {"kuang": ["矿", "匡", "况", ...], ...}   # 按地名用字频率排序
    }

``py2chars`` 里每个音节的字是按「地名语料中的出现频率」降序排的，所以
生成候选时优先取前面的字，命中率明显高于按 Unicode 顺序排。
"""

import itertools
import json
import os

TABLE_NAME = "pinyin_table.json"

_table = None


def table_path():
    """拼音表路径（与本模块同目录）"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), TABLE_NAME)


def load_table():
    """加载拼音表，首次调用读盘，之后缓存。失败返回空表而不是抛异常。"""
    global _table
    if _table is None:
        try:
            with open(table_path(), encoding="utf-8") as f:
                _table = json.load(f)
        except Exception:
            _table = {"char2py": {}, "py2chars": {}}
    return _table


def available():
    """拼音表是否可用"""
    return bool(load_table().get("char2py"))


def char_pinyin(ch):
    """单字拼音，查不到返回 None"""
    return (load_table().get("char2py") or {}).get(ch)


def homophone_candidates(keyword, limit=6):
    """同音字替换候选：一次只换一个字。

    >>> homophone_candidates('罗田具', 6)
    ['落田具', '罗田县', '螺田具', ...]

    这里是**逐位轮转**，而不是「先把第一个字的所有同音字试完」。用户的
    错字可能出现在任何位置；如果是顺序取，词尾的错字（「罗田具」的「具」
    应为「县」）会被词首的候选挤掉，永远轮不到。
    """
    t = load_table()
    c2p = t.get("char2py") or {}
    p2c = t.get("py2chars") or {}

    per_position = []
    for i, ch in enumerate(keyword):
        pinyin = c2p.get(ch)
        if not pinyin:
            per_position.append((i, []))
            continue
        alts = [a for a in (p2c.get(pinyin) or []) if a != ch]
        per_position.append((i, alts))

    out = []
    seen = {keyword}
    round_index = 0
    while len(out) < limit:
        progressed = False
        for i, alts in per_position:
            if round_index >= len(alts):
                continue
            progressed = True
            cand = keyword[:i] + alts[round_index] + keyword[i + 1:]
            if cand not in seen:
                seen.add(cand)
                out.append(cand)
                if len(out) >= limit:
                    return out
        if not progressed:
            break
        round_index += 1
    return out


def split_pinyin(text):
    """把连写的拼音切成音节（最长匹配）。切不开返回 None。

    >>> split_pinyin('kuanghezhen')
    ['kuang', 'he', 'zhen']
    """
    sylls = (load_table().get("py2chars") or {})
    if not sylls:
        return None
    maxlen = max(len(x) for x in sylls)
    out = []
    i = 0
    n = len(text)
    while i < n:
        for length in range(min(maxlen, n - i), 0, -1):
            piece = text[i:i + length]
            if piece in sylls:
                out.append(piece)
                i += length
                break
        else:
            return None
    return out


def pinyin_candidates(pinyin, per_syllable=3, limit=6):
    """拼音串 -> 汉字组合候选，按「各字在自己音节里的常见度排名之和」升序。

    >>> pinyin_candidates('kuanghezhen', 3, 3)
    ['矿河镇', '匡河镇', '矿合镇']

    排序方式很关键。笛卡尔积的天然顺序是「第一个音节变得最慢」，那样
    「矿河镇 / 矿河振 / 矿河真 / 矿合镇 …」会把「匡河镇」挤到很后面；
    改成按排名和排序后，匡（kuang 里排第 2）+ 河（第 1）+ 镇（第 1）= 1，
    稳稳排在前面，几次请求就能命中。
    """
    p2c = load_table().get("py2chars") or {}
    sylls = split_pinyin(pinyin.lower())
    if not sylls:
        return []
    if len(sylls) > 8:                    # 音节太多时缩小候选，避免组合爆炸
        per_syllable = min(per_syllable, 2)

    groups = []
    for syllable in sylls:
        chars = (p2c.get(syllable) or [])[:per_syllable]
        if not chars:
            return []
        groups.append(list(enumerate(chars)))     # [(排名, 字), ...]

    scored = []
    for combo in itertools.product(*groups):
        score = sum(rank for rank, _ in combo)
        scored.append((score, "".join(ch for _, ch in combo)))
    scored.sort(key=lambda item: item[0])
    return [text for _, text in scored[:limit]]


def looks_like_pinyin(text):
    """输入是否像拼音串（纯 ASCII 字母）"""
    return bool(text) and text.isascii() and text.isalpha()
