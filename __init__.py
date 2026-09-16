# -*- coding: utf-8 -*-
"""QGIS 插件入口。

QGIS 会加载本目录（包名即插件名），调用 classFactory 拿到插件实例。
"""


def classFactory(iface):
    """QGIS 插件工厂函数。

    :param iface: QgisInterface 实例
    :return: 插件对象
    """
    from .plugin import CnPlaceSearchPlugin
    return CnPlaceSearchPlugin(iface)
