"""Quiet native desktop styling for the personal dictionary."""

STYLE = """
QWidget { color: #252b2b; font-family: 'Segoe UI Variable', 'Segoe UI', 'Microsoft YaHei UI'; font-size: 13px; }
QWidget#appCanvas { background: #f5f5f7; }
QFrame#sidebar { background: #ffffff; border-left: 1px solid #e7e8e9; }
QFrame#inputShell { background: #ffffff; border: 1px solid #e1e4e3; border-radius: 23px; }
QFrame#card, QFrame#suggestion, QFrame#imageCard {
    background: #ffffff; border: 1px solid #e5e8e6; border-radius: 14px;
}
QFrame#suggestion:hover, QFrame#imageCard:hover { border-color: #b8c3be; }
QFrame#toolbar { background: #f5f6f4; border: 1px solid #e8ebe8; border-radius: 12px; }
QLabel#brand { color: #222b29; font-size: 19px; font-weight: 650; }
QLabel#eyebrow { color: #78817d; font-size: 11px; font-weight: 600; letter-spacing: 1px; }
QLabel#pageTitle { color: #212928; font-size: 27px; font-weight: 650; }
QLabel#sectionTitle { color: #2b3431; font-size: 19px; font-weight: 600; }
QLabel#muted, QLabel#status { color: #7c8581; font-size: 12px; }
QLabel#badge { color: #52665d; background: #eef2ee; border-radius: 9px; padding: 5px 10px; }
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit {
    background: #ffffff; border: 1px solid #dfe4df; border-radius: 10px;
    padding: 8px 10px; selection-background-color: #ccddd3;
}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus { border: 1px solid #8ba79a; }
QPlainTextEdit#topicInput {
    border: 0; background: transparent; padding: 7px 6px; color: #26302e;
    font-size: 17px; selection-background-color: #d3e3d9;
}
QLineEdit#readerTitle { border: 0; background: transparent; padding: 3px 0;
    font-size: 29px; font-weight: 650; color: #222b29; }
QLineEdit#readerTitle:focus { border-bottom: 1px solid #aabcb1; }
QTextEdit#articleEditor { border: 0; background: #ffffff; padding: 17px 20px;
    font-family: Georgia, 'Times New Roman'; font-size: 16px; line-height: 150%; }
QPushButton, QToolButton {
    background: #f7f8f6; color: #303a36; border: 1px solid #e0e5e0;
    border-radius: 10px; padding: 8px 13px; font-weight: 550;
}
QPushButton:hover, QToolButton:hover { background: #edf1ed; border-color: #cbd5ce; }
QPushButton:pressed, QToolButton:pressed { background: #e2e9e3; }
QPushButton:disabled, QToolButton:disabled { color: #9ba39e; background: #f4f5f3; }
QPushButton#primary { color: #ffffff; background: #303b36; border: 1px solid #303b36; }
QPushButton#primary:hover { background: #1e2924; }
QPushButton#danger { color: #a04747; background: #fff8f6; border-color: #efd5d2; }
QPushButton#yellowPen { background: #fff2aa; border-color: #ecd771; color: #5c5525; }
QPushButton#redPen { background: #fbe6e2; border-color: #e9b8b0; color: #a04747; }
QToolButton#chromeIcon { background: transparent; border: 0; border-radius: 12px; padding: 0; }
QToolButton#chromeIcon:hover { background: #ecefeb; }
QToolButton#composerIcon { background: transparent; border: 0; border-radius: 12px; padding: 0; }
QToolButton#composerIcon:hover { background: #edf0ed; }
QToolButton#composerIcon[recording="true"] { background: #fce9e8; }
QToolButton#exploreIcon { background: #303b36; border: 0; border-radius: 18px; padding: 0; }
QToolButton#exploreIcon:hover { background: #1e2924; }
QToolButton#exploreIcon:disabled { background: #bfc7c1; }
QToolButton#addIcon { background: rgba(255, 255, 255, 180); border: 1px solid #cbd6cf; border-radius: 22px; padding: 0; }
QToolButton#addIcon:hover { background: #e6eee8; border-color: #9eafa3; }
QToolButton#resultPen { background: rgba(255, 255, 255, 218); border: 1px solid #e3e8e3; border-radius: 13px; padding: 0; }
QToolButton#resultPen:hover { background: #f4f7f3; border-color: #b9c9bd; }
QToolButton#resultPen:checked { background: #eaf2ec; border: 2px solid #84a794; }
QToolButton#resultPen[penMode="yellow"]:checked { background: #fff3bd; border-color: #dbbd65; }
QToolButton#resultPen[penMode="red"]:checked { background: #f9e4e3; border-color: #d39b9c; }
QTextEdit#paintableFact { font-family: Georgia, 'Times New Roman'; font-size: 15px; line-height: 145%; }
QMenu { background: #ffffff; border: 1px solid #dfe6df; border-radius: 12px; padding: 9px; }
QMenu::item { padding: 7px 12px; border-radius: 7px; }
QMenu::item:selected { background: #edf2ed; }
QTreeWidget { background: transparent; border: 0; outline: 0; font-size: 12px; }
QTreeWidget::item { padding: 6px 3px; border-radius: 7px; }
QTreeWidget::item:selected { background: #e7ede8; color: #25312b; }
QTreeWidget::item:hover { background: #f1f4f1; }
QScrollArea { border: 0; background: transparent; }
QWidget#researchContent { background: transparent; }
QScrollBar:vertical { background: transparent; width: 9px; margin: 2px; }
QScrollBar::handle:vertical { background: #cbd2cb; border-radius: 4px; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; }
"""
