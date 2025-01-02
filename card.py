#!/usr/bin/env python3

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from dataclasses import dataclass
from copy import deepcopy

import sys

IBM_MODEL_029_KEYPUNCH = """
    /&-0123456789ABCDEFGHIJKLMNOPQR/STUVWXYZ:#@'="`.<(+|!$*);^~,%_>? |
12 / O           OOOOOOOOO                        OOOOOO             |
11|   O                   OOOOOOOOO                     OOOOOO       |
 0|    O                           OOOOOOOOO                  OOOOOO |
 1|     O        O        O        O                                 |
 2|      O        O        O        O       O     O     O     O      |
 3|       O        O        O        O       O     O     O     O     |
 4|        O        O        O        O       O     O     O     O    |
 5|         O        O        O        O       O     O     O     O   |
 6|          O        O        O        O       O     O     O     O  |
 7|           O        O        O        O       O     O     O     O |
 8|            O        O        O        O OOOOOOOOOOOOOOOOOOOOOOOO |
 9|             O        O        O        O                         | 
  |__________________________________________________________________|"""


def master_card_to_map(master_card_string):
    # Turn the ASCII art sideways and build a hash look up for
    # column values, for example:
    #   (O, , ,O, , , , , , , , ):A
    #   (O, , , ,O, , , , , , , ):B
    #   (O, , , , ,O, , , , , , ):C
    rows = master_card_string[1:].split('\n')
    rotated = [[r[i] for r in rows[0:13]] for i in range(5, len(rows[0]) - 1)]
    translate = {}
    for v in rotated:
        translate[tuple(v[1:])] = v[0]
    return translate


translate = master_card_to_map(IBM_MODEL_029_KEYPUNCH)


class ZoomableGraphicsView(QGraphicsView):
    def __init__(self, parent=None):
        super(ZoomableGraphicsView, self).__init__(parent)

    def wheelEvent(self, event: QWheelEvent):
        oldAnchor = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        angle = event.angleDelta().y()

        zoomFactor = 1.25 if angle > 0 else 1 / 1.25

        self.scale(zoomFactor, zoomFactor)
        self.setTransformationAnchor(oldAnchor)


class Handle(QGraphicsItemGroup):
    def __init__(self, parent):
        super().__init__(parent)

        self.circle = QGraphicsEllipseItem()

        self.circle.setRect(QRect(-10, -10, 20, 20))
        self.circle.setBrush(QColor.fromRgb(0, 30, 200))
        self.circle.setPen(QColor.fromRgb(0, 30, 190))

        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

        self.addToGroup(self.circle)

        self.changed = lambda pos: None

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.changed()

        return super().itemChange(change, value)


@dataclass
class CardGeometry:
    top: int
    right: int
    bottom: int
    left: int

    @property
    def width(self):
        return self.right - self.left

    @property
    def height(self):
        return self.bottom - self.top

    @property
    def qrect(self):
        return QRect(self.left, self.top,
                     self.width, self.height)

    @property
    def top_left(self):
        return QPoint(self.left, self.top)

    @property
    def bottom_right(self):
        return QPoint(self.right, self.bottom)


@dataclass
class CardFormat:
    columns: int
    rows: int
    reference_width: float
    top_margin: float
    left_margin: float
    columns_spacing: float
    rows_spacing: float

    threshold: float


def word_from_data(data):
    word = ''

    for x in data:
        code_key = []
        for y in x:
            def key_str(x): return 'O' if x else ' '
            dot = y
            code_key.append(key_str(dot))

        code_key = tuple(code_key)
        word += translate.get(code_key, '•')

    return word


def ascii_card_from_data(data, card_format, word):
    h1 = '  ' + '_' * card_format.columns
    h2 = '/ ' + ' ' * card_format.columns + '|'
    t  = '| ' + word + ' ' * (card_format.columns - len(word)) + '|'

    lines = [h1, h2, t]

    for y in range(card_format.rows):
        line = ['| ']

        for x in range(card_format.columns):
            def bit_str(x): return '0' if x else '.'

            dot = data[x][y]
            line.append(bit_str(dot))

        line.append('|')
        lines.append("".join(line))

    lines.append('`-' + '-' * card_format.columns)
    return "\n".join(lines)


test_format = CardFormat(
    columns=80,
    rows=12,
    reference_width=(7 + 3 / 8),
    top_margin=0.56,
    left_margin=0.25,
    rows_spacing=0.56,
    columns_spacing=0.088,

    threshold=0.2
)

class CardRecognizer:
    path: str
    image: QImage
    image_pixmap: QPixmap
    geometry: CardGeometry
    format: CardFormat

    def __init__(self, path):
        self.path = path
        self.image = QImage(path)
        self.image_pixmap = QPixmap(self.image)

        if self.image_pixmap.isNull():
            raise Exception(f"cannot open image file at path: {path}")

        self.geometry = CardGeometry(0, 0, 0, 0)
        self.format = deepcopy(test_format)

    @property
    def row_y(self):
        vertical_scale = self.geometry.height / self.format.reference_width

        y = self.geometry.top + vertical_scale * self.format.top_margin
        for _ in range(self.format.rows):
            yield y
            y += vertical_scale * self.format.rows_spacing

    @property
    def column_x(self):
        horizontal_scale = self.geometry.width / self.format.reference_width
        x = self.geometry.left + horizontal_scale * self.format.left_margin

        for _ in range(self.format.columns):
            yield x
            x += horizontal_scale * self.format.columns_spacing

    @property
    def row_lines(self):
        return (QLineF(self.geometry.left, y, self.geometry.right, y)
                for y in self.row_y)

    @property
    def column_lines(self):
        return (QLineF(x, self.geometry.top, x, self.geometry.bottom)
                for x in self.column_x)

    def parse_card(self):
        data = []
        image_size = self.image.size()

        for x in self.column_x:
            column = []
            data.append(column)

            for y in self.row_y:
                if (x < image_size.width() and
                    y < image_size.height() and
                    x >= 0 and
                    y >= 0):

                    color = self.image.pixel(x, y)
                    r, g, b, _ = QColor(color).getRgbF()
                    gray = (r + g + b) / 3

                    isHole = gray < self.format.threshold
                    column.append(isHole)

                else:
                    column.append(False)

        return data


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        QMainWindow.__init__(self, parent)

        bar = self.addToolBar("Toolbar")
        bar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)

        self.open_action = bar.addAction(
            self.style().standardIcon(QStyle.SP_DialogOpenButton),
            "Open",
            self.on_open
        )
        self.open_action.setShortcut(QKeySequence.Open)

        bar.addSeparator()

        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        font.setPointSize(12)
        font.setWeight(QFont.Bold)

        self.text_label = QLabel()
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setContentsMargins(10, 10, 10, 10)
        self.text_label.setFont(font)
        bar.addWidget(self.text_label)

        self.scene = QGraphicsScene()
        self.scene_widget = ZoomableGraphicsView(self.scene)

        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(font)
        self.text_edit.setMinimumHeight(200)

        panel_group = QGroupBox("Card format")
        panel_group.setFlat(True)
        panel_layout = QFormLayout()

        minimum_spin_size = 100

        self.columns_edit = QSpinBox()
        self.columns_edit.setMinimumWidth(minimum_spin_size)
        self.columns_edit.valueChanged.connect(self.on_ui_change)
        panel_layout.addRow("Columns", self.columns_edit)

        self.rows_edit = QSpinBox()
        self.rows_edit.setMinimumWidth(minimum_spin_size)
        self.rows_edit.valueChanged.connect(self.on_ui_change)
        panel_layout.addRow("Rows", self.rows_edit)

        self.reference_width_edit = QDoubleSpinBox()
        self.reference_width_edit.setSingleStep(0.01)
        self.reference_width_edit.setMinimumWidth(minimum_spin_size)
        self.reference_width_edit.valueChanged.connect(self.on_ui_change)
        panel_layout.addRow("Reference width", self.reference_width_edit)

        self.top_margin_edit = QDoubleSpinBox()
        self.top_margin_edit.setSingleStep(0.01)
        self.top_margin_edit.setMinimumWidth(minimum_spin_size)
        self.top_margin_edit.valueChanged.connect(self.on_ui_change)
        panel_layout.addRow("Top Margin", self.top_margin_edit)

        self.left_margin_edit = QDoubleSpinBox()
        self.left_margin_edit.setSingleStep(0.01)
        self.left_margin_edit.setMinimumWidth(minimum_spin_size)
        self.left_margin_edit.valueChanged.connect(self.on_ui_change)
        panel_layout.addRow("Left Margin", self.left_margin_edit)

        self.rows_spacing_edit = QDoubleSpinBox()
        self.rows_spacing_edit.setSingleStep(0.01)
        self.rows_spacing_edit.setMinimumWidth(minimum_spin_size)
        self.rows_spacing_edit.valueChanged.connect(self.on_ui_change)
        panel_layout.addRow("Rows Spacing", self.rows_spacing_edit)

        self.columns_spacing_edit = QDoubleSpinBox()
        self.columns_spacing_edit.setSingleStep(0.01)
        self.columns_spacing_edit.setDecimals(3)
        self.columns_spacing_edit.setMinimumWidth(minimum_spin_size)
        self.columns_spacing_edit.valueChanged.connect(self.on_ui_change)
        panel_layout.addRow("Columns Spacing", self.columns_spacing_edit)

        self.threshold_edit = QDoubleSpinBox()
        self.threshold_edit.setSingleStep(0.01)
        self.threshold_edit.setMinimumWidth(minimum_spin_size)
        self.threshold_edit.valueChanged.connect(self.on_ui_change)
        panel_layout.addRow("Threshold", self.threshold_edit)

        panel_group.setLayout(panel_layout)

        self.cards_list = QListWidget()
        self.cards_list.itemSelectionChanged.connect(self.on_card_selection)

        hor_split = QSplitter(Qt.Horizontal)
        hor_split.addWidget(self.cards_list)
        hor_split.addWidget(self.scene_widget)
        hor_split.addWidget(panel_group)

        split = QSplitter(Qt.Vertical)
        split.addWidget(hor_split)
        split.addWidget(self.text_edit)

        self.setCentralWidget(split)

        self.image_item = QGraphicsPixmapItem()
        self.scene.addItem(self.image_item)

        self.top_left_handle = Handle(None)
        self.top_left_handle.changed = self.on_ui_change
        self.scene.addItem(self.top_left_handle)

        self.bottom_right_handle = Handle(None)
        self.bottom_right_handle.changed = self.on_ui_change
        self.scene.addItem(self.bottom_right_handle)

        self.rect = QGraphicsRectItem()
        self.rect.setPen(QColor(0, 0, 255))
        self.scene.addItem(self.rect)

        self.items_to_delete = []

        self.recognizers = []
        self.selected_recognizer = None

        #self.load_image("examples/foto.png")

    def load_images(self, paths: [str]):
        try:
            for path in paths:
                card_recognizer = CardRecognizer(path)
                self.recognizers.append(card_recognizer)

            self.cards_list.clear()
            self.cards_list.addItems((i.path for i in self.recognizers))

            self.select_recognizer(0)

        except Exception as e:
            box = QMessageBox()
            box.setWindowTitle = "Error loading file"
            box.setText(str(e))
            box.setIcon(QMessageBox.Critical)
            box.setStandardButtons(QMessageBox.Ok)
            box.exec()

    def select_recognizer(self, idx):
        recognizer = self.recognizers[idx]
        self.selected_recognizer = idx
        self.image_item.setPixmap(recognizer.image_pixmap)
        self.set_ui_values(recognizer)
        self.update(recognizer)

    def set_ui_values(self, recognizer):
        self.updating = True
        self.top_left_handle.setPos(recognizer.geometry.top_left)
        self.bottom_right_handle.setPos(recognizer.geometry.bottom_right)
        self.columns_edit.setValue(recognizer.format.columns)
        self.rows_edit.setValue(recognizer.format.rows)
        self.reference_width_edit.setValue(recognizer.format.reference_width)
        self.top_margin_edit.setValue(recognizer.format.top_margin)
        self.left_margin_edit.setValue(recognizer.format.left_margin)
        self.rows_spacing_edit.setValue(recognizer.format.rows_spacing)
        self.columns_spacing_edit.setValue(recognizer.format.columns_spacing)
        self.threshold_edit.setValue(recognizer.format.threshold)
        self.updating = False

    def ui_changed(self, recognizer):
        if self.updating: return

        recognizer.geometry.left   = self.top_left_handle.pos().x()
        recognizer.geometry.top    = self.top_left_handle.pos().y()
        recognizer.geometry.right  = self.bottom_right_handle.pos().x()
        recognizer.geometry.bottom = self.bottom_right_handle.pos().y()

        recognizer.format.columns         = self.columns_edit.value()
        recognizer.format.rows            = self.rows_edit.value()
        recognizer.format.reference_width = self.reference_width_edit.value()
        recognizer.format.top_margin      = self.top_margin_edit.value()
        recognizer.format.left_margin     = self.left_margin_edit.value()
        recognizer.format.rows_spacing    = self.rows_spacing_edit.value()
        recognizer.format.columns_spacing = self.columns_spacing_edit.value()
        recognizer.format.threshold       = self.threshold_edit.value()

        self.update(recognizer)

    def update(self, recognizer):
        self.rect.setRect(recognizer.geometry.qrect)

        for line in self.items_to_delete:
            self.scene.removeItem(line)

        self.items_to_delete = []

        for line in recognizer.row_lines:
            line_item = self.scene.addLine(line)
            line_item.setPen(QColor(255, 0, 255))
            self.items_to_delete.append(line_item)

        for line in recognizer.column_lines:
            line_item = self.scene.addLine(line)
            line_item.setPen(QColor(0, 255, 255))
            self.items_to_delete.append(line_item)

        data = recognizer.parse_card()
        word = word_from_data(data)
        txt  = ascii_card_from_data(data, recognizer.format, word)

        for (x, column) in zip(recognizer.column_x, data):
            for (y, one) in zip(recognizer.row_y, column):
                dot = QGraphicsEllipseItem(QRect(-2 + x, -4 + y, 4, 8))
                if one:
                    dot.setPen(QColor(255, 255, 255))
                    dot.setBrush(QColor(0, 0, 0))
                else:
                    dot.setPen(QColor(0, 0, 0))
                    dot.setBrush(QColor(255, 255, 255))

                self.scene.addItem(dot)
                self.items_to_delete.append(dot)

        self.text_label.setText(word)
        self.text_edit.setText(txt)

    def on_ui_change(self):
        idx = self.selected_recognizer
        if idx is None: return
        recognizer = self.recognizers[idx]
        self.ui_changed(recognizer)

    def on_open(self):
        dialog = QFileDialog(self, "Load Files")
        dialog.setFileMode(QFileDialog.ExistingFiles)
        dialog.setAcceptMode(QFileDialog.AcceptOpen)

        if dialog.exec() == QFileDialog.Accepted:
            if dialog.selectedFiles():
                self.load_images(dialog.selectedFiles())

    def on_card_selection(self):
        selected_items = self.cards_list.selectedItems()
        if selected_items:
            item_index = self.cards_list.row(selected_items[0])
            self.select_recognizer(item_index)
        else:
            self.selected_recognizer = None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
