from operator import truediv
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from card import ImageReader, PunchCard

import sys

class ZoomableGraphicsView(QGraphicsView):
    def __init__ (self, parent=None):
        super(ZoomableGraphicsView, self).__init__ (parent)

    def wheelEvent(self, event: QWheelEvent):
        oldAnchor = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        angle = event.angleDelta().y()

        zoomFactor = 1.25 if angle > 0 else 1 / 1.25

        self.scale(zoomFactor, zoomFactor)
        self.setTransformationAnchor(oldAnchor)

class QPixmapImageReader(ImageReader):
    qpix: QPixmap

    def __init__(self, qpix):
        self.qpix = qpix

    def size(self):
        return (int(self.qpix.size().width()),
                int(self.qpix.size().height()))

    def get_pixel(self, x, y):
        return QColor(self.qpix.pixel(x, y)).getRgb()

class MainWindow(QMainWindow):
    """An Application example to draw using a pen """

    def __init__(self, parent=None):
        QMainWindow.__init__(self, parent)

        self.scene = QGraphicsScene()
        self.scene_widget = ZoomableGraphicsView(self.scene)

        self.sample = QImage("examples/foto.png")
        self.sample_pixmap = QPixmap(self.sample)
        self.sample_item = self.scene.addPixmap(self.sample_pixmap)

        self.bar = self.make_toolbar()
        
        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(font)

        split = QSplitter(Qt.Vertical)
        split.addWidget(self.scene_widget)
        split.addWidget(self.text_edit)

        self.setCentralWidget(split)

        self.color = Qt.black
        self.set_color(self.color)
        self.reader = QPixmapImageReader(self.sample)
        self.card = PunchCard(self.reader)

        txt = self.card.dump("xx")
        self.text_edit.setText(txt)

    def make_toolbar(self):
        bar = self.addToolBar("Menu")
        bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        self._save_action = bar.addAction(
            qApp.style().standardIcon(QStyle.SP_DialogSaveButton),
            "Save",
            self.on_save
        )

        self._save_action.setShortcut(QKeySequence.Save)

        self._open_action = bar.addAction(
            qApp.style().standardIcon(QStyle.SP_DialogOpenButton),
            "Open",
            self.on_open
        )

        self._open_action.setShortcut(QKeySequence.Open)

        bar.addAction(
            qApp.style().standardIcon(QStyle.SP_DialogResetButton),
            "Clear",
            self.clear,
        )

        bar.addSeparator()

        self.color_action = QAction(self)
        self.color_action.triggered.connect(self.on_color_clicked)
        bar.addAction(self.color_action)
        
        return bar

    def clear(self):
        print("succhia")

    def dialog(self, title):
        mime_type_filters = ["image/png", "image/jpeg"]
        dialog = QFileDialog(self, title)
        dialog.setMimeTypeFilters(mime_type_filters)
        dialog.setFileMode(QFileDialog.AnyFile)
        dialog.setDefaultSuffix("png")
        dialog.setDirectory(QStandardPaths.writableLocation(QStandardPaths.PicturesLocation))
        return dialog
        
    @Slot()
    def on_save(self):
        dialog = self.dialog("Save File")
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        if dialog.exec() == QFileDialog.Accepted:
            if dialog.selectedFiles():
                name = dialog.selectedFiles()[0]
                print(f"save {name}")

    @Slot()
    def on_open(self):
        dialog = self.dialog("Load File")
        dialog.setAcceptMode(QFileDialog.AcceptOpen)
        if dialog.exec() == QFileDialog.Accepted:
            if dialog.selectedFiles():
                name = dialog.selectedFiles()[0]
                print(f"load {name}")

    @Slot()
    def on_color_clicked(self):
        color = QColorDialog.getColor(self.color, self)
        if color:
            self.set_color(color)

    def set_color(self, color: QColor = Qt.black):
        self.color = color

        # Create color icon
        pix_icon = QPixmap(32, 32)
        pix_icon.fill(self.color)

        self.color_action.setIcon(QIcon(pix_icon))
        self.color_action.setText(QColor(self.color).name())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


