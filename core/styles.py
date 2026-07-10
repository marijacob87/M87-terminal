APP_STYLE = """
QWidget {
    font-family: "JetBrains Mono";
    color: rgba(105, 220, 65, 0.92);
    font-size: 12px;
}

#terminalBox {
    background-color: rgba(0, 0, 0, 0.78);
    border: 1px solid rgba(114, 255, 66, 0.30);
    border-radius: 13px;
}

#title {
    color: rgba(114, 255, 66, 0.72);
    font-size: 9px;
    font-weight: 400;
    letter-spacing: 1px;
}

#status {
    color: rgba(105, 220, 65, 0.88);
    font-size: 12px;
}

#divider {
    color: rgba(114, 255, 66, 0.25);
    font-size: 6px;
}

#flag {
    color: rgba(165, 255, 115, 1);
    font-size: 12px;
    font-weight: 700;
}

#minimizeButton {
    color: rgba(114, 255, 66, 0.75);
    font-size: 13px;
    padding: 0px 4px;
}
#codeButton {
    color: rgba(114, 255, 66, 0.58);
    font-size: 9px;
    font-weight: 500;
    padding: 0px 5px;
}

#codeButton:hover {
    color: rgba(165, 255, 115, 1);
}

#minimizeButton:hover {
    color: rgba(165, 255, 115, 1);
}

#sizeGrip {
    width: 12px;
    height: 12px;
    background: transparent;
}

#terminalInput {
    background: transparent;
    border: none;
    min-height: 18px;
}

#suggestionsBox {
    background: transparent;
}

#suggestionItem {
    color: rgba(105, 220, 65, 0.48);
    font-size: 12px;
}

QLabel#activeFileLabel {
    color: rgba(255, 221, 40, 0.85);
    font-size: 11px;
    font-weight: 400;
    padding-top: 4px;
    padding-bottom: 4px;
    line-height: 1.25;
}

#suggestionSelected {
    color: rgba(255, 221, 40, 0.95);
    font-size: 12px;
}

"""