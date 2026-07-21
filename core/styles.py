APP_STYLE = """
QWidget {
    font-family: "JetBrains Mono";
    color: #FFC400;
    font-size: 12px;
}

#terminalBox {
    background-color: rgba(0, 0, 0, 120);
    border: 0px solid rgba(114, 255, 66, 0.30);
    border-radius: 13px;
}

#title {
    color: #FFC400;
    font-size: 9px;
    font-weight: 200;
    letter-spacing: 1px;
}

#status {
    color: #FFC400;
    font-size: 10px;
}

#divider {
    color: #FFC400;
    font-size: 6px;
}

#flag {
    color: #FFC400;
    font-size: 12px;
    font-weight: 700;
}

#minimizeButton {
    color: #FFC400;
    font-size: 13px;
    padding: 0px 4px;
}
#codeButton, #referenceButton, #reloadButton {
    color: #FFC400;
    font-size: 9px;
    font-weight: 500;
    padding: 0px 5px;
}

#referenceButton {
    font-size: 12px;
    padding: 0px 3px;
}

#reloadButton {
    font-size: 13px;
    padding: 0px 3px;
}

#codeButton:hover, #referenceButton:hover, #reloadButton:hover {
    color: #A5FF73;
}

#minimizeButton:hover {
    color: #A5FF73;
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
    color: #FFC400;
    font-size: 12px;
}

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

#suggestionSelected {
    color: #FFC400;
    font-size: 11px;
}

"""