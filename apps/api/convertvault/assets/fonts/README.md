# ConvertVault internal fonts

Place legally licensed `.ttf`, `.otf`, or `.ttc` files in this directory to make
them available to PDF Studio's automatic font-family resolver.

Container builds also populate `/data/fonts` with the open-source Noto,
Liberation, and DejaVu families. Together they cover the major Latin, Cyrillic,
Greek, Arabic, Hebrew, Indic, Southeast Asian, CJK, symbol, and emoji scripts.
Commercial fonts are not redistributed; an embedded PDF font is reused first,
and a matching installed/internal family is used only when its subset lacks a
newly typed glyph.
