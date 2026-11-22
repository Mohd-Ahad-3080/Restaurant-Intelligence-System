"""Validate a Tableau workbook (.twb) against the XML schema shipped inside Tableau itself.

Tableau Public keeps its workbook schema in bin/res/tablangres.rcc (a Qt resource bundle), as
TQRC_FILEFORMAT_TWB_XSD plus two small imported schemas. The schema has feature-flag sections
(<!--?IF Flag --> ... <!--?ELSE --> ... <!--?END -->), and workbooks carry flag-dependent names
('_.fcp.Flag.true...name'). Both are resolved from the workbook's own <document-format-change-manifest>:
flags listed there are on, every other flag is off. Tableau's own starter file validates cleanly this way.

Usage:  python scripts/validate_twb.py dashboards/tableau/RestaurantIntelligence.twb [more.twb ...]
Exit code 0 = valid, 1 = schema errors (printed with line numbers).
"""
from __future__ import annotations

import re
import struct
import sys
import tempfile
import zlib
from pathlib import Path

from lxml import etree

# Tableau Public's resource file holding its XML schemas: Windows install folder, or the macOS app bundle
RCC_CANDIDATES = sorted([*Path("C:/Program Files/Tableau").glob("Tableau Public */bin/res/tablangres.rcc"),
                         *Path("/Applications").glob("Tableau Public*.app/**/tablangres.rcc")], reverse=True)
NEEDED = ("TQRC_FILEFORMAT_TWB_XSD", "TQRC_FILEFORMAT_USER_XSD", "TQRC_FILEFORMAT_XML_XSD")


def read_rcc(path: Path, wanted: tuple[str, ...]) -> dict[str, bytes]:
    """Minimal Qt .rcc (format 1-3) reader: returns the wanted top-level files."""
    b = path.read_bytes()
    if b[:4] != b"qres":
        raise ValueError(f"{path} is not a Qt resource file")
    ver, tree, data, names = struct.unpack(">IIII", b[4:20])
    node = 14 if ver == 1 else 22
    out: dict[str, bytes] = {}

    def name(off: int) -> str:
        n = struct.unpack(">H", b[names + off:names + off + 2])[0]
        return b[names + off + 6:names + off + 6 + 2 * n].decode("utf-16-be")

    def walk(i: int) -> None:
        base = tree + i * node
        noff, flags = struct.unpack(">IH", b[base:base + 6])
        if flags & 2:  # directory
            count, first = struct.unpack(">II", b[base + 6:base + 14])
            for c in range(count):
                walk(first + c)
            return
        nm = name(noff)
        if nm in wanted:
            doff = struct.unpack(">I", b[base + 10:base + 14])[0]
            ln = struct.unpack(">I", b[data + doff:data + doff + 4])[0]
            raw = b[data + doff + 4:data + doff + 4 + ln]
            out[nm] = zlib.decompress(raw[4:]) if flags & 1 else raw

    walk(0)
    return out


def resolve_flags(xsd: str, enabled: set[str]) -> str:
    """Keep the <!--?IF Flag --> / <!--?ELSE --> branch that applies; nested blocks supported."""
    tokens = re.split(r"(<!--\?(?:IF\s+!?\w+|ELSE|END)\s*-->)", xsd)
    out, stack = [], []  # stack of (active_before, condition_true, in_else)
    active = True
    for t in tokens:
        m = re.fullmatch(r"<!--\?(IF\s+(!?)(\w+)|ELSE|END)\s*-->", t)
        if not m:
            if active:
                out.append(t)
            continue
        if m.group(1).startswith("IF"):
            cond = (m.group(3) in enabled) != (m.group(2) == "!")
            stack.append((active, cond))
            active = active and cond
        elif m.group(1) == "ELSE":
            parent, cond = stack[-1]
            active = parent and not cond
        else:
            active = stack.pop()[0]
    if stack:
        raise ValueError("unbalanced IF/END in schema")
    # A choice whose branches were all switched off is empty. Tableau's validator accepts "nothing" there
    # (its own dashboards would otherwise be invalid); strict XSD (lxml) would reject everything after it.
    return re.sub(r"<xs:choice(?:\s[^>]*)?>\s*</xs:choice>", "", "".join(out))


def manifest_flags(doc: etree._ElementTree) -> set[str]:
    m = doc.getroot().find("document-format-change-manifest")
    return {re.sub(r"^_\.fcp\.\w+\.(true|false)\.\.\.", "", c.tag) for c in m} if m is not None else set()


def resolve_document(doc: etree._ElementTree, enabled: set[str]) -> None:
    """Apply '_.fcp.Flag.true...name' / '.false...' prefixes on element and attribute names."""
    pat = re.compile(r"^_\.fcp\.(\w+)\.(true|false)\.\.\.(.+)$")
    for el in list(doc.getroot().iter()):
        if not isinstance(el.tag, str):
            continue
        m = pat.match(el.tag)
        if m:
            if (m.group(1) in enabled) == (m.group(2) == "true"):
                el.tag = m.group(3)
            else:
                el.getparent().remove(el)
                continue
        for a in list(el.attrib):
            m = pat.match(a)
            if m:
                v = el.attrib.pop(a)
                if (m.group(1) in enabled) == (m.group(2) == "true"):
                    el.set(m.group(3), v)


def _schema_resources() -> dict[str, bytes]:
    """Find the resource bundle containing all required schemas.

    Tableau may ship localized bundles without workbook XSD resources.
    """
    for candidate in RCC_CANDIDATES:
        files = read_rcc(candidate, NEEDED)
        if all(key in files for key in NEEDED):
            return files
    if not RCC_CANDIDATES:
        raise SystemExit("Tableau Public is not installed (no tablangres.rcc found).")
    raise SystemExit("No Tableau tablangres.rcc bundle contains all required workbook schemas.")


def validate(path: Path) -> list[str]:
    files = _schema_resources()
    doc = etree.parse(str(path))
    enabled = manifest_flags(doc)
    resolve_document(doc, enabled)
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "user.xsd").write_bytes(files["TQRC_FILEFORMAT_USER_XSD"])
        (d / "xml.xsd").write_bytes(files["TQRC_FILEFORMAT_XML_XSD"])
        xsd = resolve_flags(files["TQRC_FILEFORMAT_TWB_XSD"].decode("utf-8"), enabled)
        xsd = xsd.replace('<xs:import namespace="http://www.tableausoftware.com/xml/user"/>',
                          f'<xs:import namespace="http://www.tableausoftware.com/xml/user" '
                          f'schemaLocation="{(d / "user.xsd").as_uri()}"/>')
        xsd = xsd.replace('<xs:import namespace="http://www.w3.org/XML/1998/namespace"/>',
                          f'<xs:import namespace="http://www.w3.org/XML/1998/namespace" '
                          f'schemaLocation="{(d / "xml.xsd").as_uri()}"/>')
        (d / "twb.xsd").write_text(xsd, encoding="utf-8")
        schema = etree.XMLSchema(etree.parse(str(d / "twb.xsd")))
    if schema.validate(doc):
        return []
    return [f"line {e.line}: {e.message}" for e in schema.error_log]


if __name__ == "__main__":
    bad = 0
    for arg in sys.argv[1:]:
        errs = validate(Path(arg))
        print(f"{arg}: {'VALID' if not errs else f'{len(errs)} schema error(s)'}")
        for e in errs:
            print("  " + e)
        bad += bool(errs)
    sys.exit(1 if bad else 0)
