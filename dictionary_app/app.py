"""Little Atlas: a local, curated personal dictionary desktop UI."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from html import escape
from pathlib import Path
import sys
from typing import Callable
from urllib.parse import quote, urlsplit

from PySide6.QtCore import QObject, QRect, QSize, QThread, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
    QGraphicsDropShadowEffect, QScrollArea, QStackedWidget, QTextEdit,
    QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .ai_research import research_topic_ai
from .paintable import PaintableFact
from .research import ImageCandidate, ResearchResult, download_image, research_topic
from .siwc import SIWCClient, SIWCError
from .storage import DictionaryStore, Entry, ImageRecord
from .theme import STYLE
from .webpage_research import research_webpage


CATEGORIES = (
    "Nature & Life", "Human Body & Health", "History & Society",
    "Language & Literature", "Myths & Beliefs", "Science & Technology",
    "Arts & Culture", "Earth & Space", "People & Places",
    "Everyday Life", "Unsorted",
)


def asset_path(name: str) -> Path:
    """Find an asset from source or a PyInstaller one-directory bundle."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    if getattr(sys, "_MEIPASS", None):
        return base / "dictionary_app" / "assets" / name
    return Path(__file__).resolve().parent / "assets" / name


def label(text: str, object_name: str = "", wrap: bool = False) -> QLabel:
    result = QLabel(text)
    if object_name:
        result.setObjectName(object_name)
    result.setWordWrap(wrap)
    return result


def clear_layout(layout: QVBoxLayout | QHBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())
            item.layout().deleteLater()


def is_https_url(value: str) -> bool:
    try:
        return urlsplit(value).scheme.lower() == "https"
    except ValueError:
        return False


class Job(QObject):
    result = Signal(object)
    error = Signal(str)
    done = Signal()

    def __init__(self, action: Callable[[], object]) -> None:
        super().__init__()
        self.action = action

    @Slot()
    def run(self) -> None:
        try:
            self.result.emit(self.action())
        except Exception as exc:
            self.error.emit(str(exc) or type(exc).__name__)
        finally:
            self.done.emit()


class VoiceSignals(QObject):
    progress = Signal(str)
    level = Signal(float)


def icon(name: str, color: str = "#35403d") -> QIcon:
    """Small device-independent line icons for the compact native controls."""
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(2, 2)
    painter.setPen(QPen(QColor(color), 1.8, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if name == "menu":
        for y in (6, 12, 18):
            painter.drawLine(4, y, 20, y)
    elif name == "close":
        painter.drawLine(6, 6, 18, 18)
        painter.drawLine(18, 6, 6, 18)
    elif name == "mic":
        painter.drawRoundedRect(QRect(9, 3, 6, 12), 3, 3)
        painter.drawArc(QRect(6, 7, 12, 12), 180 * 16, 180 * 16)
        painter.drawLine(12, 19, 12, 22)
        painter.drawLine(9, 22, 15, 22)
    elif name == "stop":
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(QRect(7, 7, 10, 10), 2, 2)
    elif name == "search":
        painter.drawEllipse(QRect(4, 4, 12, 12))
        painter.drawLine(14, 14, 20, 20)
    elif name == "plus":
        painter.drawLine(12, 4, 12, 20)
        painter.drawLine(4, 12, 20, 12)
    elif name == "style":
        painter.drawEllipse(QRect(3, 3, 18, 18))
        for x, y in ((8, 8), (15, 7), (17, 13), (9, 16)):
            painter.setBrush(QColor(color))
            painter.drawEllipse(QRect(x, y, 2, 2))
    elif name == "pen":
        painter.drawLine(6, 18, 17, 7)
        painter.drawLine(8, 20, 19, 9)
        painter.drawLine(17, 7, 19, 9)
        painter.setBrush(QColor(color))
        painter.drawEllipse(QRect(4, 19, 4, 3))
    painter.end()
    return QIcon(pixmap)


class ComposerInput(QPlainTextEdit):
    submitted = Signal()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.submitted.emit()
            return
        super().keyPressEvent(event)


class ImageChoice(QFrame):
    def __init__(self, candidate: ImageCandidate) -> None:
        super().__init__()
        self.candidate = candidate
        self.setObjectName("imageCard")
        self.setFixedWidth(188)
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(7)
        self.preview = QLabel("Loading image…")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedHeight(105)
        self.preview.setStyleSheet("background:#f1f4ed; border-radius:8px; color:#8a9a8d;")
        root.addWidget(self.preview)
        self.check = QCheckBox("Add to entry")
        root.addWidget(self.check)
        title = label(candidate.title.removeprefix("File:")[:50], "", True)
        title.setMaximumHeight(35)
        root.addWidget(title)
        credit = label((candidate.license or "See license")[:35], "muted")
        credit.setToolTip(candidate.attribution or candidate.license)
        root.addWidget(credit)
        source = QPushButton("Image source ↗")
        source.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(candidate.description_url)))
        root.addWidget(source)
        root.addStretch()

    def set_image(self, data: bytes) -> None:
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self.preview.setPixmap(pixmap.scaled(165, 105, Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation))
            self.preview.setText("")
        else:
            self.preview.setText("Preview unavailable")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.store = DictionaryStore()
        try:
            self.chatgpt = SIWCClient(self.store.data_dir)
            self.chatgpt_error = ""
        except SIWCError as exc:
            self.chatgpt = None
            self.chatgpt_error = str(exc)
        self.pending_search: tuple[str, str] | None = None
        self.result: ResearchResult | None = None
        self.current_entry: Entry | None = None
        self.target_entry_id: int | None = None
        self.fact_widgets: list[tuple[PaintableFact, str]] = []
        self.current_pen = "select"
        self.image_choices: list[ImageChoice] = []
        self.jobs: list[tuple[QThread, Job]] = []
        self.voice_recorder = None
        self.voice_signals = VoiceSignals()
        self.voice_signals.progress.connect(self._set_status)
        self.voice_signals.level.connect(self._show_voice_level)
        self.network = QNetworkAccessManager(self)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(850)
        self.save_timer.timeout.connect(self._save_reader)
        self._loading_reader = False
        self._closing = False
        self.setWindowTitle("Little Atlas · Personal Dictionary")
        self.setWindowIcon(QIcon(str(asset_path("little-atlas.png"))))
        self.setMinimumSize(800, 225)
        self.resize(800, 232)
        self._make_ui()
        self._refresh_catalog()
        self._show_home()

    def _make_ui(self) -> None:
        root = QWidget()
        root.setObjectName("appCanvas")
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        body = QWidget()
        root_layout.addWidget(body, 1)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(22, 16, 22, 16)
        body_layout.setSpacing(0)
        self.pages = QStackedWidget()
        body_layout.addWidget(self.pages, 1)
        self.home_page = self._make_home_page()
        self.reader_page = self._make_reader_page()
        self.chapter_page = self._make_chapter_page()
        self.pages.addWidget(self.home_page)
        self.pages.addWidget(self.reader_page)
        self.pages.addWidget(self.chapter_page)
        self.status = label("", "status")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.hide()
        body_layout.addWidget(self.status)
        self.status_timer = QTimer(self)
        self.status_timer.setSingleShot(True)
        self.status_timer.timeout.connect(self.status.hide)

        self.sidebar = QFrame(root)
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(280)
        left = QVBoxLayout(self.sidebar)
        left.setContentsMargins(23, 24, 23, 22)
        left.setSpacing(14)
        drawer_top = QHBoxLayout()
        drawer_top.addWidget(label("Contents", "brand"))
        drawer_top.addStretch()
        close_menu = QToolButton()
        close_menu.setObjectName("chromeIcon")
        close_menu.setIcon(icon("close"))
        close_menu.setIconSize(QSize(18, 18))
        close_menu.setFixedSize(38, 38)
        close_menu.setToolTip("Close contents")
        close_menu.setAccessibleName("Close contents")
        close_menu.clicked.connect(self._close_menu)
        drawer_top.addWidget(close_menu)
        left.addLayout(drawer_top)
        self.catalog = QTreeWidget()
        self.catalog.setHeaderHidden(True)
        self.catalog.setIndentation(13)
        self.catalog.itemClicked.connect(self._catalog_clicked)
        left.addWidget(self.catalog, 1)
        self.sidebar.hide()
        self.menu_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.menu_shortcut.activated.connect(self._close_menu)
        self.contents_shortcut = QShortcut(QKeySequence("Ctrl+B"), self)
        self.contents_shortcut.activated.connect(self._toggle_menu)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if hasattr(self, "sidebar"):
            self._place_sidebar()

    def _place_sidebar(self) -> None:
        root = self.centralWidget()
        self.sidebar.setGeometry(root.width() - self.sidebar.width(), 0,
                                 self.sidebar.width(), root.height())

    def _toggle_menu(self) -> None:
        if self.sidebar.isHidden():
            self._place_sidebar()
            self.sidebar.show()
            self.sidebar.raise_()
            self.catalog.setFocus()
        else:
            self._close_menu()

    def _close_menu(self) -> None:
        if not self.sidebar.isHidden():
            self.sidebar.hide()
            if self.pages.currentWidget() is self.home_page:
                self.topic_input.setFocus()

    def _make_home_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.home_top_space = QWidget()
        layout.addWidget(self.home_top_space, 2)
        centered = QHBoxLayout()
        centered.addStretch(1)
        self.input_shell = QFrame()
        self.input_shell.setObjectName("inputShell")
        self.input_shell.setFixedSize(740, 176)
        shadow = QGraphicsDropShadowEffect(self.input_shell)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(29, 35, 32, 20))
        self.input_shell.setGraphicsEffect(shadow)
        shell_layout = QVBoxLayout(self.input_shell)
        shell_layout.setContentsMargins(20, 14, 20, 13)
        shell_layout.setSpacing(5)
        self.topic_input = ComposerInput()
        self.topic_input.setObjectName("topicInput")
        self.topic_input.setPlaceholderText("Search a topic or write what you learned…")
        self.topic_input.setFixedHeight(100)
        self.topic_input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.topic_input.submitted.connect(self._explore)
        shell_layout.addWidget(self.topic_input, 1)
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(4)
        self.mic_button = QToolButton()
        self.mic_button.setObjectName("composerIcon")
        self.mic_button.setIcon(icon("mic"))
        self.mic_button.setIconSize(QSize(20, 20))
        self.mic_button.setFixedSize(44, 44)
        self.mic_button.setToolTip("Dictate in Chinese or English")
        self.mic_button.setAccessibleName("Dictate")
        self.mic_button.clicked.connect(self._toggle_voice)
        self.voice_menu = QMenu(self.mic_button)
        self.voice_menu.addAction("Dictate in Chinese", lambda: self._start_voice("zh"))
        self.voice_menu.addAction("Dictate in English", lambda: self._start_voice("en"))
        controls.addWidget(self.mic_button)
        controls.addStretch()
        self.explore_button = QToolButton()
        self.explore_button.setObjectName("exploreIcon")
        self.explore_button.setIcon(icon("search", "#ffffff"))
        self.explore_button.setIconSize(QSize(20, 20))
        self.explore_button.setFixedSize(44, 44)
        self.explore_button.setToolTip("Search English sources")
        self.explore_button.setAccessibleName("Search English sources")
        self.explore_button.clicked.connect(self._explore)
        self.explore_button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.explore_button.customContextMenuRequested.connect(self._show_search_options)
        controls.addWidget(self.explore_button)
        self.plus_button = QToolButton()
        self.plus_button.setObjectName("addIcon")
        self.plus_button.setIcon(icon("plus"))
        self.plus_button.setIconSize(QSize(20, 20))
        self.plus_button.setFixedSize(44, 44)
        self.plus_button.setToolTip("Add an English entry")
        self.plus_button.setAccessibleName("Add an English entry")
        self.plus_button.clicked.connect(self._add_current)
        controls.addWidget(self.plus_button)
        shell_layout.addLayout(controls)
        centered.addWidget(self.input_shell)
        centered.addStretch(1)
        layout.addLayout(centered)

        self.research_scroll = QScrollArea()
        self.research_scroll.setWidgetResizable(True)
        research_content = QWidget()
        research_content.setObjectName("researchContent")
        research_content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.research_layout = QVBoxLayout(research_content)
        self.research_layout.setContentsMargins(1, 4, 10, 5)
        self.research_layout.setSpacing(13)
        self.research_layout.addStretch()
        self.research_scroll.setWidget(research_content)
        self.research_scroll.viewport().setAutoFillBackground(False)
        self.research_scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.research_scroll.hide()
        layout.addWidget(self.research_scroll, 1)
        self.home_bottom_space = QWidget()
        layout.addWidget(self.home_bottom_space, 3)
        return page

    def _make_reader_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        heading = QHBoxLayout()
        back = QPushButton("← Contents")
        back.clicked.connect(self._show_home)
        heading.addWidget(back)
        heading.addStretch()
        extend = QPushButton("＋ Find more")
        extend.clicked.connect(self._extend_entry)
        heading.addWidget(extend)
        delete = QPushButton("Delete entry")
        delete.setObjectName("danger")
        delete.clicked.connect(self._delete_entry)
        heading.addWidget(delete)
        layout.addLayout(heading)
        self.reader_title = QLineEdit()
        self.reader_title.setObjectName("readerTitle")
        self.reader_title.setPlaceholderText("English title")
        self.reader_title.setMinimumHeight(52)
        self.reader_title.textChanged.connect(self._queue_save)
        layout.addWidget(self.reader_title)
        metadata = QHBoxLayout()
        self.reader_category = QComboBox()
        self.reader_category.addItems(CATEGORIES)
        self.reader_category.currentTextChanged.connect(self._queue_save)
        metadata.addWidget(self.reader_category)
        self.reader_subcategory = QLineEdit()
        self.reader_subcategory.setPlaceholderText("Subchapter")
        self.reader_subcategory.textChanged.connect(self._queue_save)
        metadata.addWidget(self.reader_subcategory, 1)
        self.source_button = QPushButton("Open source ↗")
        self.source_button.clicked.connect(self._open_source)
        metadata.addWidget(self.source_button)
        layout.addLayout(metadata)
        self.original_button = QPushButton("View original input")
        self.original_button.clicked.connect(lambda: self.original_note.setVisible(not self.original_note.isVisible()))
        layout.addWidget(self.original_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.original_note = label("", "muted", True)
        self.original_note.hide()
        layout.addWidget(self.original_note)

        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        tools = QHBoxLayout(toolbar)
        tools.setContentsMargins(9, 7, 9, 7)
        tools.addWidget(label("Select text to mark:", "muted"))
        yellow = QPushButton("Highlight")
        yellow.setObjectName("yellowPen")
        yellow.clicked.connect(lambda: self._mark_text("yellow"))
        tools.addWidget(yellow)
        red = QPushButton("Red pen")
        red.setObjectName("redPen")
        red.clicked.connect(lambda: self._mark_text("red"))
        tools.addWidget(red)
        clear = QPushButton("Clear marks")
        clear.clicked.connect(lambda: self._mark_text("clear"))
        tools.addWidget(clear)
        tools.addStretch()
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.clicked.connect(self._save_reader)
        tools.addWidget(save)
        layout.addWidget(toolbar)
        self.article_editor = QTextEdit()
        self.article_editor.setObjectName("articleEditor")
        self.article_editor.setAcceptRichText(True)
        self.article_editor.textChanged.connect(self._queue_save)
        layout.addWidget(self.article_editor, 1)
        self.image_scroller = QScrollArea()
        self.image_scroller.setWidgetResizable(True)
        self.image_scroller.setFixedHeight(164)
        self.image_content = QWidget()
        self.image_layout = QHBoxLayout(self.image_content)
        self.image_layout.setContentsMargins(1, 5, 1, 5)
        self.image_layout.setSpacing(12)
        self.image_scroller.setWidget(self.image_content)
        layout.addWidget(self.image_scroller)
        return page

    def _make_chapter_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.chapter_title = label("", "pageTitle")
        layout.addWidget(self.chapter_title)
        self.chapter_subtitle = label("", "muted")
        layout.addWidget(self.chapter_subtitle)
        self.chapter_scroll = QScrollArea()
        self.chapter_scroll.setWidgetResizable(True)
        content = QWidget()
        self.chapter_items = QVBoxLayout(content)
        self.chapter_items.setContentsMargins(2, 4, 12, 4)
        self.chapter_items.setSpacing(9)
        self.chapter_scroll.setWidget(content)
        layout.addWidget(self.chapter_scroll, 1)
        return page

    def _run_job(self, action: Callable[[], object], on_result: Callable[[object], None],
                 on_error: Callable[[str], None] | None = None) -> None:
        thread = QThread(self)
        job = Job(action)
        job.moveToThread(thread)
        thread.started.connect(job.run)
        job.result.connect(on_result)
        job.error.connect(on_error or self._show_error)
        job.done.connect(thread.quit)
        job.done.connect(job.deleteLater)
        thread.finished.connect(thread.deleteLater)
        pair = (thread, job)
        self.jobs.append(pair)
        thread.finished.connect(lambda: self.jobs.remove(pair) if pair in self.jobs else None)
        thread.start()

    def _set_status(self, message: str) -> None:
        self.status.setText(message)
        self.status.setVisible(bool(message))
        if message:
            self.status_timer.start(7000)

    def _show_error(self, message: str) -> None:
        self._set_status(message)
        QMessageBox.warning(self, "Little Atlas", message)

    def _show_home(self) -> None:
        self._save_reader()
        self.result = None
        self.research_scroll.hide()
        self.input_shell.setFixedHeight(176)
        self.topic_input.setFixedHeight(100)
        self.home_top_space.show()
        self.home_bottom_space.show()
        self.home_page.layout().setContentsMargins(0, 0, 0, 0)
        self.plus_button.setToolTip("Add an English entry")
        self.plus_button.setAccessibleName("Add an English entry")
        self.pages.setCurrentWidget(self.home_page)
        self._close_menu()
        self.setMinimumSize(800, 225)
        if not self.isMaximized():
            self.resize(800, 232)
        self.topic_input.setFocus()

    def _show_research_window(self) -> None:
        self.setMinimumSize(800, 490)
        if not self.isMaximized() and self.height() < 650:
            self.resize(900, 690)

    def _new_entry(self) -> None:
        self.target_entry_id = None
        self.topic_input.clear()
        self._show_home()

    def _explore(self) -> None:
        text = self.topic_input.toPlainText().strip()
        if not text:
            self._show_error("Enter a topic or use the microphone first.")
            return
        self.explore_button.setEnabled(False)
        existing = self.store.get_entry(self.target_entry_id) if self.target_entry_id else None
        exclude_text = existing.body_html if existing else ""
        if not is_https_url(text):
            self._open_google(text)
        self._start_lookup(text, exclude_text)

    def _open_google(self, text: str) -> None:
        QDesktopServices.openUrl(QUrl("https://www.google.com/search?q=" + quote(text[:350], safe="")))

    def _show_search_options(self, point) -> None:
        menu = QMenu(self)
        google = menu.addAction("Search on Google")
        contents = menu.addAction("Contents  ·  Ctrl+B")
        ai = menu.addAction("ChatGPT research · optional") if self.chatgpt is not None else None
        chosen = menu.exec(self.explore_button.mapToGlobal(point))
        if chosen is google:
            self._open_google(self.topic_input.toPlainText().strip())
        elif chosen is contents:
            self._toggle_menu()
        elif chosen is ai:
            self._start_optional_ai()

    def _start_optional_ai(self) -> None:
        text = self.topic_input.toPlainText().strip()
        if not text:
            self._show_error("Enter a topic first.")
            return
        if self.chatgpt is None:
            self._set_status(self.chatgpt_error or "ChatGPT is unavailable on this device.")
            return
        existing = self.store.get_entry(self.target_entry_id) if self.target_entry_id else None
        exclude_text = existing.body_html if existing else ""
        try:
            connected = self.chatgpt.is_signed_in()
        except SIWCError as exc:
            self._set_status(str(exc))
            return
        if connected:
            self._start_lookup(text, exclude_text, prefer_ai=True)
        else:
            self.pending_search = (text, exclude_text)
            self._begin_sign_in()

    def _begin_sign_in(self) -> None:
        if self.chatgpt is None:
            self.explore_button.setEnabled(True)
            self._set_status(self.chatgpt_error or "Could not connect to ChatGPT.")
            return
        self.explore_button.setEnabled(False)
        self._set_status("Finish signing in with ChatGPT in your browser. Search will resume automatically.")
        self._run_job(self.chatgpt.sign_in, self._signed_in, self._sign_in_failed)

    def _signed_in(self, _profile: object) -> None:
        self.chatgpt_error = ""
        pending = self.pending_search
        self.pending_search = None
        if pending:
            self._start_lookup(*pending, prefer_ai=True)
        else:
            self.explore_button.setEnabled(True)
            self._set_status("ChatGPT connected. Enter a topic to search.")

    def _sign_in_failed(self, message: str) -> None:
        pending = self.pending_search
        self.pending_search = None
        if pending:
            self._start_lookup(*pending, fallback_reason=message)
        else:
            self.explore_button.setEnabled(True)
            self._set_status(message)

    def _start_lookup(self, text: str, exclude_text: str,
                      *, fallback_reason: str = "", prefer_ai: bool = False) -> None:
        self.explore_button.setEnabled(False)
        self._set_status("Searching English sources and images…")

        def lookup() -> tuple[ResearchResult, str, str]:
            if is_https_url(text):
                return research_webpage(text), "Web page", ""
            ai_error = fallback_reason
            if prefer_ai and self.chatgpt is not None:
                try:
                    token = self.chatgpt.access_token()
                    answer = research_topic_ai(token, text, exclude_text=exclude_text)
                    if answer.suggestions:
                        return answer, "ChatGPT", ""
                    ai_error = answer.error
                except SIWCError as exc:
                    ai_error = str(exc)
            result = research_topic(text, exclude_text=exclude_text)
            return result, "Wikimedia", ai_error

        self._run_job(lookup, self._lookup_ready, self._research_failed)

    def _lookup_ready(self, payload: object) -> None:
        if not isinstance(payload, tuple) or len(payload) != 3:
            self._research_failed("Unexpected search result format.")
            return
        result, provider, ai_error = payload
        if isinstance(result, ResearchResult) and not result.suggestions and ai_error:
            result.error = f"ChatGPT: {ai_error}\nPublic sources: {result.error or 'No suitable result found.'}"
        self._research_ready(result)
        if isinstance(result, ResearchResult) and result.suggestions:
            if ai_error:
                self._set_status(f"ChatGPT unavailable ({ai_error}). Showing Wikimedia results; use the selection pen to choose what to save.")
            elif provider == "ChatGPT":
                self._set_status("Found sourced results. Drag the selection pen over what you want to save.")

    def _add_current(self) -> None:
        if self.result is not None and not self.research_scroll.isHidden():
            self._accept_results()
        else:
            self._manual_entry()

    def _research_failed(self, message: str) -> None:
        self.explore_button.setEnabled(True)
        self._show_error(f"Search failed: {message}\nCheck your connection or try a more specific topic.")

    def _research_ready(self, result: object) -> None:
        self.explore_button.setEnabled(True)
        self.result = result  # type: ignore[assignment]
        if not isinstance(self.result, ResearchResult):
            self._show_error("Unexpected search result format.")
            return
        if not self.result.suggestions:
            self._show_error((self.result.error or "No relevant English sources found.") +
                             "\nTry a more specific topic, or use + to write an entry.")
            return
        self._draw_results()
        self._set_status("Drag the selection pen across text to save it. Use yellow or red to mark key points, then click +.")

    def _draw_results(self) -> None:
        assert self.result is not None
        clear_layout(self.research_layout)
        self.fact_widgets.clear()
        self.image_choices.clear()
        self.pen_buttons: dict[str, QToolButton] = {}
        header = QHBoxLayout()
        heading = label(self.result.title, "pageTitle")
        header.addWidget(heading, 1)
        for mode, color, tip in (
            ("select", "#387765", "Selection pen: drag over text to save"),
            ("yellow", "#b58b2e", "Highlighter: mark key points"),
            ("red", "#b12c35", "Red pen: emphasize or annotate"),
        ):
            button = QToolButton()
            button.setObjectName("resultPen")
            button.setProperty("penMode", mode)
            button.setIcon(icon("pen", color))
            button.setIconSize(QSize(22, 22))
            button.setFixedSize(40, 40)
            button.setCheckable(True)
            button.setToolTip(tip)
            button.setAccessibleName(tip)
            button.clicked.connect(lambda _checked=False, selected=mode: self._choose_pen(selected))
            self.pen_buttons[mode] = button
            header.addWidget(button)
        self.research_layout.addLayout(header)
        self._choose_pen("select")
        if self.result.source_url:
            source = label(
                f'<a href="{escape(self.result.source_url, quote=True)}" '
                'style="color:#66736f;text-decoration:none;">Source ↗</a>', "muted")
            source.setOpenExternalLinks(True)
            self.research_layout.addWidget(source)
        classification = QHBoxLayout()
        self.proposed_category = QComboBox()
        self.proposed_category.addItems(CATEGORIES)
        index = self.proposed_category.findText(self.result.category)
        self.proposed_category.setCurrentIndex(max(index, 0))
        classification.addWidget(self.proposed_category)
        self.proposed_subcategory = QLineEdit(self.result.subcategory)
        self.proposed_subcategory.setPlaceholderText("Subchapter")
        classification.addWidget(self.proposed_subcategory, 1)
        self.research_layout.addLayout(classification)

        note_card = QFrame()
        note_card.setObjectName("card")
        note_layout = QVBoxLayout(note_card)
        note_layout.setContentsMargins(15, 12, 15, 12)
        note_layout.addWidget(label("My notes", "eyebrow"))
        self.english_note_input = QPlainTextEdit()
        self.english_note_input.setPlaceholderText("Write your own note in English…")
        self.english_note_input.setFixedHeight(60)
        note_layout.addWidget(self.english_note_input)
        self.research_layout.addWidget(note_card)

        self.research_layout.addWidget(label("Related English content", "eyebrow"))
        for suggestion in self.result.suggestions:
            card = QFrame()
            card.setObjectName("suggestion")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 10, 16, 10)
            card_layout.setSpacing(4)
            fact_header = QHBoxLayout()
            fact_header.addWidget(label(suggestion.title, "muted"))
            fact_header.addStretch()
            if suggestion.source_url and suggestion.source_url != self.result.source_url:
                citation = label(
                    f'<a href="{escape(suggestion.source_url, quote=True)}" '
                    'style="color:#66736f;text-decoration:none;">Source ↗</a>', "muted")
                citation.setOpenExternalLinks(True)
                fact_header.addWidget(citation)
            card_layout.addLayout(fact_header)
            paragraph = PaintableFact(suggestion.text)
            paragraph.set_pen(self.current_pen)
            paragraph.selection_changed.connect(self._update_selection_count)
            paragraph.setFixedHeight(max(50, min(190, 34 + ((len(suggestion.text) + 84) // 85) * 25)))
            card_layout.addWidget(paragraph)
            self.fact_widgets.append((paragraph, suggestion.source_url))
            self.research_layout.addWidget(card)

        if self.result.images:
            self.research_layout.addWidget(label("Related images", "eyebrow"))
            image_row = QHBoxLayout()
            image_row.setSpacing(10)
            for candidate in self.result.images:
                choice = ImageChoice(candidate)
                choice.check.toggled.connect(self._update_selection_count)
                image_row.addWidget(choice)
                self.image_choices.append(choice)
                self._load_thumb(choice)
            image_row.addStretch()
            self.research_layout.addLayout(image_row)
        else:
            self.research_layout.addWidget(label("No suitable images found. You can save the text alone.", "muted"))
        self.research_layout.addStretch()
        self.input_shell.setFixedHeight(176)
        self.topic_input.setFixedHeight(100)
        self.home_top_space.hide()
        self.home_bottom_space.hide()
        self.home_page.layout().setContentsMargins(0, 14, 0, 0)
        self.research_scroll.show()
        self._show_research_window()
        self.plus_button.setToolTip("Save selected content")
        self.plus_button.setAccessibleName("Save selected content")
        self._update_selection_count()

    def _choose_pen(self, mode: str) -> None:
        self.current_pen = mode
        for fact, _ in self.fact_widgets:
            fact.set_pen(mode)
        for name, button in self.pen_buttons.items():
            button.setChecked(name == mode)

    def _update_selection_count(self) -> None:
        facts = sum(len(fact.selected_segments()) for fact, _ in self.fact_widgets)
        self.plus_button.setToolTip(f"Save {facts} selected passage{'s' if facts != 1 else ''}")

    def _load_thumb(self, choice: ImageChoice) -> None:
        if not choice.candidate.thumb_url:
            choice.preview.setText("No preview")
            return
        request = QNetworkRequest(QUrl(choice.candidate.thumb_url))
        request.setRawHeader(b"User-Agent", b"LittleAtlas/0.1 (educational personal dictionary)")
        reply = self.network.get(request)

        def finished() -> None:
            if reply.error() == reply.NetworkError.NoError:
                choice.set_image(bytes(reply.readAll()))
            else:
                choice.preview.setText("Preview unavailable")
            reply.deleteLater()

        reply.finished.connect(finished)

    def _accept_results(self) -> None:
        if self.result is None:
            return
        selected = [(plain, marked_html, url)
                    for fact, url in self.fact_widgets
                    for plain, marked_html in fact.selected_segments()]
        own_note = self.english_note_input.toPlainText().strip()
        if not selected and not own_note:
            self._show_error("Use the selection pen to choose English text, or write your own note in English.")
            return
        body = ""
        if own_note:
            body += '<h3 style="color:#456b50;">My note</h3>'
            body += f'<p style="font-size:16px;line-height:1.6;">{escape(own_note).replace(chr(10), "<br/>")}</p>'
        body += "".join(
            f'<p style="font-size:16px;line-height:1.6;">{marked_html}</p>'
            for _, marked_html, _ in selected
        )
        urls = list(dict.fromkeys(url for _, _, url in selected if url))
        if urls:
            body += '<p style="font-size:12px;color:#728579;">Source: ' + " · ".join(
                f'<a href="{escape(url, quote=True)}">{escape(QUrl(url).host() or "Source")}</a>' for url in urls
            ) + "</p>"
        existing = self.store.get_entry(self.target_entry_id) if self.target_entry_id else None
        if existing and existing.title.casefold() != self.result.title.casefold():
            existing = None
        if existing is None:
            existing = next((e for e in self.store.list_entries()
                             if e.title.casefold() == self.result.title.casefold()), None)
        if existing:
            latest_input = self.topic_input.toPlainText().strip()
            originals = existing.original_input
            if latest_input and latest_input not in originals:
                originals += f"\n\n[{date.today().isoformat()}] {latest_input}"
            entry = replace(existing, body_html=self._append_html(existing.body_html, body),
                            original_input=originals,
                            category=self.proposed_category.currentText(),
                            subcategory=self.proposed_subcategory.text().strip())
        else:
            entry = Entry(title=self.result.title,
                          original_input=self.topic_input.toPlainText().strip(),
                          category=self.proposed_category.currentText(),
                          subcategory=self.proposed_subcategory.text().strip(),
                          body_html=body, source_url=self.result.source_url)
        saved = self.store.upsert_entry(entry)
        candidates = [choice.candidate for choice in self.image_choices if choice.check.isChecked()]
        self.target_entry_id = None
        self._refresh_catalog()
        self._open_entry(saved.id)
        if candidates:
            self._set_status("Entry saved. Saving selected images to your computer…")

            def save_images() -> int:
                count = 0
                for candidate in candidates:
                    try:
                        path = download_image(candidate, self.store.images_dir)
                        self.store.add_image(saved.id, path, source_url=candidate.description_url,
                                             attribution=candidate.attribution, license=candidate.license,
                                             caption=candidate.title.removeprefix("File:"))
                        count += 1
                    except Exception:
                        continue
                return count

            self._run_job(save_images, lambda count: self._images_saved(saved.id, int(count)))
        else:
            self._set_status("Entry saved. Select article text to highlight it or mark it in red.")

    @staticmethod
    def _append_html(existing_html: str, addition_html: str) -> str:
        document = QTextDocument()
        document.setHtml(existing_html)
        cursor = QTextCursor(document)
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertBlock()
        cursor.insertHtml(addition_html)
        return document.toHtml()

    def _manual_entry(self) -> None:
        """Keep the daily writing loop usable when a topic has no encyclopedia page."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Write an English entry")
        dialog.setMinimumWidth(540)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Write down the English content you have checked. You can add more sources later.", "muted", True))
        form = QFormLayout()
        title_input = QLineEdit()
        original = self.topic_input.toPlainText().strip()
        if original and len(original) <= 70 and original.isascii():
            title_input.setText(original)
        title_input.setPlaceholderText("English title")
        form.addRow("English title", title_input)
        body_input = QTextEdit()
        body_input.setMinimumHeight(170)
        body_input.setPlaceholderText("Write what you learned in English…")
        form.addRow("English content", body_input)
        chapter_input = QComboBox()
        chapter_input.addItems(CATEGORIES)
        form.addRow("Chapter", chapter_input)
        subchapter_input = QLineEdit()
        subchapter_input.setPlaceholderText("Optional subchapter")
        form.addRow("Subchapter", subchapter_input)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)

        def validate_and_accept() -> None:
            if not title_input.text().strip() or not body_input.toPlainText().strip():
                QMessageBox.information(dialog, "Missing information", "Add an English title and content.")
                return
            dialog.accept()

        buttons.accepted.connect(validate_and_accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        title = title_input.text().strip()
        paragraph = f'<p style="font-size:16px;line-height:1.6;">{escape(body_input.toPlainText())}</p>'
        existing = next((e for e in self.store.list_entries() if e.title.casefold() == title.casefold()), None)
        if existing:
            originals = existing.original_input
            if original and original not in originals:
                originals += f"\n\n[{date.today().isoformat()}] {original}"
            entry = replace(existing, original_input=originals,
                            body_html=self._append_html(existing.body_html, paragraph))
        else:
            entry = Entry(title=title, original_input=original,
                          category=chapter_input.currentText(),
                          subcategory=subchapter_input.text().strip(), body_html=paragraph)
        saved = self.store.upsert_entry(entry)
        self.target_entry_id = None
        self._refresh_catalog()
        self._open_entry(saved.id)
        self._set_status("Your English entry is saved on this computer.")

    def _images_saved(self, entry_id: int, count: int) -> None:
        if self.current_entry and self.current_entry.id == entry_id:
            self._draw_saved_images(entry_id)
        self._set_status(f"Saved {count} image{'s' if count != 1 else ''} to your computer." if count else
                         "Text saved, but the images could not be downloaded. Try again later.")

    def _refresh_catalog(self) -> None:
        entries = self.store.list_entries()
        self.catalog.clear()
        grouped: dict[str, dict[str, list[Entry]]] = {category: {} for category in CATEGORIES}
        for entry in entries:
            chapter = entry.category if entry.category in grouped else "Unsorted"
            grouped[chapter].setdefault(entry.subcategory or "General", []).append(entry)
        for category in CATEGORIES:
            groups = grouped[category]
            count = sum(len(items) for items in groups.values())
            if not count:
                continue
            chapter = QTreeWidgetItem([f"{category}  ·  {count}"])
            chapter.setData(0, Qt.ItemDataRole.UserRole, ("chapter", category, ""))
            self.catalog.addTopLevelItem(chapter)
            for subcategory in sorted(groups, key=str.casefold):
                parent = QTreeWidgetItem([subcategory])
                parent.setData(0, Qt.ItemDataRole.UserRole, ("subcategory", category, subcategory))
                chapter.addChild(parent)
                for entry in groups[subcategory]:
                    item = QTreeWidgetItem([entry.title])
                    item.setData(0, Qt.ItemDataRole.UserRole, ("entry", entry.id, ""))
                    parent.addChild(item)
                parent.setExpanded(True)
            chapter.setExpanded(bool(count))

    def _catalog_clicked(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        self._close_menu()
        kind, first, second = data
        if kind == "entry":
            self._open_entry(first)
        elif kind == "chapter":
            self._show_chapter(first)
        else:
            self._show_chapter(first, second)

    def _show_chapter(self, category: str, subcategory: str | None = None) -> None:
        self._save_reader()
        self._show_research_window()
        self.chapter_title.setText(subcategory or category)
        entries = self.store.list_entries(category=category, subcategory=subcategory)
        self.chapter_subtitle.setText(f"{category} · {len(entries)} entries")
        clear_layout(self.chapter_items)
        if not entries:
            self.chapter_items.addWidget(label("No entries in this chapter yet.", "muted"))
        for entry in entries:
            button = QPushButton(f"{entry.title}     ↗")
            button.setMinimumHeight(52)
            button.setStyleSheet("text-align:left; padding-left:18px; background:white;")
            button.clicked.connect(lambda checked=False, entry_id=entry.id: self._open_entry(entry_id))
            self.chapter_items.addWidget(button)
        self.chapter_items.addStretch()
        self.pages.setCurrentWidget(self.chapter_page)

    def _open_entry(self, entry_id: int | None) -> None:
        if entry_id is None:
            return
        if self.current_entry and self.current_entry.id != entry_id:
            self._save_reader()
        entry = self.store.get_entry(entry_id)
        if entry is None:
            self._refresh_catalog()
            self._show_home()
            return
        self.current_entry = entry
        self._show_research_window()
        self._loading_reader = True
        self.save_timer.stop()
        self.reader_title.setText(entry.title)
        self.reader_category.setCurrentText(entry.category or "Unsorted")
        self.reader_subcategory.setText(entry.subcategory)
        self.article_editor.setHtml(entry.body_html)
        self.original_note.setText("Original input (stored on this device): " + entry.original_input)
        self.original_note.hide()
        self._loading_reader = False
        self.source_button.setEnabled(bool(entry.source_url))
        self._draw_saved_images(entry_id)
        self.pages.setCurrentWidget(self.reader_page)
        self._set_status("Edit the article or select text to mark it. Changes save automatically.")

    def _draw_saved_images(self, entry_id: int) -> None:
        clear_layout(self.image_layout)
        images = self.store.list_images(entry_id)
        self.image_scroller.setVisible(bool(images))
        for record in images:
            card = QFrame()
            card.setObjectName("imageCard")
            card.setFixedWidth(180)
            column = QVBoxLayout(card)
            column.setContentsMargins(8, 8, 8, 8)
            picture = QLabel()
            picture.setFixedHeight(91)
            picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pixmap = QPixmap(record.local_path)
            if not pixmap.isNull():
                picture.setPixmap(pixmap.scaled(158, 91, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation))
            else:
                picture.setText("Image file missing")
            column.addWidget(picture)
            caption = QPushButton((record.caption or "Image")[:25] + " ↗")
            caption.setToolTip(f"{record.attribution}\n{record.license}\n{record.source_url}")
            caption.clicked.connect(lambda checked=False, url=record.source_url: QDesktopServices.openUrl(QUrl(url)))
            column.addWidget(caption)
            credit = label(f"{record.attribution or 'Wikimedia Commons'} · {record.license or 'See source'}", "muted")
            credit.setToolTip(f"{record.attribution}\n{record.license}")
            column.addWidget(credit)
            self.image_layout.addWidget(card)
        self.image_layout.addStretch()

    def _queue_save(self) -> None:
        if not self._loading_reader and self.current_entry and self.pages.currentWidget() is self.reader_page:
            self.save_timer.start()

    def _save_reader(self) -> None:
        if not hasattr(self, "pages") or self.current_entry is None:
            return
        if self.pages.currentWidget() is not self.reader_page and not self.save_timer.isActive():
            return
        self.save_timer.stop()
        title = self.reader_title.text().strip()
        if not title:
            self._set_status("Enter an English title.")
            return
        entry = replace(self.current_entry, title=title,
                        category=self.reader_category.currentText(),
                        subcategory=self.reader_subcategory.text().strip(),
                        body_html=self.article_editor.toHtml())
        if entry != self.current_entry:
            self.current_entry = self.store.upsert_entry(entry)
            self._refresh_catalog()
            self._set_status("Saved automatically.")

    def _mark_text(self, kind: str) -> None:
        cursor = self.article_editor.textCursor()
        if not cursor.hasSelection():
            self._set_status("Select text in the article, then choose a pen.")
            return
        fmt = QTextCharFormat()
        if kind == "yellow":
            fmt.setBackground(QColor("#fff09a"))
        elif kind == "red":
            fmt.setForeground(QColor("#bb4247"))
            fmt.setFontUnderline(True)
            fmt.setUnderlineColor(QColor("#bb4247"))
        else:
            fmt.setBackground(QColor("#ffffff"))
            fmt.setForeground(QColor("#34483d"))
            fmt.setFontUnderline(False)
        cursor.mergeCharFormat(fmt)
        self.article_editor.setTextCursor(cursor)
        self._save_reader()

    def _open_source(self) -> None:
        if self.current_entry and self.current_entry.source_url:
            QDesktopServices.openUrl(QUrl(self.current_entry.source_url))

    def _extend_entry(self) -> None:
        if not self.current_entry:
            return
        self._save_reader()
        self.target_entry_id = self.current_entry.id
        self.topic_input.setPlainText(self.current_entry.title)
        self._show_home()
        self._explore()

    def _delete_entry(self) -> None:
        if not self.current_entry:
            return
        answer = QMessageBox.question(self, "Delete entry", f"Delete “{self.current_entry.title}”?",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        image_paths = [Path(item.local_path) for item in self.store.list_images(self.current_entry.id)]
        self.store.delete_entry(self.current_entry.id)
        still_used = {
            str(Path(image.local_path).resolve())
            for entry in self.store.list_entries()
            for image in self.store.list_images(entry.id)
        }
        for path in image_paths:
            try:
                if (path.is_file() and path.parent.resolve() == self.store.images_dir.resolve()
                        and str(path.resolve()) not in still_used):
                    path.unlink()
            except OSError:
                pass
        self.current_entry = None
        self._refresh_catalog()
        self._show_home()
        self._set_status("Entry deleted.")

    def _toggle_voice(self) -> None:
        if self.voice_recorder is None:
            self.voice_menu.popup(self.mic_button.mapToGlobal(self.mic_button.rect().bottomLeft()))
            return
        recorder = self.voice_recorder
        self.voice_recorder = None
        self.mic_button.setEnabled(False)
        self.mic_button.setToolTip("Transcribing…")
        self._run_job(recorder.stop_and_transcribe, self._voice_ready, self._voice_failed)

    def _start_voice(self, language: str) -> None:
        if self.voice_recorder is not None:
            return
        try:
            from .voice import VoiceRecorder
            self.voice_recorder = VoiceRecorder(
                language,
                on_level=lambda amount: self.voice_signals.level.emit(amount),
                on_progress=lambda message: self.voice_signals.progress.emit(message),
            )
            self.voice_recorder.start()
        except Exception as exc:
            self.voice_recorder = None
            self._show_error(f"Could not start recording: {exc}")
            return
        self.mic_button.setIcon(icon("stop", "#b94646"))
        self.mic_button.setToolTip("Stop and transcribe")
        self.mic_button.setAccessibleName("Stop and transcribe")
        self.mic_button.setProperty("recording", True)
        self.mic_button.style().unpolish(self.mic_button)
        self.mic_button.style().polish(self.mic_button)
        self._set_status("Recording. Click the microphone again to transcribe your speech.")

    def _show_voice_level(self, amount: float) -> None:
        if self.voice_recorder is not None and amount > 0.04:
            self._set_status("Listening…")

    def _voice_ready(self, transcript: object) -> None:
        self._reset_mic_button()
        if transcript:
            if self.topic_input.toPlainText().strip():
                self.topic_input.insertPlainText(" " + str(transcript))
            else:
                self.topic_input.setPlainText(str(transcript))
            self.topic_input.setFocus()
            self._set_status("Transcript ready. Check it, then search.")
        else:
            self._set_status("Could not hear speech. Try again.")

    def _voice_failed(self, message: str) -> None:
        self._reset_mic_button()
        self._show_error(f"Transcription failed: {message}")

    def _reset_mic_button(self) -> None:
        self.mic_button.setEnabled(True)
        self.mic_button.setIcon(icon("mic"))
        self.mic_button.setToolTip("Dictate in Chinese or English")
        self.mic_button.setAccessibleName("Dictate")
        self.mic_button.setProperty("recording", False)
        self.mic_button.style().unpolish(self.mic_button)
        self.mic_button.style().polish(self.mic_button)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._save_reader()
        if self.voice_recorder is not None:
            try:
                self.voice_recorder.cancel()
            except Exception:
                pass
        if self.jobs:
            self._closing = True
            self.hide()
            event.ignore()
            QTimer.singleShot(250, self._close_when_idle)
            return
        event.accept()

    def _close_when_idle(self) -> None:
        if not self._closing:
            return
        if self.jobs:
            QTimer.singleShot(250, self._close_when_idle)
        else:
            self.close()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Little Atlas")
    app.setOrganizationName("Little Atlas")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return app.exec()
