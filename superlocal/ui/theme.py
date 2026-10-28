"""
SuperLocal UI Theme Manager
Modern Windows 11 style styling: 8px grid, rounded cards, Segoe UI Variable / Inter font,
accent colors, and Dark/Light QSS sheets.
"""

from typing import Dict, Any


class Colors:
    # Accent & Status
    ACCENT = "#0078D4"           # Fluent Windows Blue
    ACCENT_HOVER = "#106EBE"
    ACCENT_PRESSED = "#005A9E"
    SUCCESS = "#107C41"          # Green
    WARNING = "#D83B01"          # Amber / Orange
    DANGER = "#D13438"           # Red
    INFO = "#0078D4"

    # Dark Theme Palette
    DARK_BG = "#1A1A1A"
    DARK_SURFACE = "#242424"
    DARK_CARD = "#2D2D2D"
    DARK_BORDER = "#3A3A3A"
    DARK_TEXT_PRIMARY = "#FFFFFF"
    DARK_TEXT_SECONDARY = "#CCCCCC"
    DARK_TEXT_MUTED = "#8A8A8A"

    # Light Theme Palette
    LIGHT_BG = "#F3F3F3"
    LIGHT_SURFACE = "#FFFFFF"
    LIGHT_CARD = "#FBFBFB"
    LIGHT_BORDER = "#E5E5E5"
    LIGHT_TEXT_PRIMARY = "#1F1F1F"
    LIGHT_TEXT_SECONDARY = "#424242"
    LIGHT_TEXT_MUTED = "#707070"


def get_stylesheet(dark: bool = True) -> str:
    """Returns complete Qt stylesheet for modern Fluent-inspired UI."""
    bg = Colors.DARK_BG if dark else Colors.LIGHT_BG
    surface = Colors.DARK_SURFACE if dark else Colors.LIGHT_SURFACE
    card = Colors.DARK_CARD if dark else Colors.LIGHT_CARD
    border = Colors.DARK_BORDER if dark else Colors.LIGHT_BORDER
    text_pri = Colors.DARK_TEXT_PRIMARY if dark else Colors.LIGHT_TEXT_PRIMARY
    text_sec = Colors.DARK_TEXT_SECONDARY if dark else Colors.LIGHT_TEXT_SECONDARY
    text_muted = Colors.DARK_TEXT_MUTED if dark else Colors.LIGHT_TEXT_MUTED

    return f"""
    * {{
        font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif;
        font-size: 13px;
        color: {text_pri};
        outline: none;
    }}

    QMainWindow, QDialog {{
        background-color: {bg};
    }}

    QWidget {{
        background-color: transparent;
    }}

    /* Rounded Card Panels */
    QFrame[card="true"] {{
        background-color: {card};
        border: 1px solid {border};
        border-radius: 8px;
    }}

    QScrollArea {{
        border: none;
        background-color: transparent;
    }}

    /* Scrollbars */
    QScrollBar:vertical {{
        border: none;
        background: transparent;
        width: 8px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {border};
        min-height: 24px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {Colors.ACCENT};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    /* Buttons */
    QPushButton {{
        background-color: {card};
        border: 1px solid {border};
        border-radius: 6px;
        padding: 6px 14px;
        font-weight: 500;
        min-height: 20px;
    }}
    QPushButton:hover {{
        background-color: {border};
        border-color: {Colors.ACCENT};
    }}
    QPushButton:pressed {{
        background-color: {surface};
    }}

    /* Accent Buttons */
    QPushButton[accent="true"] {{
        background-color: {Colors.ACCENT};
        border: 1px solid {Colors.ACCENT};
        color: #FFFFFF;
        font-weight: 600;
    }}
    QPushButton[accent="true"]:hover {{
        background-color: {Colors.ACCENT_HOVER};
        border-color: {Colors.ACCENT_HOVER};
    }}
    QPushButton[accent="true"]:pressed {{
        background-color: {Colors.ACCENT_PRESSED};
    }}

    /* Danger / Stop Buttons */
    QPushButton[danger="true"] {{
        background-color: {Colors.DANGER};
        border: 1px solid {Colors.DANGER};
        color: #FFFFFF;
        font-weight: 600;
    }}
    QPushButton[danger="true"]:hover {{
        background-color: #B8282C;
    }}

    /* LineEdit and TextEdit */
    QLineEdit, QTextEdit, QPlainTextEdit {{
        background-color: {card};
        border: 1px solid {border};
        border-radius: 6px;
        padding: 8px;
        color: {text_pri};
        selection-background-color: {Colors.ACCENT};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        border: 1.5px solid {Colors.ACCENT};
    }}

    /* ComboBox */
    QComboBox {{
        background-color: {card};
        border: 1px solid {border};
        border-radius: 6px;
        padding: 5px 10px;
        min-height: 22px;
    }}
    QComboBox:hover {{
        border-color: {Colors.ACCENT};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {surface};
        border: 1px solid {border};
        border-radius: 6px;
        selection-background-color: {Colors.ACCENT};
    }}

    /* Progress Bar */
    QProgressBar {{
        background-color: {border};
        border: none;
        border-radius: 4px;
        height: 6px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background-color: {Colors.ACCENT};
        border-radius: 4px;
    }}

    /* Tables */
    QTableWidget, QTableView {{
        background-color: {card};
        border: 1px solid {border};
        border-radius: 8px;
        gridline-color: {border};
        selection-background-color: {Colors.ACCENT};
        selection-color: #FFFFFF;
    }}
    QHeaderView::section {{
        background-color: {surface};
        border: none;
        border-bottom: 1px solid {border};
        padding: 6px;
        font-weight: bold;
        color: {text_sec};
    }}
    """
