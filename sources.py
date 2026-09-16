# -*- coding: utf-8 -*-
"""数据源封装。

两个数据源：

* **民政部 · 中国国家地名信息库**（``dmfw.mca.gov.cn``）
  标准地名库。搜索接口可按名称模糊匹配；详情接口返回地名来历、含义、
  历史沿革、驻地变迁等文字。**不需要 Key**。
* **天地图 · 地名搜索 V2.0**（``api.tianditu.gov.cn/v2/search``）
  全量 POI（地名 + 机构 + 商铺）。``queryType=1`` 的普通搜索会遵守
  ``mapBound``（地图视野），适合"在当前视野里找东西"。**需要 Key**。

容错：两个源的搜索接口都不认拼音、也不认同音字（实测：搜「框河镇」
返回 0 条），所以这里在客户端做同音字替换与拼音转换，再由调用方控制
请求次数上限。
"""

import json
import urllib.parse
import urllib.request

from .pinyin import homophone_candidates, looks_like_pinyin, pinyin_candidates

MCA_API = "https://dmfw.mca.gov.cn/9095/stname"
TDT_API = "http://api.tianditu.gov.cn/v2/search"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

TIMEOUT = 8
DEFAULT_MAX_FALLBACK = 6      # 容错时最多再试几次


def _http_json(url, timeout=TIMEOUT):
    """发起 HTTP 请求并解析 JSON。

    只允许 http / https：调用方传的都是硬编码的 https 接口地址，这里再校验一次，
    避免 urlopen 接受 file: 之类的意外 scheme。
    """
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError("仅支持 http/https，收到: %s" % (scheme or "(空)"))

    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
    })
    # 上方已校验 scheme 只可能是 http/https
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
        return json.loads(resp.read().decode("utf-8", "ignore"))


# ------------------------------------------------------------------ 民政部
def mca_search(keyword, size=15):
    """民政部地名搜索，返回 records 列表（原始字段）"""
    url = MCA_API + "/listPub?" + urllib.parse.urlencode({
        "stName": keyword,
        "page": 1,
        "size": size,
        "searchType": 1,
        "year": "",
    })
    return _http_json(url).get("records") or []


def mca_detail(place_id):
    """地名详情（来历 / 含义 / 历史沿革 / 驻地变迁）"""
    return _http_json(MCA_API + "/detailsPub?id=" + urllib.parse.quote(place_id))


def mca_search_fuzzy(keyword, size=15, max_try=DEFAULT_MAX_FALLBACK):
    """先直搜，搜不到再按同音字 / 拼音容错。

    :return: ``(records, matched_keyword)``；``matched_keyword`` 为 None
             表示是原词直接命中的。
    """
    kw = (keyword or "").strip()
    if not kw:
        return [], None

    records = mca_search(kw, size)
    if records:
        return records, None

    if looks_like_pinyin(kw):
        candidates = pinyin_candidates(kw, limit=max_try)
    else:
        candidates = homophone_candidates(kw, limit=max_try)

    for cand in candidates:
        records = mca_search(cand, size)
        if records:
            return records, cand
    return [], None


# ------------------------------------------------------------------ 天地图
def tdt_search(keyword, map_bound, level, key, count=15):
    """天地图视野内搜索。

    :param map_bound: ``"minx,miny,maxx,maxy"``（WGS84 经纬度）
    :param level: 天地图级别 1-18。**低于 10 时接口不返回 POI 明细**，
                  调用方需自行夹到 10 以上。
    :param key: 天地图 Key
    """
    if not key:
        return []
    post = {
        "keyWord": keyword,
        "queryType": 1,        # 1 = 普通搜索（遵守 mapBound）；7 = 地名搜索，但忽略 mapBound
        "level": level,
        "mapBound": map_bound,
        "start": 0,
        "count": count,
        "show": 2,             # 返回详细 poi 信息
    }
    url = (TDT_API + "?postStr="
           + urllib.parse.quote(json.dumps(post, ensure_ascii=False))
           + "&type=query&tk=" + key)
    return _http_json(url).get("pois") or []


def tdt_search_fuzzy(keyword, map_bound, level, key,
                     count=15, max_try=DEFAULT_MAX_FALLBACK):
    """天地图版本的同音字 / 拼音容错搜索，返回 ``(pois, matched_keyword)``"""
    kw = (keyword or "").strip()
    if not kw or not key:
        return [], None

    pois = tdt_search(kw, map_bound, level, key, count)
    if pois:
        return pois, None

    if looks_like_pinyin(kw):
        candidates = pinyin_candidates(kw, limit=max_try)
    else:
        candidates = homophone_candidates(kw, limit=max_try)

    for cand in candidates:
        pois = tdt_search(cand, map_bound, level, key, count)
        if pois:
            return pois, cand
    return [], None


# ------------------------------------------------------------------ 工具
def coord_from_geometry(node):
    """从 ``gdm`` / ``pdm`` 这类几何字段里取出第一个坐标点。

    坐标可能藏在多层数组里，逐层下钻找 ``[lng, lat]``。
    """
    try:
        if not node or not node.get("coordinates"):
            return None
        stack = [node["coordinates"]]
        while stack:
            item = stack.pop()
            if not item:
                continue
            if (len(item) >= 2 and isinstance(item[0], (int, float))
                    and isinstance(item[1], (int, float))):
                return (float(item[0]), float(item[1]))
            for x in item:
                if isinstance(x, (list, tuple)):
                    stack.append(x)
    # 几何字段结构不固定，解析失败即视为无坐标
    except Exception:  # nosec B110
        pass
    return None


def mca_coord(record):
    """民政部记录的坐标：gdm 优先，退到 pdm"""
    if not record:
        return None
    return (coord_from_geometry(record.get("gdm"))
            or coord_from_geometry(record.get("pdm")))


def mca_region_text(record):
    """民政部记录的地域文字，如「湖北省 · 黄冈市 · 罗田县」"""
    return " · ".join([x for x in (
        record.get("province_name"),
        record.get("city_name"),
        record.get("area_name"),
    ) if x])
