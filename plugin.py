# -*- coding: utf-8 -*-
"""插件主体：注册定位器滤镜，并提供天地图 Key 的设置入口。"""

from qgis.core import QgsApplication

try:                                    # Qt6（QGIS 4）把 QAction 放在 QtGui
    from qgis.PyQt.QtGui import QAction
except ImportError:                     # Qt5（QGIS 3）
    from qgis.PyQt.QtWidgets import QAction

from . import config
from .locator import McaLocatorFilter, TdtLocatorFilter

MENU_NAME = "中国地名搜索"
ICON_SEARCH = ":/images/themes/default/mActionSearch.svg"


class CnPlaceSearchPlugin(object):
    """QGIS 插件对象。

    ``initGui`` 里做两件事：注册两个定位器滤镜、挂一个设置 Key 的菜单项。
    """

    def __init__(self, iface):
        self.iface = iface
        self.filters = []
        self.action_settings = None
        self.action_about = None

    # -------------------------------------------------------------- 生命周期
    def initGui(self):
        # 1) 两个定位器滤镜
        for filter_class in (McaLocatorFilter, TdtLocatorFilter):
            locator_filter = filter_class(self.iface)
            self.filters.append(locator_filter)
            self.iface.registerLocatorFilter(locator_filter)

        # 2) 菜单项：设置天地图 Key
        self.action_settings = QAction(
            QgsApplication.getThemeIcon(ICON_SEARCH) if hasattr(QgsApplication, "getThemeIcon")
            else QAction(None).icon(),
            "设置天地图 Key…", self.iface.mainWindow())
        self.action_settings.setObjectName("cnPlaceSearchSettings")
        self.action_settings.triggered.connect(self.open_settings)
        self.iface.addPluginToMenu(MENU_NAME, self.action_settings)

        # 3) 菜单项：关于 / 用法
        self.action_about = QAction("用法说明", self.iface.mainWindow())
        self.action_about.setObjectName("cnPlaceSearchAbout")
        self.action_about.triggered.connect(self.show_about)
        self.iface.addPluginToMenu(MENU_NAME, self.action_about)

        config.log("插件已加载：民政部地名库 + 天地图 POI（天地图 Key：%s）"
                   % config.tianditu_key_hint())

    def unload(self):
        for locator_filter in self.filters:
            try:
                self.iface.deregisterLocatorFilter(locator_filter)
            except Exception:
                pass
        self.filters = []

        for action in (self.action_settings, self.action_about):
            if action is not None:
                try:
                    self.iface.removePluginMenu(MENU_NAME, action)
                except Exception:
                    pass
        self.action_settings = None
        self.action_about = None

    # -------------------------------------------------------------- 设置入口
    def open_settings(self):
        """弹框填写天地图 Key（不需要改代码或配置文件）"""
        from qgis.PyQt.QtWidgets import QInputDialog, QLineEdit

        mode = getattr(QLineEdit, "EchoMode", QLineEdit)
        normal = getattr(mode, "Normal", 0)

        current = config.tianditu_key()
        text, ok = QInputDialog.getText(
            self.iface.mainWindow(),
            "设置天地图 Key",
            "请输入天地图 Key（tk）：\n"
            "留空 = 停用天地图数据源（民政部地名库不受影响）。\n"
            "申请地址：https://console.tianditu.gov.cn/",
            normal, current)
        if not ok:
            return
        if config.set_tianditu_key(text):
            self.iface.messageBar().pushSuccess(
                "中国地名搜索",
                "天地图 Key 已保存（%s）。立即生效，无需重启。" % config.tianditu_key_hint())

    def show_about(self):
        """用法说明"""
        from qgis.PyQt.QtWidgets import QMessageBox

        QMessageBox.information(
            self.iface.mainWindow(),
            "中国地名搜索 · 用法",
            "<b>在定位器里用（Ctrl+K）</b><br><br>"
            "· 直接输入地名 → 查<b>民政部国家地名信息库</b>（带地名来历、历史沿革）<br>"
            "· <code>tdt 医院</code> → 查<b>天地图 POI</b>（当前地图视野内）<br><br>"
            "<b>容错</b><br>"
            "· 打错同音字会自动尝试，例如「框河镇」→「匡河镇」<br>"
            "· 也可以直接输拼音，例如 <code>kuanghezhen</code><br><br>"
            "<b>选中结果回车</b>：地图飞到该位置，并在「地名搜索结果」图层落点。<br><br>"
            "天地图数据源需要 Key，在菜单「中国地名搜索 → 设置天地图 Key」里填。")
