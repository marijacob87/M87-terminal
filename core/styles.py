APP_STYLE = """
QWidget {
    font-family: "JetBrains Mono";
    color: #FFC400;
    font-size: 12px;
}

#terminalBox {
    background-color: rgba(0, 0, 0, 178);
    border: 1px solid rgba(255, 255, 255, 42);
    border-radius: 13px;
}

#contentContainer { background: transparent; }

#title {
    color: rgba(255, 255, 255, 0.97);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
    background: transparent;
}

#status { color: #FFC400; font-size: 10px; }
#divider { color: rgba(255, 255, 255, 0.25); font-size: 6px; }
#flag { color: #FFC400; font-size: 12px; font-weight: 700; }

#minimizeButton,
#codeButton,
#referenceButton,
#reloadButton {
    color: rgba(255, 255, 255, 0.96);
    background: transparent;
    font-weight: 600;
}

#minimizeButton { font-size: 13px; padding: 0px 2px; }
#codeButton { font-size: 9px; padding: 0px 2px; }
#referenceButton { font-size: 12px; padding: 0px 2px; }
#reloadButton { font-size: 13px; padding: 0px 2px; }

#codeButton:hover,
#referenceButton:hover,
#reloadButton:hover,
#minimizeButton:hover { color: #FFE066; }

#sizeGrip { width: 14px; height: 12px; background: transparent; }
#terminalInput { background: transparent; border: none; min-height: 18px; }
#suggestionsBox { background: transparent; }
#suggestionItem { color: #FFC400; font-size: 12px; }

QLabel#calculatorResultLabel {
    color: rgba(255,255,255,0.96);
    font-size: 13px;
    font-weight: 500;
    padding-top: 1px;
    padding-bottom: 3px;
}

QLabel#activeFileLabel {
    color: rgba(255,255,255,0.78);
    font-size: 11px;
    font-weight: 400;
    padding-top: 4px;
    padding-bottom: 4px;
    line-height: 1.25;
}

#suggestionSelected { color: #FFC400; font-size: 11px; }
"""
