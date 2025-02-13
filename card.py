#!/usr/bin/env python3

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from dataclasses import dataclass
from copy import deepcopy

import sys
import json

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
    rows = master_card_string[1:].split("\n")
    rotated = [[r[i] for r in rows[0:13]] for i in range(5, len(rows[0]) - 1)]
    translate = {}
    for v in rotated:
        translate[tuple(v[1:])] = v[0]
    return translate


translate = master_card_to_map(IBM_MODEL_029_KEYPUNCH)


class ZoomableGraphicsView(QGraphicsView):
    def __init__(self, parent=None):
        super(ZoomableGraphicsView, self).__init__(parent)
        self.setDragMode(QGraphicsView.ScrollHandDrag)

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
        return QRect(self.left, self.top, self.width, self.height)

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
    reference_height: float
    top_margin: float
    left_margin: float
    columns_spacing: float
    rows_spacing: float
    threshold: float


@dataclass
class Card:
    geometry: CardGeometry
    format: CardFormat
    path: str

    @property
    def image_data(self):
        if hasattr(self, "_image_data"):
            return self._image_data

        img = QImage(self.path)
        pxm = QPixmap(img)

        if pxm.isNull():
            raise Exception(f"cannot open image file at path: {self.path}")

        self._image_data = (img, pxm)
        return self._image_data

    @property
    def row_y(self):
        vertical_scale = self.geometry.height / self.format.reference_height
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
        return (
            QLineF(self.geometry.left, y, self.geometry.right, y) for y in self.row_y
        )

    @property
    def column_lines(self):
        return (
            QLineF(x, self.geometry.top, x, self.geometry.bottom) for x in self.column_x
        )

    @property
    def image(self):
        return self.image_data[0]

    @property
    def image_pixmap(self):
        return self.image_data[1]

    def parse_card(self):
        data = []
        image_size = self.image.size()

        for x in self.column_x:
            column = []
            data.append(column)

            for y in self.row_y:
                if (
                    x < image_size.width()
                    and y < image_size.height()
                    and x >= 0
                    and y >= 0
                ):

                    color = self.image.pixel(x, y)
                    r, g, b, _ = QColor(color).getRgbF()
                    gray = (r + g + b) / 3

                    isHole = gray < self.format.threshold
                    column.append(isHole)

                else:
                    column.append(False)

        return data


@dataclass
class Deck:
    cards: list[Card]

    def to_json(self):
        return {
            "cards": [
                {
                    "path": card.path,
                    "geometry": {
                        "top": card.geometry.top,
                        "right": card.geometry.right,
                        "bottom": card.geometry.bottom,
                        "left": card.geometry.left,
                    },
                    "format": {
                        "columns": card.format.columns,
                        "rows": card.format.rows,
                        "reference_width": card.format.reference_width,
                        "reference_height": card.format.reference_height,
                        "top_margin": card.format.top_margin,
                        "left_margin": card.format.left_margin,
                        "columns_spacing": card.format.columns_spacing,
                        "rows_spacing": card.format.rows_spacing,
                        "threshold": card.format.threshold,
                    },
                }
                for card in self.cards
            ]
        }

    @staticmethod
    def from_json(data):
        cards = []
        for card_data in data["cards"]:
            geometry = CardGeometry(
                top=card_data["geometry"]["top"],
                right=card_data["geometry"]["right"],
                bottom=card_data["geometry"]["bottom"],
                left=card_data["geometry"]["left"],
            )

            format = CardFormat(
                columns=card_data["format"]["columns"],
                rows=card_data["format"]["rows"],
                reference_width=card_data["format"]["reference_width"],
                reference_height=card_data["format"]["reference_height"],
                top_margin=card_data["format"]["top_margin"],
                left_margin=card_data["format"]["left_margin"],
                columns_spacing=card_data["format"]["columns_spacing"],
                rows_spacing=card_data["format"]["rows_spacing"],
                threshold=card_data["format"]["threshold"],
            )

            card = Card(geometry=geometry, format=format, path=card_data["path"])
            cards.append(card)

        return Deck(cards=cards)

    @staticmethod
    def from_paths(paths):
        cards = [
            Card(
                path=path,
                geometry=CardGeometry(top=0, right=0, bottom=0, left=0),
                format=deepcopy(test_format),
            )
            for path in paths
        ]
        return Deck(cards=cards)


def word_from_data(data):
    word = ""

    for x in data:
        code_key = []
        for y in x:

            def key_str(x):
                return "O" if x else " "

            dot = y
            code_key.append(key_str(dot))

        code_key = tuple(code_key)
        word += translate.get(code_key, "•")

    return word


def ascii_card_from_data(data, card_format, word):
    h1 = "  " + "_" * card_format.columns
    h2 = "/ " + " " * card_format.columns + "|"
    t = "| " + word + " " * (card_format.columns - len(word)) + "|"

    lines = [h1, h2, t]

    for y in range(card_format.rows):
        line = ["| "]

        for x in range(card_format.columns):

            def bit_str(x):
                return "0" if x else "."

            dot = data[x][y]
            line.append(bit_str(dot))

        line.append("|")
        lines.append("".join(line))

    lines.append("`-" + "-" * card_format.columns)
    return "\n".join(lines)


# CARD_WIDTH = 7.0 + 3.0/8.0 # Inches
# CARD_HEIGHT = 3.25 # Inches
# CARD_COL_WIDTH = 0.087 # Inches
# CARD_HOLE_WIDTH = 0.055 # Inches IBM, 0.056 Control Data
# CARD_ROW_HEIGHT = 0.25 # Inches
# CARD_HOLE_HEIGHT = 0.125 # Inches
# CARD_TOPBOT_MARGIN = 3.0/16.0 # Inches at top and bottom
# CARD_SIDE_MARGIN = 0.2235 # Inches on each side

test_format = CardFormat(
    columns=80,
    rows=12,
    reference_width=(7 + 3 / 8),
    reference_height=3.25,
    top_margin=(3 / 16),
    left_margin=0.2235,
    rows_spacing=1 / 4,
    columns_spacing=0.087,
    threshold=0.2,
)


def create_spinbox(layout, klass, on_change, label, step=1, decimals=0):
    spinbox = klass()
    spinbox.setSingleStep(step)
    spinbox.setMinimumWidth(100)

    spinbox.setMaximum(999999999)
    spinbox.setMinimum(-999999999)

    if decimals != 0:
        spinbox.setDecimals(decimals)

    if on_change:
        spinbox.valueChanged.connect(on_change)
    else:
        spinbox.setReadOnly(True)

    layout.addRow(label, spinbox)
    return spinbox


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        QMainWindow.__init__(self, parent)

        self.items_to_delete = []
        self.selected_card_idx = None
        self.updating = False
        self.updating_geo_panel = False
        self.geo_paste_buffer = None

        self.deck = Deck(cards=[])

        bar = self.addToolBar("Toolbar")
        bar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)

        self.open_deck_action = bar.addAction(
            self.style().standardIcon(QStyle.SP_DialogOpenButton),
            "Open Deck",
            self.on_open_deck,
        )

        self.save_project_action = bar.addAction(
            self.style().standardIcon(QStyle.SP_DialogSaveButton),
            "Save Deck",
            self.on_save_deck,
        )
        self.save_project_action.setShortcut(QKeySequence.Save)

        bar.addSeparator()

        self.open_action = bar.addAction(
            self.style().standardIcon(QStyle.SP_DialogOpenButton), "Open", self.on_open
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

        self.cards_list = QListWidget()
        self.cards_list.itemSelectionChanged.connect(self.on_card_selection)

        self.setCentralWidget(self.scene_widget)

        deck_panel = QDockWidget("Deck")
        deck_panel.setAllowedAreas(
            Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea
        )
        deck_panel.setWidget(self.cards_list)
        self.addDockWidget(Qt.LeftDockWidgetArea, deck_panel)

        ascii_card_panel = QDockWidget("Card")
        ascii_card_panel.setAllowedAreas(
            Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea
        )
        ascii_card_panel.setWidget(self.text_edit)
        self.addDockWidget(Qt.BottomDockWidgetArea, ascii_card_panel)

        format_panel = QDockWidget("Format")
        format_panel.setAllowedAreas(
            Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea
        )
        format_panel.setWidget(self.create_format_panel())
        self.addDockWidget(Qt.RightDockWidgetArea, format_panel)

        geometry_panel = QDockWidget("Geometry")
        geometry_panel.setAllowedAreas(
            Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea
        )
        geometry_panel.setWidget(self.create_geometry_panel())
        self.addDockWidget(Qt.RightDockWidgetArea, geometry_panel)

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

    def create_format_panel(self):
        panel_group = QGroupBox()
        panel_group.setFlat(True)
        panel_layout = QFormLayout()

        self.columns_edit = create_spinbox(
            panel_layout, QSpinBox, self.on_ui_change, "Columns"
        )
        self.rows_edit = create_spinbox(
            panel_layout, QSpinBox, self.on_ui_change, "Rows"
        )

        self.reference_width_edit = create_spinbox(
            panel_layout,
            QDoubleSpinBox,
            self.on_ui_change,
            "Reference width",
            step=0.01,
        )
        self.top_margin_edit = create_spinbox(
            panel_layout,
            QDoubleSpinBox,
            self.on_ui_change,
            "Top Margin",
            step=0.01,
        )
        self.left_margin_edit = create_spinbox(
            panel_layout,
            QDoubleSpinBox,
            self.on_ui_change,
            "Left Margin",
            step=0.01,
        )
        self.rows_spacing_edit = create_spinbox(
            panel_layout,
            QDoubleSpinBox,
            self.on_ui_change,
            "Rows Spacing",
            step=0.01,
        )
        self.columns_spacing_edit = create_spinbox(
            panel_layout,
            QDoubleSpinBox,
            self.on_ui_change,
            "Columns Spacing",
            step=0.01,
            decimals=3,
        )
        self.threshold_edit = create_spinbox(
            panel_layout,
            QDoubleSpinBox,
            self.on_ui_change,
            "Threshold",
            step=0.01,
        )

        panel_group.setLayout(panel_layout)
        return panel_group

    def create_geometry_panel(self):
        layout = QFormLayout()
        self.geometry_top_edit = create_spinbox(layout, QSpinBox, None, "Top")
        self.geometry_right_edit = create_spinbox(layout, QSpinBox, None, "Right")
        self.geometry_bottom_edit = create_spinbox(layout, QSpinBox, None, "Bottom")
        self.geometry_left_edit = create_spinbox(layout, QSpinBox, None, "Left")

        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(self.on_geo_copy_button)
        layout.addRow(self.copy_button)

        self.paste_button = QPushButton("Paste")
        self.paste_button.clicked.connect(self.on_geo_paste_button)
        self.paste_button.setEnabled(self.geo_paste_buffer is not None)
        layout.addRow(self.paste_button)

        group = QGroupBox()
        group.setFlat(True)
        group.setLayout(layout)
        return group

    def load_deck(self, deck):
        self.deck = deck

        self.cards_list.clear()
        self.cards_list.addItems((i.path.split("/")[-1] for i in self.deck.cards))

        self.select_card(0)

    def select_card(self, idx):
        card = self.deck.cards[idx]
        self.selected_card_idx = idx
        self.image_item.setPixmap(card.image_pixmap)
        self.set_ui_values()
        self.redraw_grid_and_text(card)

    @property
    def format(self):
        return self.deck.cards[self.selected_card_idx].format

    @property
    def geometry(self):
        return self.deck.cards[self.selected_card_idx].geometry

    def set_ui_values(self):
        self.updating = True
        self.top_left_handle.setPos(self.geometry.top_left)
        self.bottom_right_handle.setPos(self.geometry.bottom_right)
        self.columns_edit.setValue(self.format.columns)
        self.rows_edit.setValue(self.format.rows)
        self.reference_width_edit.setValue(self.format.reference_width)
        self.top_margin_edit.setValue(self.format.top_margin)
        self.left_margin_edit.setValue(self.format.left_margin)
        self.rows_spacing_edit.setValue(self.format.rows_spacing)
        self.columns_spacing_edit.setValue(self.format.columns_spacing)
        self.threshold_edit.setValue(self.format.threshold)
        self.geometry_top_edit.setValue(self.geometry.top)
        self.geometry_right_edit.setValue(self.geometry.right)
        self.geometry_bottom_edit.setValue(self.geometry.bottom)
        self.geometry_left_edit.setValue(self.geometry.left)
        self.updating = False

    def ui_changed(self, card):
        if self.updating:
            return

        self.geometry.left = self.top_left_handle.pos().x()
        self.geometry.top = self.top_left_handle.pos().y()
        self.geometry.right = self.bottom_right_handle.pos().x()
        self.geometry.bottom = self.bottom_right_handle.pos().y()

        self.format.columns = self.columns_edit.value()
        self.format.rows = self.rows_edit.value()
        self.format.reference_width = self.reference_width_edit.value()
        self.format.top_margin = self.top_margin_edit.value()
        self.format.left_margin = self.left_margin_edit.value()
        self.format.rows_spacing = self.rows_spacing_edit.value()
        self.format.columns_spacing = self.columns_spacing_edit.value()
        self.format.threshold = self.threshold_edit.value()

        self.redraw_grid_and_text(card)

    def redraw_grid_and_text(self, card):
        self.rect.setRect(self.geometry.qrect)

        for line in self.items_to_delete:
            self.scene.removeItem(line)

        self.items_to_delete = []

        for line in card.row_lines:
            line_item = self.scene.addLine(line)
            line_item.setPen(QColor(255, 0, 255))
            self.items_to_delete.append(line_item)

        for line in card.column_lines:
            line_item = self.scene.addLine(line)
            line_item.setPen(QColor(0, 255, 255))
            self.items_to_delete.append(line_item)

        data = card.parse_card()
        word = word_from_data(data)
        txt = ascii_card_from_data(data, self.format, word)

        colors = {
            False: QColor(0, 0, 0),
            True: QColor(255, 255, 255),
        }

        for x, column in zip(card.column_x, data):
            for y, one in zip(card.row_y, column):
                dot = QGraphicsEllipseItem(QRect(-2 + x, -4 + y, 4, 8))
                dot.setPen(colors[one])
                dot.setBrush(colors[not one])

                self.scene.addItem(dot)
                self.items_to_delete.append(dot)

        self.text_label.setText(word)
        self.text_edit.setText(txt)

    def on_ui_change(self):
        idx = self.selected_card_idx
        if idx is None:
            return
        card = self.deck.cards[idx]
        self.ui_changed(card)

    def on_card_selection(self):
        selected_items = self.cards_list.selectedItems()
        if selected_items:
            item_index = self.cards_list.row(selected_items[0])
            self.select_card(item_index)
        else:
            self.selected_card_idx = None

    def on_open(self):
        dialog = QFileDialog(self, "Load Files")
        dialog.setFileMode(QFileDialog.ExistingFiles)
        dialog.setAcceptMode(QFileDialog.AcceptOpen)

        if dialog.exec() == QFileDialog.Accepted and dialog.selectedFiles():
            deck = Deck.from_paths(dialog.selectedFiles())
            self.load_deck(deck)

    def on_open_deck(self):
        dialog = QFileDialog(self, "Load Deck")
        dialog.setFileMode(QFileDialog.ExistingFile)
        dialog.setAcceptMode(QFileDialog.AcceptOpen)

        if dialog.exec() == QFileDialog.Accepted and dialog.selectedFiles():
            with open(dialog.selectedFiles()[0], "r") as f:
                data = json.load(f)
                self.load_deck(Deck.from_json(data))

    def on_save_deck(self):
        dialog = QFileDialog(self, "Save Deck")
        dialog.setFileMode(QFileDialog.AnyFile)
        dialog.setAcceptMode(QFileDialog.AcceptSave)

        if dialog.exec() == QFileDialog.Accepted:
            if dialog.selectedFiles():
                with open(dialog.selectedFiles()[0], "w") as f:
                    json.dump(self.deck.to_json(), f)

    def on_geo_copy_button(self):
        self.geo_paste_buffer = deepcopy(self.geometry)
        self.paste_button.setEnabled(True)

    def on_geo_paste_button(self):
        if self.geo_paste_buffer is None:
            return

        self.geometry.top = self.geo_paste_buffer.top
        self.geometry.right = self.geo_paste_buffer.right
        self.geometry.bottom = self.geo_paste_buffer.bottom
        self.geometry.left = self.geo_paste_buffer.left
        self.set_ui_values()
        self.on_ui_change()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
