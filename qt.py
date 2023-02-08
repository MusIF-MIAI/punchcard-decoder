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
    def __init__ (self, parent=None):
        super(ZoomableGraphicsView, self).__init__ (parent)

    def wheelEvent(self, event: QWheelEvent):
        oldAnchor = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        angle = event.angleDelta().y()

        zoomFactor = 1.25 if angle > 0 else 1 / 1.25

        self.scale(zoomFactor, zoomFactor)
        self.setTransformationAnchor(oldAnchor)


class Dot(QGraphicsItemGroup):
    def __init__(self, parent):
        super().__init__(parent)
        
        self.suca = QGraphicsEllipseItem()

        self.suca.setRect(QRect(-10, -10, 20, 20))
        self.suca.setBrush(QColor.fromRgb(0, 30, 200))
        self.suca.setPen(QColor.fromRgb(0, 30, 190))

        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

        self.addToGroup(self.suca)

        self.changed = lambda pos: None

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.changed(self.pos())

        return super().itemChange(change, value)
    
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
    
    def row_y(self, left, top, right, bottom):
        vertical_scale = (bottom - top) / self.reference_width
        y = top + vertical_scale * self.top_margin
        for _ in range(self.rows):
            yield y
            y += vertical_scale * self.rows_spacing

    def column_x(self, left, top, right, bottom):
        horizontal_scale = (right - left) / self.reference_width
        x = left + horizontal_scale * self.left_margin
        
        for _ in range(self.columns):
            yield x
            x += horizontal_scale * self.columns_spacing

    def row_lines(self, left, top, right, bottom):
        return ((left, y, right, y) 
            for y in self.row_y(left, top, right, bottom))

    def column_lines(self, left, top, right, bottom):
        return ((x, top, x, bottom) 
            for x in self.column_x(left, top, right, bottom))

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

class Card(QGraphicsItemGroup):
    rows_lines = [QGraphicsLineItem]
    card_format = CardFormat
    image: QImage

    def __init__(self, parent, card_format, image, set_data):
        super().__init__(parent)
        self.top = 0
        self.right = 0
        self.bottom = 0
        self.left = 0

        self.image = image
        self.card_format = card_format
        self.rows_lines = []
        self.rect = QGraphicsRectItem()
        self.rect.setPen(QColor(0, 0, 255))

        self.addToGroup(self.rect)

        self.set_data = set_data
    
    def update(self):
        rect = QRect(self.left, self.top, self.right - self.left, self.bottom - self.top)
        self.rect.setRect(rect)

        for line in self.rows_lines:
            line.scene().removeItem(line)

        self.rows_lines = []

        row_lines = self.card_format.row_lines(self.left, self.top, self.right, self.bottom)
        for x1, y1, x2, y2 in row_lines:
            line = QLineF(QPoint(x1, y1), QPoint(x2, y2))
            line_item = QGraphicsLineItem()
            line_item.setLine(line)
            line_item.setPen(QColor(255, 0, 255))
            self.addToGroup(line_item)
            self.rows_lines.append(line_item)
        
        column_lines = self.card_format.column_lines(self.left, self.top, self.right, self.bottom)
        for x1, y1, x2, y2 in column_lines:
            line = QLineF(QPoint(x1, y1), QPoint(x2, y2))
            line_item = QGraphicsLineItem()
            line_item.setLine(line)
            line_item.setPen(QColor(0, 255, 255))
            self.addToGroup(line_item)
            self.rows_lines.append(line_item)
        
        xs = list(self.card_format.column_x(self.left, self.top, self.right, self.bottom))
        ys = list(self.card_format.row_y(self.left, self.top, self.right, self.bottom))

        data = []

        for x in xs:
            column = []
            data.append(column)

            for y in ys:
                color = self.image.pixel(x, y)
                r, g, b, _ = QColor(color).getRgbF()
                gray = (r + g + b) / 3

                dot = QGraphicsEllipseItem(QRect(-2 + x, -4 + y, 4, 8))
                one = gray < self.card_format.threshold

                column.append(one)

                if one:
                    dot.setPen(QColor(255, 255, 255))
                    dot.setBrush(QColor(0, 0, 0))
                else:
                    dot.setPen(QColor(0, 0, 0))
                    dot.setBrush(QColor(255, 255, 255))
                
                self.addToGroup(dot)
                self.rows_lines.append(dot)
        
        # move the data thresholding etc out of the ui
        self.set_data(data)

class MainWindow(QMainWindow):
    """An Application example to draw using a pen """

    def __init__(self, parent=None):
        QMainWindow.__init__(self, parent)

        self.card_format = deepcopy(test_format)

        self.scene = QGraphicsScene()
        self.scene_widget = ZoomableGraphicsView(self.scene)

        self.bar = self.make_toolbar()
        
        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(font)

        panel_group = QGroupBox("Card format")
        panel_group.setFlat(True)
        panel_layout = QFormLayout()

        minimum_spin_size = 100

        self.columns_edit = QSpinBox()
        self.columns_edit.setValue(self.card_format.columns)
        self.columns_edit.setMinimumWidth(minimum_spin_size)
        self.columns_edit.valueChanged.connect(self.update_columns)
        panel_layout.addRow("Columns", self.columns_edit)

        self.rows_edit = QSpinBox()
        self.rows_edit.setMinimumWidth(minimum_spin_size)
        self.rows_edit.setValue(self.card_format.rows)
        self.rows_edit.valueChanged.connect(self.update_rows)
        panel_layout.addRow("Rows", self.rows_edit)

        self.reference_width_edit = QDoubleSpinBox()
        self.reference_width_edit.setSingleStep(0.01)
        self.reference_width_edit.setMinimumWidth(minimum_spin_size)
        self.reference_width_edit.setValue(self.card_format.reference_width)
        self.reference_width_edit.valueChanged.connect(self.update_reference_width)
        panel_layout.addRow("Reference width", self.reference_width_edit)

        self.top_margin_edit = QDoubleSpinBox() 
        self.top_margin_edit.setSingleStep(0.01)
        self.top_margin_edit.setMinimumWidth(minimum_spin_size)
        self.top_margin_edit.setValue(self.card_format.top_margin)
        self.top_margin_edit.valueChanged.connect(self.update_top_margin)
        panel_layout.addRow("Top Margin", self.top_margin_edit)

        self.left_margin_edit = QDoubleSpinBox() 
        self.left_margin_edit.setSingleStep(0.01)
        self.left_margin_edit.setMinimumWidth(minimum_spin_size)
        self.left_margin_edit.setValue(self.card_format.left_margin)
        self.left_margin_edit.valueChanged.connect(self.update_left_margin)
        panel_layout.addRow("Left Margin", self.left_margin_edit)

        self.rows_spacing_edit = QDoubleSpinBox() 
        self.rows_spacing_edit.setSingleStep(0.01)
        self.rows_spacing_edit.setMinimumWidth(minimum_spin_size)
        self.rows_spacing_edit.setValue(self.card_format.rows_spacing)
        self.rows_spacing_edit.valueChanged.connect(self.update_rows_spacing)
        panel_layout.addRow("Rows Spacing", self.rows_spacing_edit)

        self.columns_spacing_edit = QDoubleSpinBox() 
        self.columns_spacing_edit.setSingleStep(0.01)
        self.columns_spacing_edit.setDecimals(3)
        self.columns_spacing_edit.setMinimumWidth(minimum_spin_size)
        self.columns_spacing_edit.setValue(self.card_format.columns_spacing)
        self.columns_spacing_edit.valueChanged.connect(self.update_columns_spacing)
        panel_layout.addRow("Columns Spacing", self.columns_spacing_edit)
        
        self.threshold_edit = QDoubleSpinBox() 
        self.threshold_edit.setSingleStep(0.01)
        self.threshold_edit.setMinimumWidth(minimum_spin_size)
        self.threshold_edit.setValue(self.card_format.threshold)
        self.threshold_edit.valueChanged.connect(self.update_threshold)
        panel_layout.addRow("Threshold", self.threshold_edit)

        panel_group.setLayout(panel_layout)

        hor_split = QSplitter(Qt.Horizontal)
        hor_split.addWidget(self.scene_widget)
        hor_split.addWidget(panel_group)

        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        font.setPointSize(12)
        font.setWeight(QFont.Bold)
        
        self.text_label = QLabel()
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setContentsMargins(10, 10, 10, 10)
        self.text_label.setText('•' * self.card_format.columns)
        self.text_label.setFont(font)

        split = QSplitter(Qt.Vertical)
        split.addWidget(self.text_label)
        split.addWidget(hor_split)
        split.addWidget(self.text_edit)

        self.setCentralWidget(split)

        self.color = Qt.black
        self.set_color(self.color)

        self.sample = QImage("examples/foto.png")
        self.sample_pixmap = QPixmap(self.sample)
        self.sample_item = self.scene.addPixmap(self.sample_pixmap)

        self.suca = Dot(None)
        self.suca.changed = self.sucachanged
        self.scene.addItem(self.suca)

        self.suca1 = Dot(None)
        self.suca1.changed = self.suca1changed
        self.scene.addItem(self.suca1)

        self.line = self.scene.addLine(0, 0, 0, 0, QColor(0, 255, 0))

        self.card_item = Card(None, self.card_format, self.sample, self.got_card_data)
        self.scene.addItem(self.card_item)


    def sucachanged(self, pos: QPointF):
        line = self.line.line()
        line.setP1(pos.toPoint())
        self.line.setLine(line)
        self.card_item.left = pos.x()
        self.card_item.top = pos.y()
        self.card_item.update()

    def suca1changed(self, pos):
        line = self.line.line()
        line.setP2(pos.toPoint())
        self.line.setLine(line)
        self.card_item.right = pos.x()
        self.card_item.bottom = pos.y()
        self.card_item.update()

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

    def update_columns(self):
        self.card_format.columns = self.columns_edit.value()
        self.card_item.update()

    def update_rows(self):
        self.card_format.rows = self.rows_edit.value()
        self.card_item.update()
        
    def update_reference_width(self):
        self.card_format.reference_width = self.reference_width_edit.value()
        self.card_item.update()        

    def update_top_margin(self):
        self.card_format.top_margin = self.top_margin_edit.value()
        self.card_item.update()

    def update_left_margin(self):
        self.card_format.left_margin = self.left_margin_edit.value()
        self.card_item.update()

    def update_rows_spacing(self):
        self.card_format.rows_spacing = self.rows_spacing_edit.value()
        self.card_item.update()

    def update_columns_spacing(self):
        self.card_format.columns_spacing = self.columns_spacing_edit.value()
        self.card_item.update()
        
    def update_threshold(self):
        self.card_format.threshold = self.threshold_edit.value()
        self.card_item.update()

    def got_card_data(self, data):
        h1 = ' ' + '_' * self.card_format.columns  
        h2 = '/' + ' ' * self.card_format.columns + '|' 

        lines = [h1, h2]

        for y in range(self.card_format.rows):
            line = ['|']

            for x in range(self.card_format.columns):
                bit_str = lambda x: '0' if x else '.'

                dot = data[x][y]
                line.append(bit_str(dot))

            line.append('|')
            lines.append("".join(line))

        lines.append('`' + '-' * self.card_format.columns)

        txt = "\n".join(lines)
        self.text_edit.setText(txt)
        
        word = ''

        for x in range(self.card_format.columns):
            code_key = []
            for y in range(self.card_format.rows):
                key_str = lambda x: 'O' if x else ' '
                dot = data[x][y]
                code_key.append(key_str(dot))

            code_key = tuple(code_key)
            word += translate.get(code_key, '•')

        self.text_label.setText(word)

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


