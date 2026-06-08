from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
SITE_BASE_URL = os.getenv("SITE_BASE_URL", "https://obaksa-home.github.io")
BLOG_FETCH_CANDIDATES = [
    ROOT / "blog_fetch_result.json",
    ROOT.parent / "blog_fetch_result.json",
    ROOT / "output" / "blog_fetch_result.json",
    ROOT / "data" / "blog_fetch_result.json",
    ROOT / "tmp" / "blog_fetch_result.json",
]

MARKERS = {
    "index.html": (
        "<!-- AUTO:LATEST_CASE_START -->",
        "<!-- AUTO:LATEST_CASE_END -->",
    ),
    "cases.html": (
        "<!-- AUTO:CASE_HIGHLIGHTS_START -->",
        "<!-- AUTO:CASE_HIGHLIGHTS_END -->",
        "<!-- AUTO:CASE_LIST_START -->",
        "<!-- AUTO:CASE_LIST_END -->",
    ),
    "sitemap.xml": (
        "<!-- AUTO:SITEMAP_CASES_START -->",
        "<!-- AUTO:SITEMAP_CASES_END -->",
    ),
}

PREVIEW_DIR = ROOT / "build_preview"
CASES_INDEX_PATH = ROOT / "cases_index.json"
CASES_INDEX_PREVIEW_PATH = PREVIEW_DIR / "cases_index.preview.json"
APPLY_BACKUP_DIR = ROOT / "backups"


@dataclass
class BlogData:
    title: str = ""
    date: str = ""
    year: str = ""
    slug: str = ""
    category: str = ""
    summary: str = ""
    source_url: str = ""
    instagram_url: str = ""
    images: list[str] | None = None
    thumbnail: str = ""
    source_path: Path | None = None


@dataclass
class CaseEntry:
    date: str
    title: str
    summary: str
    slug: str
    category: str = ""
    thumb: str = ""
    source_url: str = ""
    instagram_url: str = ""
    highlight_image: str = ""

    @property
    def year(self) -> str:
        return extract_year(self.date)

    @property
    def case_url(self) -> str:
        return f"cases/{self.year}/case-{self.slug}.html"

    @property
    def sitemap_url(self) -> str:
        return f"{SITE_BASE_URL}/{self.case_url}"


def load_blog_data() -> tuple[bool, BlogData, Path | None]:
    for candidate in BLOG_FETCH_CANDIDATES:
        if candidate.exists():
            with candidate.open("r", encoding="utf-8") as f:
                data = json.load(f)
            source_url = str(data.get("input_url") or data.get("url") or "").strip()
            date_text = str(data.get("date", "")).strip()
            year = extract_year(date_text)
            slug = normalize_slug(str(data.get("slug", "")).strip(), date_text, str(data.get("title", "")).strip())
            return True, BlogData(
                title=str(data.get("title", "")).strip(),
                date=date_text,
                year=year,
                slug=slug,
                category=str(data.get("category", "")).strip(),
                summary=str(data.get("summary", "")).strip(),
                source_url=source_url,
                instagram_url=str(data.get("instagram_url", "")).strip(),
                images=list(data.get("images") or []),
                thumbnail=str(data.get("thumbnail", "")).strip(),
                source_path=candidate,
            ), candidate
    return False, BlogData(), None


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_year(date_text: str) -> str:
    if len(date_text) >= 4 and date_text[:4].isdigit():
        return date_text[:4]
    return datetime.now().strftime("%Y")


def normalize_slug(existing_slug: str, date_text: str, title: str) -> str:
    if existing_slug:
        return existing_slug
    base = title or "new-case"
    cleaned = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    cleaned = cleaned.lower()
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in cleaned)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    cleaned = cleaned[:48].strip("-")
    year = extract_year(date_text)
    if cleaned:
        return f"{year}-{cleaned}"
    return f"{year}-new-case"


def case_folder_slug(data: BlogData) -> str:
    return data.slug or normalize_slug("", data.date, data.title)


def case_url_for(data: BlogData) -> str:
    slug = case_folder_slug(data)
    year = data.year or extract_year(data.date)
    return f"cases/{year}/case-{slug}.html"


def sitemap_url_for(data: BlogData) -> str:
    return f"{SITE_BASE_URL}/{case_url_for(data)}"


def thumbnail_path_for(data: BlogData) -> str:
    return f"images/cases/{case_folder_slug(data)}/thumb.jpg"


def parse_case_date(raw: str) -> str:
    raw = (raw or "").strip()
    if re.match(r"20\d{2}\.\d{2}\.\d{2}", raw):
        return raw.replace(".", "-")
    if re.match(r"20\d{2}-\d{2}-\d{2}", raw):
        return raw
    return datetime.now().strftime("%Y-%m-%d")


def parse_case_entries_from_text(text: str) -> list[CaseEntry]:
    entries: list[CaseEntry] = []
    seen: set[str] = set()

    row_pattern = re.compile(
        r'<div class="case-row"[^>]*data-category="(?P<category>[^"]*)">.*?'
        r'<div class="case-date">(?P<date>[^<]*)</div>.*?'
        r'<div class="case-cat"><span>[^<]*</span></div>.*?'
        r'<div class="case-title">\s*<a href="(?P<href>[^"]+)">(?P<title>[^<]*)</a>\s*<p>(?P<summary>[^<]*)</p>',
        re.S,
    )
    for m in row_pattern.finditer(text):
        href = m.group("href").strip()
        slug_match = re.search(r"case-([a-z0-9\-]+)\.html", href)
        if not slug_match:
            continue
        slug = slug_match.group(1)
        if slug in seen:
            continue
        seen.add(slug)
        entries.append(
            CaseEntry(
                date=parse_case_date(m.group("date")),
                title=m.group("title").strip(),
                summary=m.group("summary").strip(),
                slug=slug,
                category=m.group("category").strip(),
                thumb="",
            )
        )

    return entries


def load_existing_cases() -> list[CaseEntry]:
    candidates = [ROOT / "cases.html", PREVIEW_DIR / "cases.preview.html"]
    for path in candidates:
        if path.exists():
            entries = parse_case_entries_from_text(read_text(path))
            if entries:
                return entries
    return []


def merge_cases(existing: list[CaseEntry], new_case: CaseEntry) -> tuple[list[CaseEntry], bool, bool]:
    merged: dict[str, CaseEntry] = {}
    duplicate = False
    replaced = False

    def put(entry: CaseEntry, is_new: bool = False) -> None:
        nonlocal duplicate, replaced
        key = entry.case_url
        if key in merged:
            duplicate = True
            if is_new:
                replaced = True
        merged[key] = entry

    for entry in existing:
        put(entry)
    put(new_case, is_new=True)
    ordered = sorted(merged.values(), key=lambda item: item.date, reverse=True)
    return ordered, duplicate, replaced


def build_case_feature_card(entry: CaseEntry, is_latest: bool = False) -> str:
    img = entry.highlight_image or entry.thumb or "images/gallery/case_hero.jpg"
    link_block = [f'      <a href="{entry.case_url}">상세보기</a>']
    if entry.instagram_url:
        link_block.append(f'      <a href="{entry.instagram_url}" target="_blank" rel="noopener">Instagram</a>')
    return "\n".join([
        '<article class="case-feature-card">',
        f'  <img src="{img}" alt="{entry.title}">',
        "  <div>",
        f"    <h2>{entry.title}</h2>",
        f"    <p>{entry.summary}</p>",
        '    <div class="case-card-links">',
        *link_block,
        "    </div>",
        "  </div>",
        "</article>",
    ])


def build_case_row(entry: CaseEntry) -> str:
    return "\n".join([
        f'<div class="case-row" data-category="{entry.category}">',
        f'  <div class="case-date">{entry.date.replace("-", ".")}</div>',
        f'  <div class="case-cat"><span>{entry.category}</span></div>',
        '  <div class="case-title">',
        f'    <a href="{entry.case_url}">{entry.title}</a>',
        f'    <p>{entry.summary}</p>',
        "  </div>",
        f'  <div class="case-more"><a href="{entry.case_url}">보기</a></div>',
        "</div>",
    ])


def build_sitemap_entry(entry: CaseEntry) -> str:
    return f'  <url><loc>{entry.sitemap_url}</loc><lastmod>{entry.date}</lastmod></url>'


def make_case_entry_from_blog(data: BlogData) -> CaseEntry:
    return CaseEntry(
        date=data.date or datetime.now().strftime("%Y-%m-%d"),
        title=data.title,
        summary=data.summary,
        slug=case_folder_slug(data),
        category=data.category,
        thumb=data.thumbnail or thumbnail_path_for(data),
        source_url=data.source_url,
        instagram_url=data.instagram_url,
        highlight_image=data.thumbnail or thumbnail_path_for(data),
    )


def case_entry_to_dict(entry: CaseEntry) -> dict[str, str]:
    return {
        "title": entry.title,
        "date": entry.date,
        "slug": entry.slug,
        "category": entry.category,
        "summary": entry.summary,
        "case_url": entry.case_url,
        "thumbnail": entry.thumb,
        "source_url": entry.source_url,
        "instagram_url": entry.instagram_url,
    }


def load_cases_index() -> tuple[list[CaseEntry], str]:
    if CASES_INDEX_PATH.exists():
        raw = json.loads(read_text(CASES_INDEX_PATH))
        entries = []
        for item in raw if isinstance(raw, list) else []:
            slug = str(item.get("slug", "")).strip()
            date = parse_case_date(str(item.get("date", "")).strip())
            title = str(item.get("title", "")).strip()
            summary = str(item.get("summary", "")).strip()
            category = str(item.get("category", "")).strip()
            case_url = str(item.get("case_url", "")).strip()
            if not slug and case_url:
                m = re.search(r"case-([a-z0-9\-]+)\.html", case_url)
                if m:
                    slug = m.group(1)
            if not slug:
                slug = normalize_slug("", date, title)
            entries.append(
                CaseEntry(
                    date=date,
                    title=title,
                    summary=summary,
                    slug=slug,
                    category=category,
                    thumb=str(item.get("thumbnail", "")).strip(),
                    source_url=str(item.get("source_url", "")).strip(),
                    instagram_url=str(item.get("instagram_url", "")).strip(),
                    highlight_image=str(item.get("thumbnail", "")).strip(),
                )
            )
        return entries, "cases_index.json"

    existing = load_existing_cases()
    return existing, "cases.html fallback"


def find_marker_span(text: str, start: str, end: str) -> tuple[bool, int, str]:
    s = text.find(start)
    e = text.find(end)
    if s == -1 or e == -1 or e < s:
        return False, 0, ""
    inner_start = s + len(start)
    inner = text[inner_start:e]
    return True, len(inner), inner


def build_latest_case_html(data: BlogData) -> str:
    thumb = thumbnail_path_for(data)
    case_url = case_url_for(data)
    instagram_button = []
    if data.instagram_url:
        instagram_button = [
            f'          <li><a href="{data.instagram_url}" target="_blank" rel="noopener" class="button">Instagram</a></li>'
        ]
    parts = [
        '<section class="wrapper style1 align-center ob-latest-case" aria-label="최신 시공사례">',
        '  <div class="inner">',
        '    <p class="eyebrow">최신 시공사례</p>',
        f"    <h2>{data.title}</h2>",
        f"    <p>{data.summary}</p>",
        '    <div class="ob-latest-case-card">',
        f'      <a class="ob-latest-case-img" href="{case_url}" aria-label="{data.title} 상세보기">',
        f'        <img src="{thumb}" alt="{data.title} 썸네일" loading="lazy" />',
        "      </a>",
        '      <div class="ob-latest-case-text">',
        f"        <span>{data.category}</span>",
        f"        <h3>{data.title}</h3>",
        f"        <p>{data.summary}</p>",
        '        <ul class="actions ob-latest-case-actions">',
        f'          <li><a href="{case_url}" class="button primary">상세보기</a></li>',
        *instagram_button,
        "        </ul>",
        "      </div>",
        "    </div>",
        "  </div>",
        "</section>",
    ]
    return "\n".join(parts)


def build_case_highlights_preview(data: BlogData) -> str:
    case_url = case_url_for(data)
    thumb = thumbnail_path_for(data)
    return "\n".join([
        '<article class="case-feature-card">',
        f'  <img src="{thumb}" alt="{data.title}">',
        "  <div>",
        f"    <h2>{data.title}</h2>",
        f"    <p>{data.summary}</p>",
        '    <div class="case-card-links">',
        f'      <a href="{case_url}">상세보기</a>',
        "    </div>",
        "  </div>",
        "</article>",
    ])


def build_case_list_preview(data: BlogData) -> str:
    case_url = case_url_for(data)
    return "\n".join([
        '<div class="case-row" data-category="{category}">'.format(category=data.category),
        f'  <div class="case-date">{data.date.replace("-", ".")}</div>',
        f'  <div class="case-cat"><span>{data.category}</span></div>',
        '  <div class="case-title">',
        f'    <a href="{case_url}">{data.title}</a>',
        f'    <p>{data.summary}</p>',
        "  </div>",
        '  <div class="case-more"><a href="{0}">보기</a></div>'.format(case_url),
        "</div>",
    ])


def build_sitemap_url(data: BlogData) -> str:
    return sitemap_url_for(data)


def replace_between_markers(text: str, start: str, end: str, replacement: str) -> tuple[str, bool]:
    start_index = text.find(start)
    end_index = text.find(end)
    if start_index == -1 or end_index == -1 or end_index < start_index:
        return text, False
    end_pos = end_index + len(end)
    return text[: start_index + len(start)] + "\n" + replacement + "\n" + text[end_index:end_pos] + text[end_pos:], True


def render_index_preview(data: BlogData, latest_case: CaseEntry) -> str:
    source = read_text(ROOT / "index.html")
    rendered, _ = replace_between_markers(source, *MARKERS["index.html"], build_latest_case_html(
        BlogData(
            title=latest_case.title,
            date=latest_case.date,
            year=latest_case.year,
            slug=latest_case.slug,
            category=latest_case.category,
            summary=latest_case.summary,
            source_url=latest_case.source_url,
            instagram_url=latest_case.instagram_url,
            thumbnail=latest_case.thumb,
        )
    ))
    return rendered


def render_cases_preview(cases: list[CaseEntry]) -> str:
    source = read_text(ROOT / "cases.html")
    highlights = "\n".join(build_case_feature_card(entry, is_latest=(idx == 0)) for idx, entry in enumerate(cases[:3]))
    case_list = "\n".join(build_case_row(entry) for entry in cases)
    rendered, _ = replace_between_markers(source, MARKERS["cases.html"][0], MARKERS["cases.html"][1], highlights)
    rendered, _ = replace_between_markers(rendered, MARKERS["cases.html"][2], MARKERS["cases.html"][3], case_list)
    return rendered


def render_sitemap_preview(cases: list[CaseEntry]) -> str:
    source = read_text(ROOT / "sitemap.xml")
    preview_entry = "\n".join(build_sitemap_entry(entry) for entry in cases)
    rendered, _ = replace_between_markers(source, *MARKERS["sitemap.xml"], preview_entry)
    return rendered


def write_cases_index_file(cases: list[CaseEntry], out_path: Path) -> None:
    out_path.write_text(json.dumps([case_entry_to_dict(case) for case in cases], ensure_ascii=False, indent=2), encoding="utf-8")


def backup_cases_index_if_needed(out_path: Path) -> tuple[bool, Path | None]:
    if not out_path.exists():
        return False, None
    backups_dir = ROOT / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    backup_name = f"cases_index_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    backup_path = backups_dir / backup_name
    backup_path.write_text(out_path.read_text(encoding="utf-8"), encoding="utf-8")
    return True, backup_path


def validate_preview_outputs() -> tuple[bool, list[str]]:
    required = [
        PREVIEW_DIR / "index.preview.html",
        PREVIEW_DIR / "cases.preview.html",
        PREVIEW_DIR / "sitemap.preview.xml",
        CASES_INDEX_PREVIEW_PATH,
    ]
    errors: list[str] = []
    for path in required:
        if not path.exists():
            errors.append(f"missing preview file: {path.as_posix()}")
            continue
        if path.stat().st_size == 0:
            errors.append(f"empty preview file: {path.as_posix()}")

    marker_checks = {
        PREVIEW_DIR / "index.preview.html": MARKERS["index.html"],
        PREVIEW_DIR / "cases.preview.html": MARKERS["cases.html"],
        PREVIEW_DIR / "sitemap.preview.xml": MARKERS["sitemap.xml"],
    }
    for path, markers in marker_checks.items():
        if not path.exists():
            continue
        text = read_text(path)
        for marker in markers:
            if marker not in text:
                errors.append(f"missing marker in preview: {marker} ({path.as_posix()})")

    try:
        json.loads(read_text(CASES_INDEX_PREVIEW_PATH))
    except Exception as exc:
        errors.append(f"invalid preview json: {exc}")

    return (len(errors) == 0), errors


def backup_and_apply_live_files() -> tuple[bool, Path | None, list[Path]]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = APPLY_BACKUP_DIR / f"apply_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    backup_files: list[Path] = []
    live_map = {
        ROOT / "index.html": PREVIEW_DIR / "index.preview.html",
        ROOT / "cases.html": PREVIEW_DIR / "cases.preview.html",
        ROOT / "sitemap.xml": PREVIEW_DIR / "sitemap.preview.xml",
        CASES_INDEX_PATH: CASES_INDEX_PREVIEW_PATH,
    }

    for live_path, preview_path in live_map.items():
        if live_path.exists():
            backup_target = backup_dir / live_path.name
            backup_target.write_text(live_path.read_text(encoding="utf-8"), encoding="utf-8")
            backup_files.append(backup_target)
        live_path.write_text(read_text(preview_path), encoding="utf-8")

    return True, backup_dir, backup_files


def parse_args() -> dict[str, bool]:
    import argparse

    parser = argparse.ArgumentParser(description="오박사 홈페이지 preview/인덱스 동기화")
    parser.add_argument("--write-index", action="store_true", help="preview 대신 cases_index.json을 실제로 갱신")
    parser.add_argument("--apply", action="store_true", help="preview 결과를 실제 운영 파일에 반영")
    args = parser.parse_args()
    return {"write_index": bool(args.write_index), "apply": bool(args.apply)}


def write_preview_files(data: BlogData, cases: list[CaseEntry]) -> list[Path]:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    index_path = PREVIEW_DIR / "index.preview.html"
    cases_path = PREVIEW_DIR / "cases.preview.html"
    sitemap_path = PREVIEW_DIR / "sitemap.preview.xml"
    index_json_path = CASES_INDEX_PREVIEW_PATH
    index_path.write_text(render_index_preview(data, cases[0] if cases else CaseEntry(date=data.date, title=data.title, summary=data.summary, slug=case_folder_slug(data), category=data.category, thumb=data.thumbnail, source_url=data.source_url, instagram_url=data.instagram_url)), encoding="utf-8")
    cases_path.write_text(render_cases_preview(cases), encoding="utf-8")
    sitemap_path.write_text(render_sitemap_preview(cases), encoding="utf-8")
    index_json_path.write_text(json.dumps([case_entry_to_dict(case) for case in cases], ensure_ascii=False, indent=2), encoding="utf-8")
    return [index_json_path, index_path, cases_path, sitemap_path]


def preview_marker_block(name: str, path: Path, markers: Iterable[str]) -> None:
    text = read_text(path)
    print(f"[{name}] marker checks")
    marker_list = list(markers)
    if len(marker_list) == 2:
        start, end = marker_list
        found, length, _ = find_marker_span(text, start, end)
        print(f"- {start}: {start in text}")
        print(f"- {end}: {end in text}")
        print(f"- span_length: {length if found else 0}")
    else:
        start1, end1, start2, end2 = marker_list
        found1, length1, _ = find_marker_span(text, start1, end1)
        found2, length2, _ = find_marker_span(text, start2, end2)
        print(f"- {start1}: {start1 in text}")
        print(f"- {end1}: {end1 in text}")
        print(f"- span_length: {length1 if found1 else 0}")
        print(f"- {start2}: {start2 in text}")
        print(f"- {end2}: {end2 in text}")
        print(f"- span_length: {length2 if found2 else 0}")


def main() -> int:
    args = parse_args()
    mode = "apply" if args["apply"] else ("write-index" if args["write_index"] else "preview")
    ok, data, source_path = load_blog_data()
    print(f"mode: {mode}")
    print(f"blog_fetch_result.json load success: {ok}")
    if source_path:
        print(f"blog_fetch_result.json path: {source_path}")
    print(f"title: {data.title}")
    print(f"date: {data.date}")
    print(f"year: {data.year}")
    print(f"slug: {data.slug}")
    print(f"category: {data.category}")
    print(f"summary: {data.summary}")
    print(f"source_url: {data.source_url}")
    print(f"instagram_url: {data.instagram_url}")
    print(f"SITE_BASE_URL: {SITE_BASE_URL}")
    print(f"case_url: {case_url_for(data) if data.slug else ''}")
    print(f"sitemap_url: {sitemap_url_for(data) if data.slug else ''}")

    if not data.title:
        print("warning: title is missing")
    if not data.date:
        print("warning: date is missing; current year fallback will be used")
    if not data.slug:
        print("warning: slug is missing; auto-generated fallback may be used")
    if not data.category:
        print("warning: category is missing")
    if not data.summary:
        print("warning: summary is missing")
    if not data.source_url:
        print("warning: input_url/url is missing")

    for filename, markers in MARKERS.items():
        path = ROOT / filename
        if not path.exists():
            print(f"[{filename}] exists: False")
            continue
        print(f"[{filename}] exists: True")
        preview_marker_block(filename, path, markers)

    existing_cases, data_source = load_cases_index()
    new_case = make_case_entry_from_blog(data)
    merged_cases, duplicate_found, replaced = merge_cases(existing_cases, new_case)
    preview_files = write_preview_files(data, merged_cases)
    thumbnail_used = bool(data.thumbnail)

    cases_index_exists_before = CASES_INDEX_PATH.exists()
    backup_created = False
    backup_path = None
    if args["write_index"]:
        backup_created, backup_path = backup_cases_index_if_needed(CASES_INDEX_PATH)
        write_cases_index_file(merged_cases, CASES_INDEX_PATH)

    if args["apply"]:
        preview_ok, preview_errors = validate_preview_outputs()
        if not preview_ok:
            print("완료 메시지: preview 검증 실패로 실제 반영 중단")
            for error in preview_errors:
                print(f"- {error}")
            return 1
        backup_created, backup_path, backup_files = backup_and_apply_live_files()
        print(f"backup path: {backup_path.as_posix() if backup_path else ''}")
        if backup_files:
            print("backup files:")
            for backup_file in backup_files:
                print(backup_file.as_posix())

    print(f"cases_index.json 기존 존재 여부: {'예' if cases_index_exists_before else '아니오'}")
    print(f"cases_index.json 존재 여부: {'예' if CASES_INDEX_PATH.exists() else '아니오'}")
    print(f"기존 데이터 소스: {data_source}")
    print(f"기존 사례 수: {len(existing_cases)}")
    print(f"신규 사례 추가 여부: {'예' if new_case.case_url not in {case.case_url for case in existing_cases} else '아니오'}")
    print(f"중복 갱신 여부: {'예' if replaced or duplicate_found else '아니오'}")
    print(f"정렬 후 전체 사례 수: {len(merged_cases)}")
    print(f"하이라이트 사례 수: {min(3, len(merged_cases))}")
    print(f"sitemap URL 수: {len({case.sitemap_url for case in merged_cases})}")
    print(f"thumbnail 사용 여부: {'예' if thumbnail_used else '아니오'}")
    print(f"backup 생성 여부: {'예' if backup_created else '아니오'}")
    if backup_path:
        print(f"backup 파일: {backup_path.as_posix()}")
    print(f"저장된 cases_index.json 경로: {CASES_INDEX_PATH.as_posix()}")
    print(f"preview JSON 경로: {CASES_INDEX_PREVIEW_PATH.as_posix()}")
    print("preview files:")
    for preview_file in preview_files:
        print(preview_file.as_posix())
    print(f"generated case_url: {new_case.case_url}")
    print(f"generated sitemap_url: {new_case.sitemap_url}")
    print("완료 메시지: preview 생성 완료" if not args["apply"] else "완료 메시지: 실제 운영 파일 반영 완료")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
