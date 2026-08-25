import re


# Aproximações sRGB para identificação visual na interface. A separação do PDF
# continua sendo a fonte de verdade para produção e não é alterada por esta tabela.
PANTONE_SRGB = {
    "PANTONE 185 C": "#E4002B",
    "PANTONE 186 C": "#C8102E",
    "PANTONE 286 C": "#0033A0",
    "PANTONE 3005 C": "#0077C8",
    "PANTONE 485 C": "#DA291C",
    "PANTONE 871 C": "#84754E",
    "PANTONE 2768 C": "#071D49",
    "PANTONE PROCESS BLUE C": "#0085CA",
    "PANTONE REFLEX BLUE C": "#001489",
}


def spot_srgb(name):
    normalized = re.sub(r"\s+", " ", str(name).strip()).upper()
    return PANTONE_SRGB.get(normalized, "#777777")
