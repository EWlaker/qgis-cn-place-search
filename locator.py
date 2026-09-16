# -*- coding: utf-8 -*-
"""两个 QGIS 定位器滤镜 + 定位落点。

* :class:`McaLocatorFilter` —— 民政部国家地名信息库（前缀 ``dm``，不带前缀也参与）
* :class:`TdtLocatorFilter` —— 天地图地名搜索（前缀 ``tdt``，只在前缀下触发）
"""

import math

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsGeometry,
    QgsLocatorFilter,
    QgsLocatorResult,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)

from . import config, sources

MARKER_LAYER_NAME = "地名搜索结果"
MIN_CHARS = 2                 # 至少输入几个字才查
MIN_TDT_LEVEL = 10            # 天地图低于此级别不返回 POI 明细（实测）


# ------------------------------------------------------------------ 公共
def canvas_view(iface, min_level=MIN_TDT_LEVEL):
    """当前画布范围（WGS84 经纬度字符串）+ 对应的天地图级别。

    级别由比例尺换算（``level ≈ log2(559082264 / scale)``），并夹到
    ``[min_level, 18]``——天地图在 level ≤ 8 时不返回 POI 明细。
    """
    try:
        canvas = iface.mapCanvas()
        extent = canvas.extent()
        src = canvas.mapSettings().destinationCrs()
        dst = QgsCoordinateReferenceSystem("EPSG:4326")
        if src != dst:
            transform = QgsCoordinateTransform(src, dst, QgsProject.instance())
            extent = transform.transformBoundingBox(extent)
        bound = "%.6f,%.6f,%.6f,%.6f" % (
            extent.xMinimum(), extent.yMinimum(),
            extent.xMaximum(), extent.yMaximum())
        level = int(round(math.log(559082264.0 / max(canvas.scale(), 1.0), 2)))
        return bound, max(min_level, min(18, level))
    except Exception:
        return "-180,-90,180,90", min_level


def marker_layer():
    """结果图层（内存点图层），已存在则复用"""
    existing = QgsProject.instance().mapLayersByName(MARKER_LAYER_NAME)
    if existing:
        return existing[0]
    layer = QgsVectorLayer(
        "Point?crs=EPSG:4326"
        "&field=name:string(120)"
        "&field=ftype:string(60)"
        "&field=note:string(255)",
        MARKER_LAYER_NAME, "memory")
    QgsProject.instance().addMapLayer(layer)
    return layer


def locate(iface, lng, lat, name, ftype="", note=""):
    """落点 + 地图飞过去"""
    point = QgsPointXY(lng, lat)

    layer = marker_layer()
    if layer is None:
        return

    # 字段名兼容：早期版本图层用的是 type
    have = set(f.name() for f in layer.fields())
    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(point))
    if "name" in have:
        feature["name"] = name or ""
    if "ftype" in have:
        feature["ftype"] = ftype or ""
    elif "type" in have:
        feature["type"] = ftype or ""
    if "note" in have:
        feature["note"] = note or ""
    layer.dataProvider().addFeature(feature)
    layer.updateExtents()
    layer.triggerRepaint()

    canvas = iface.mapCanvas()
    try:
        src = QgsCoordinateReferenceSystem("EPSG:4326")
        dst = canvas.mapSettings().destinationCrs()
        if src != dst:
            transform = QgsCoordinateTransform(src, dst, QgsProject.instance())
            target = transform.transform(point)
        else:
            target = point
        canvas.setCenter(target)
        if canvas.scale() > 200000:
            canvas.zoomScale(50000)
        canvas.refresh()
    except Exception:
        canvas.setCenter(point)
        canvas.refresh()

    if iface is not None:
        iface.messageBar().pushSuccess(
            "中国地名搜索", "已定位：%s%s" % (name, ("（%s）" % ftype) if ftype else ""))


# ------------------------------------------------------------------ 民政部
class McaLocatorFilter(QgsLocatorFilter):
    """民政部 · 中国国家地名信息库"""

    def __init__(self, iface):
        super().__init__()
        self.iface = iface

    def name(self):
        return "cnplaces_mca"

    def clone(self):
        return McaLocatorFilter(self.iface)

    def displayName(self):
        return "中国地名 · 民政部地名库"

    def prefix(self):
        return "dm"

    def fetchResults(self, string, context, feedback):
        keyword = (string or "").strip()
        if len(keyword) < MIN_CHARS:
            return
        try:
            records, matched = sources.mca_search_fuzzy(keyword)
        except Exception as exc:
            config.log("民政部搜索失败「%s」：%s" % (keyword, exc))
            return

        if matched:
            config.log("民政部：「%s」无结果，同音/拼音命中「%s」" % (keyword, matched))
        config.log("民政部：「%s」→ %d 条%s"
                   % (keyword, len(records), ("（匹配 %s）" % matched) if matched else ""))

        for record in records:
            if feedback is not None and feedback.isCanceled():
                return
            result = QgsLocatorResult()
            result.filter = self
            result.displayString = record.get("standard_name") or ""
            desc = "%s　%s" % (record.get("place_type") or "",
                               sources.mca_region_text(record))
            if matched:
                desc = "〔按「%s」匹配〕 %s" % (matched, desc)
            result.description = desc
            result.group = "国家地名信息库"
            result.userData = {"rec": record, "coord": sources.mca_coord(record)}
            self.resultFetched.emit(result)

    def triggerResult(self, result):
        data = result.userData or {}
        record = data.get("rec") or {}
        name = record.get("standard_name") or result.displayString
        coord = data.get("coord")
        if not coord:
            if self.iface is not None:
                self.iface.messageBar().pushWarning(
                    "中国地名搜索", "「%s」在该地名库里没有坐标，无法定位。" % name)
            return
        locate(self.iface, coord[0], coord[1], name,
               record.get("place_type"), sources.mca_region_text(record))


# ------------------------------------------------------------------ 天地图
class TdtLocatorFilter(QgsLocatorFilter):
    """天地图 · 地名搜索（当前视野内）"""

    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        # 只在前缀下触发：不打 tdt 就不查它，避免每次搜索都双倍请求
        self.setUseWithoutPrefix(False)

    def name(self):
        return "cnplaces_tdt"

    def clone(self):
        return TdtLocatorFilter(self.iface)

    def displayName(self):
        return "中国地名 · 天地图 POI"

    def prefix(self):
        return "tdt"

    def fetchResults(self, string, context, feedback):
        keyword = (string or "").strip()
        if len(keyword) < MIN_CHARS:
            return

        key = config.tianditu_key()
        if not key:
            result = QgsLocatorResult()
            result.filter = self
            result.displayString = "尚未配置天地图 Key"
            result.description = "在插件菜单「中国地名搜索 → 设置天地图 Key」里填一个"
            result.group = "天地图"
            result.userData = {}
            self.resultFetched.emit(result)
            return

        bound, level = canvas_view(self.iface)
        try:
            pois, matched = sources.tdt_search_fuzzy(keyword, bound, level, key)
            if not pois:
                # 视野内没有 → 放宽到全球再试一次
                pois, matched2 = sources.tdt_search_fuzzy(
                    keyword, "-180,-90,180,90", level, key)
                matched = matched or matched2
        except Exception as exc:
            config.log("天地图搜索失败「%s」：%s" % (keyword, exc))
            return

        config.log("天地图：「%s」level=%d 视野=%s → %d 条%s"
                   % (keyword, level, bound, len(pois),
                      ("（匹配 %s）" % matched) if matched else ""))

        for poi in pois:
            if feedback is not None and feedback.isCanceled():
                return
            raw = (poi.get("lonlat") or "").replace(" ", "").split(",")
            if len(raw) != 2:
                continue
            try:
                lng, lat = float(raw[0]), float(raw[1])
            except ValueError:
                continue
            result = QgsLocatorResult()
            result.filter = self
            result.displayString = poi.get("name") or ""
            desc = "%s　%s" % (poi.get("typeName") or "", poi.get("address") or "")
            if matched:
                desc = "〔按「%s」匹配〕 %s" % (matched, desc)
            result.description = desc
            result.group = "天地图"
            result.userData = {"rec": poi, "coord": (lng, lat)}
            self.resultFetched.emit(result)

    def triggerResult(self, result):
        data = result.userData or {}
        record = data.get("rec") or {}
        coord = data.get("coord")
        if not coord:
            return
        locate(self.iface, coord[0], coord[1], result.displayString,
               record.get("typeName"), record.get("address"))
