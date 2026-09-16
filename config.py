# -*- coding: utf-8 -*-
"""配置读写与日志。

**天地图 Key 不写死在代码里**，按以下顺序读取：

1. QGIS 设置项 ``qgis_cn_place_search/tianditu_tk``
2. 环境变量 ``TIANDITU_TK``

两个都没有时，天地图数据源自动禁用（民政部源不受影响）。
插件菜单里提供了「设置天地图 Key」的入口，普通用户不必碰配置文件。
"""

import os

from qgis.core import QgsMessageLog, QgsSettings

TK_SETTING_KEY = "qgis_cn_place_search/tianditu_tk"
TK_ENV_VAR = "TIANDITU_TK"
LOG_TAG = "中国地名搜索"


def _info_level():
    """Qgis.Info 在不同版本里位置不同，做个兼容"""
    try:
        from qgis.core import Qgis
        lvl = getattr(Qgis, "Info", None)
        if lvl is not None:
            return lvl
        return getattr(getattr(Qgis, "MessageLevel", object), "Info", 0)
    except Exception:
        return 0


def log(message):
    """写入 QGIS 日志面板（标签：中国地名搜索）。

    日志写失败（比如面板还没就绪）不该影响插件功能，因此刻意忽略。
    """
    try:
        QgsMessageLog.logMessage(str(message), LOG_TAG, _info_level())
    # 写日志失败不影响功能，故意忽略
    except Exception:  # nosec B110
        pass


def tianditu_key():
    """取天地图 Key：QGIS 设置优先，其次环境变量，都没有返回空串

    读取 QGIS 设置失败（比如配置项类型异常）时，直接回退到环境变量。
    """
    try:
        value = QgsSettings().value(TK_SETTING_KEY, "")
        if value:
            return str(value).strip()
    # 读设置失败即回退环境变量，故意忽略
    except Exception:  # nosec B110
        pass
    return (os.environ.get(TK_ENV_VAR) or "").strip()


def set_tianditu_key(key):
    """保存天地图 Key（空串表示清除）"""
    try:
        QgsSettings().setValue(TK_SETTING_KEY, (key or "").strip())
        return True
    except Exception as exc:
        log("保存天地图 Key 失败：%s" % exc)
        return False


def has_tianditu_key():
    return bool(tianditu_key())


def tianditu_key_hint():
    """给用户看的 Key 提示（脱敏，只露前 6 位）"""
    key = tianditu_key()
    if not key:
        return "未配置"
    if len(key) <= 8:
        return key[:2] + "****"
    return key[:6] + "****" + key[-2:]
