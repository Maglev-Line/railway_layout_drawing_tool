"""铁路配线图绘制器：程序入口。"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("铁路配线图绘制器")
    app.setApplicationDisplayName("铁路配线图绘制器")
    app.setOrganizationName("RailLayout")
    app.setApplicationVersion("1.0")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
