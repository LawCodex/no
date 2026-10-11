#!/usr/bin/env python3
"""Convert Lovdata public-data HTML/XML documents to LawCodex Markdown.

Usage: python convert.py EXTRACTED_DIR REPO_DIR [--retrieved YYYY-MM-DD]

EXTRACTED_DIR is the output of fetch.py (contains nl/, sf/, del/, ins/, stv/).
"""
import argparse
import copy
import datetime
import json
import os
import re
import sys
import unicodedata

from lxml import etree, html

BASE = "https://lovdata.no/"

# Lovdata base -> (output dir, type)
CATEGORIES = {
    "nl": ("lover", "act"),
    "sf": ("forskrifter", "regulation"),
    "del": ("delegeringsvedtak", "delegation"),
    "ins": ("instrukser", "instruction"),
    "stv": ("stortingsvedtak", "parliamentary_decision"),
}

WS = re.compile(r"[ \t\r\n]+")
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
BLOCK_TAGS = {"ol", "ul", "table", "footer", "div", "article", "section", "p", "blockquote",
              "figure", "figcaption", "main", "li", "caption"} | HEADINGS


def classes(el):
    return (el.get("class") or "").split()


def is_block(el):
    if not isinstance(el.tag, str):
        return False
    if el.tag in BLOCK_TAGS:
        return True
    if el.tag == "span" and "miscHeadline" in classes(el):
        return True
    if el.tag == "span" and "futureLegalArticleHeader" in classes(el):
        return True
    return False


def esc_text(t):
    t = WS.sub(" ", t)
    t = t.replace("\\", "\\\\").replace("*", "\\*").replace("`", "\\`")
    t = re.sub(r"<(?=[A-Za-z/!?])", "&lt;", t)
    t = t.replace("[", "\\[").replace("]", "\\]")
    return t


def wrap(mark, s):
    """Wrap inline content in emphasis marks, keeping surrounding whitespace outside."""
    m = re.match(r"^(\s*)(.*?)(\s*)$", s, re.S)
    lead, core, trail = m.groups()
    if not core:
        return s
    return f"{lead}{mark}{core}{mark}{trail}"


class Converter:
    def __init__(self):
        self.footnotes_seen = 0

    # ---------- inline ----------
    def inline(self, el, in_heading=False):
        """Render an element (inline) including its children, excluding its tail."""
        tag = el.tag if isinstance(el.tag, str) else ""
        cls = classes(el)
        if tag == "br":
            return " " if in_heading else "\\\n"
        if tag == "img":
            src = el.get("src") or ""
            if src and not src.startswith("http"):
                src = BASE + src
            alt = WS.sub(" ", el.get("alt") or "").replace("]", "")
            return f"![{alt}]({src})"
        if tag == "sup" and "footnotereference" in cls:
            n = el.get("data-unique-footnote-counter") or WS.sub("", el.text_content())
            return f"[^{n}]"
        if tag == "span" and "latexInline" in cls:
            return el.text_content()
        if tag == "span" and "footnoteLabel" in cls:
            return ""
        inner = self.inline_children(el, in_heading)
        if tag in ("i", "em"):
            return wrap("*", inner)
        if tag in ("strong", "b"):
            return wrap("**", inner)
        if tag == "sup":
            return f"<sup>{inner}</sup>" if inner.strip() else inner
        if tag == "sub":
            return f"<sub>{inner}</sub>" if inner.strip() else inner
        if tag == "s":
            return wrap("~~", inner)
        if tag == "span" and "underline" in cls:
            return f"<u>{inner}</u>" if inner.strip() else inner
        return inner

    def inline_children(self, el, in_heading=False):
        out = [esc_text(el.text or "")]
        for ch in el:
            if isinstance(ch.tag, str):
                out.append(self.inline(ch, in_heading))
            out.append(esc_text(ch.tail or ""))
        return "".join(out)

    # ---------- blocks ----------
    def para(self, text):
        text = re.sub(r"[ ]*\\\n[ ]*", "\\\n", text)
        text = re.sub(r"^(?:\s|\\\n)+", "", text)
        text = re.sub(r"(?:\s|\\\n)+$", "", text)
        text = re.sub(r"\\$", "", text) if text.endswith("\\") and not text.endswith("\\\\") else text
        text = re.sub(r"(\\\n)+", "\\\n", text)
        if not text:
            return None
        lines = text.split("\n")
        # escape markdown block syntax at the start of each line
        fixed = []
        for ln in lines:
            ln = ln.lstrip()
            ln = re.sub(r"^(\d+)([.)])(\s|$)", r"\1\\\2\3", ln)
            ln = re.sub(r"^([#>+\-=|])", r"\\\1", ln)
            fixed.append(ln)
        return "\n".join(fixed)

    def mixed(self, el):
        """Render an element whose content mixes inline runs and block children."""
        blocks = []
        buf = [esc_text(el.text or "")]

        def flush():
            p = self.para("".join(buf))
            if p:
                blocks.append(p)
            buf.clear()

        for ch in el:
            if not isinstance(ch.tag, str):
                buf.append(esc_text(ch.tail or ""))
                continue
            if is_block(ch):
                flush()
                blocks.extend(self.block(ch))
            else:
                buf.append(self.inline(ch))
            buf.append(esc_text(ch.tail or ""))
        flush()
        return blocks

    def heading_text(self, el):
        t = self.inline_children(el, in_heading=True)
        return WS.sub(" ", t).strip()

    def block(self, el):
        tag = el.tag
        cls = classes(el)
        if tag == "h1":
            return []
        if tag in HEADINGS:
            t = self.heading_text(el)
            if not t:
                return []
            return [f"{'#' * int(tag[1])} {t}"]
        if "legalArticleHeader" in cls or "futureLegalArticleHeader" in cls:
            t = self.heading_text(el)
            return [f"**{t}**"] if t else []
        if tag == "span" and "miscHeadline" in cls:
            p = self.para(self.inline_children(el))
            return [p] if p else []
        if tag in ("ol", "ul"):
            return [self.listing(el)]
        if tag == "table":
            return self.table(el)
        if tag == "footer":
            out = []
            for fn in el:
                if isinstance(fn.tag, str):
                    out.extend(self.footnote(fn))
            return out
        if tag == "div" and "latexBlock" in cls:
            return [WS.sub(" ", el.text_content()).strip()]
        if tag == "blockquote":
            inner = self.mixed(el)
            return ["\n".join("> " + l if l else ">" for l in "\n\n".join(inner).split("\n"))]
        if "changesToParent" in cls:
            p = self.para(self.inline_children(el))
            return [wrap("*", p)] if p else []
        if "marginIdArticle" in cls:
            label = None
            for ch in el:
                if isinstance(ch.tag, str) and "data-marginOriginalId" in classes(ch):
                    label = WS.sub(" ", ch.text_content()).strip()
            blocks = self.mixed_skip(el, "data-marginOriginalId")
            if label:
                lab = "**" + esc_text(label) + "**"
                if blocks and not blocks[0].startswith(("#", "|", "-", "<", ">", "$$", "**")):
                    blocks[0] = lab + " " + blocks[0]
                else:
                    blocks.insert(0, lab)
            return blocks
        return self.mixed(el)

    def mixed_skip(self, el, skipcls):
        blocks = []
        buf = [esc_text(el.text or "")]
        for ch in el:
            if isinstance(ch.tag, str) and skipcls in classes(ch):
                buf.append(esc_text(ch.tail or ""))
                continue
            if isinstance(ch.tag, str) and is_block(ch):
                p = self.para("".join(buf))
                if p:
                    blocks.append(p)
                buf = []
                blocks.extend(self.block(ch))
            elif isinstance(ch.tag, str):
                buf.append(self.inline(ch))
            buf.append(esc_text(ch.tail or ""))
        p = self.para("".join(buf))
        if p:
            blocks.append(p)
        return blocks

    def footnote(self, fn):
        n = fn.get("data-unique-footnote-counter") or fn.get("data-name") or "?"
        blocks = self.mixed(fn)
        if not blocks:
            return [f"[^{n}]: "]
        first = f"[^{n}]: " + blocks[0].replace("\n", "\n    ")
        rest = ["    " + b.replace("\n", "\n    ") for b in blocks[1:]]
        return ["\n\n".join([first] + rest)]

    def listing(self, el):
        items = []
        for li in el:
            if not isinstance(li.tag, str):
                continue
            if li.tag != "li":
                items.append("\n\n".join(self.block(li)))
                continue
            label = (li.get("data-name") or "").strip()
            if label == "-" or label == "":
                label = ""
            blocks = self.mixed(li)
            if label:
                lab = re.sub(r"^(\d+)([.)])$", r"\1\\\2", esc_text(label))
                if blocks and not blocks[0].startswith(("- ", "|", "<", "$$", "#")):
                    blocks[0] = lab + " " + blocks[0]
                else:
                    blocks.insert(0, lab)
            if not blocks:
                blocks = [""]
            body = "\n\n".join(blocks)
            lines = body.split("\n")
            out = ["- " + lines[0]] + [("  " + l) if l else "" for l in lines[1:]]
            items.append("\n".join(out))
        return "\n".join(items) if all("\n\n" not in i for i in items) else "\n\n".join(items)

    # ---------- tables ----------
    def table(self, el):
        out = []
        cap = el.find("caption")
        if cap is not None:
            p = self.para(self.inline_children(cap))
            if p:
                out.append(p)
        rows = el.xpath("./tr|./thead/tr|./tbody/tr|./tfoot/tr")
        complex_ = (el.xpath(".//td[@colspan or @rowspan]|.//th[@colspan or @rowspan]")
                    or el.xpath(".//table|.//ol|.//ul|.//td//article//article|.//div[contains(@class,'latexBlock')]")
                    or not rows)
        if not complex_:
            grid = []
            for tr in rows:
                cells = [c for c in tr if isinstance(c.tag, str) and c.tag in ("td", "th")]
                row = []
                for c in cells:
                    t = self.inline_children(c)
                    t = t.replace("\\\n", "<br>")
                    t = WS.sub(" ", t).strip().replace("|", "\\|")
                    row.append(t)
                grid.append(row)
            width = max(len(r) for r in grid)
            if width == 0:
                return out
            grid = [r + [""] * (width - len(r)) for r in grid]
            lines = ["| " + " | ".join(grid[0]) + " |", "|" + "---|" * width]
            lines += ["| " + " | ".join(r) + " |" for r in grid[1:]]
            out.append("\n".join(lines))
            return out
        out.append(self.html_table(el))
        return out

    def html_table(self, el):
        el = copy.deepcopy(el)  # work on a copy
        for cap in el.findall("caption"):
            el.remove(cap)
        for sup in el.xpath('.//sup[contains(@class,"footnotereference")]'):
            n = sup.get("data-unique-footnote-counter") or sup.text or ""
            tail = sup.tail
            sup.clear()
            sup.text, sup.tail = f"[{n}]", tail
        etree.strip_tags(el, "a", "span")
        for node in el.iter():
            if not isinstance(node.tag, str):
                continue
            keep = {k: v for k, v in node.attrib.items() if k in ("colspan", "rowspan", "src", "alt")}
            node.attrib.clear()
            node.attrib.update(keep)
            if node.tag == "img" and node.get("src") and not node.get("src").startswith("http"):
                node.set("src", BASE + node.get("src"))
            if node.tag in ("article", "section", "footer"):
                node.tag = "div" if any(isinstance(c.tag, str) and c.tag in BLOCK_TAGS for c in node) else "p"
        s = etree.tostring(el, encoding="unicode", method="html")
        s = re.sub(r"\s*\n\s*", " ", s)
        return s.strip()


def meta(doc):
    m = {}
    for dt in doc.xpath('//header[@id="hode"]//dl/dt'):
        key = (dt.get("class") or "").split()[0] if dt.get("class") else None
        dd = dt.getnext()
        if key is None or dd is None or dd.tag != "dd":
            continue
        lis = dd.xpath(".//li")
        if lis and key in ("ministry",):
            val = "; ".join(WS.sub(" ", li.text_content()).strip() for li in lis)
        else:
            val = WS.sub(" ", dd.text_content()).strip()
        m[key] = val
    return m


TRANS = str.maketrans({"æ": "ae", "Æ": "ae", "ø": "o", "Ø": "o", "å": "a", "Å": "a",
                       "§": "", "–": "-", "—": "-"})


def slugify(s, maxlen=70):
    s = s.translate(TRANS)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s.lower()).strip("-")
    if len(s) > maxlen:
        s = s[:maxlen].rsplit("-", 1)[0]
    return s


def yq(v):
    return json.dumps(v, ensure_ascii=False)


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def convert_file(path, base, repo, retrieved, today):
    raw = open(path, "rb").read()
    doc = html.document_fromstring(raw.decode("utf-8"))
    m = meta(doc)
    lang = (doc.get("lang") or "no").strip()
    if lang not in ("nb", "nn", "no"):
        lang = "no"
    refid = m.get("refid", "")  # lov/1814-05-17 | forskrift/1896-06-26-9805
    rm = re.match(r"^(lov|forskrift)/(\d{4})-(\d{2})-(\d{2})(?:-(\w+))?$", refid)
    if not rm:
        raise ValueError(f"bad refid {refid!r}")
    year = rm.group(2)
    date = f"{rm.group(2)}-{rm.group(3)}-{rm.group(4)}"
    nr = rm.group(5)
    idpart = date + (f"-{nr}" if nr else "")
    title = m.get("title") or doc.findtext(".//h1") or refid
    title = WS.sub(" ", title).strip()
    short = m.get("titleShort", "")
    fname = os.path.basename(path)
    nynorsk_variant = fname.endswith("-nn.xml")

    is_constitution = refid == "lov/1814-05-17"
    outdir, typ = CATEGORIES[base]
    if is_constitution:
        rel = os.path.join("grunnloven", "grunnloven-nynorsk.md" if nynorsk_variant else "grunnloven.md")
        typ = "constitution"
    else:
        slug_src = short.split(" – ")[0] if short else title
        slug = slugify(slug_src) or "dokument"
        rel = os.path.join(outdir, year, f"{idpart}-{slug}.md")
        if nynorsk_variant:
            rel = rel[:-3] + "-nynorsk.md"

    dokid = m.get("dokid", "")
    source = BASE + "dokument/" + dokid if dokid else BASE + refid

    in_force = m.get("dateInForce", "")
    status = "in_force"
    if in_force and DATE_RE.match(in_force) and in_force > today:
        status = "not_yet_in_force"
    elif in_force and not re.search(r"\d{4}", in_force):
        status = "unknown"

    fm = [
        "---",
        f"title: {yq(title)}",
    ]
    if short:
        fm.append(f"short_title: {yq(short)}")
    fm += [
        f"identifier: {yq(m.get('legacyID', refid))}",
        f"type: {typ}",
        "jurisdiction: \"no\"",
        f"language: {yq(lang)}",
        f"date: {date}",
    ]
    if in_force:
        fm.append(f"in_force_from: {yq(in_force)}" if not DATE_RE.match(in_force) else f"in_force_from: {in_force}")
    lc = m.get("lastChangeInForce", "")
    if DATE_RE.match(lc):
        fm.append(f"last_amended: {lc}")
    if m.get("lastChangedBy"):
        fm.append(f"last_amended_by: {yq(m['lastChangedBy'])}")
    if m.get("ministry"):
        fm.append(f"ministry: {yq(m['ministry'])}")
    if m.get("publishedIn"):
        fm.append(f"published_in: {yq(m['publishedIn'])}")
    if m.get("appliesTo"):
        fm.append(f"applies_to: {yq(m['appliesTo'])}")
    fm += [
        f"status: {status}",
        f"source: {yq(source)}",
        f"retrieved: {retrieved}",
        "licence: \"NLOD 2.0 (Norsk lisens for offentlige data)\"",
        "---",
    ]

    conv = Converter()
    body = []
    main = doc.xpath('//main')
    if main:
        body = conv.block(main[0])
    misc = m.get("miscInformation")
    head = ["# " + esc_text(title).strip()]
    if misc:
        p = conv.para(esc_text(misc))
        if p:
            head.append("> " + p.replace("\n", "\n> "))
    text = "\n".join(fm) + "\n\n" + "\n\n".join(head + [b for b in body if b and b.strip()]) + "\n"
    text = text.replace("\r", "")
    return rel, text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("repo")
    ap.add_argument("--retrieved", default=datetime.date.today().isoformat())
    ap.add_argument("--only", help="comma-separated categories (nl,sf,del,ins,stv)")
    args = ap.parse_args()
    today = datetime.date.today().isoformat()
    cats = args.only.split(",") if args.only else list(CATEGORIES)
    counts = {}
    errors = []
    for base in cats:
        d = os.path.join(args.src, base)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".xml"):
                continue
            try:
                rel, text = convert_file(os.path.join(d, fn), base, args.repo, args.retrieved, today)
            except Exception as e:  # keep going, report at end
                errors.append((fn, repr(e)))
                continue
            out = os.path.join(args.repo, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            top = rel.split(os.sep)[0]
            counts[top] = counts.get(top, 0) + 1
    print(json.dumps(counts, indent=1))
    for e in errors:
        print("ERROR", *e, file=sys.stderr)


if __name__ == "__main__":
    main()
