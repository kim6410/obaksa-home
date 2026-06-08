from __future__ import annotations

import html
import json
import os
import re
import shutil
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent
SITE_BASE_URL = os.getenv("SITE_BASE_URL", "https://kim6410.github.io/obaksa-home")
BLOG_FETCH_CANDIDATES = [
    ROOT / "blog_fetch_result.json",
    ROOT.parent / "blog_fetch_result.json",
    ROOT / "output" / "blog_fetch_result.json",
    ROOT / "data" / "blog_fetch_result.json",
    ROOT / "tmp" / "blog_fetch_result.json",
]
MAX_DETAIL_IMAGES = 10
IMAGE_REJECT_KEYWORDS = {
    "map",
    "profile",
    "sticker",
    "emoji",
    "icon",
    "logo",
    "kakao",
    "naver_map",
}

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
CASE_DETAIL_TEMPLATE_PATH = ROOT / "templates" / "case-detail-template.html"
FORCE_REGENERATE_DETAIL_PATHS: set[Path] = set()


@dataclass
class BlogData:
    title: str = ""
    date: str = ""
    year: str = ""
    slug: str = ""
    category: str = ""
    summary: str = ""
    content: str = ""
    source_url: str = ""
    instagram_url: str = ""
    images: list[str] | None = None
    image_plan: list[dict[str, object]] | None = None
    thumbnail: str = ""
    source_path: Path | None = None


@dataclass
class CaseEntry:
    date: str
    title: str
    summary: str
    slug: str
    category: str = ""
    url: str = ""
    thumb: str = ""
    source_url: str = ""
    instagram_url: str = ""
    highlight_image: str = ""
    added_at: str = ""

    @property
    def year(self) -> str:
        return extract_year(self.date)

    @property
    def case_url(self) -> str:
        if self.url:
            return self.url.lstrip("/")
        return f"cases/{self.year}/case-{self.slug}.html"

    @property
    def sitemap_url(self) -> str:
        relative = self.case_url.lstrip("/")
        return f"{SITE_BASE_URL.rstrip('/')}/{relative}"

    @property
    def image_folder(self) -> Path:
        if self.url.endswith("/"):
            return ROOT / "cases" / self.year / self.slug
        return ROOT / "assets" / "images" / "cases" / self.year / self.date[5:7] / self.slug

    @property
    def case_folder(self) -> Path:
        if self.url.endswith("/"):
            return ROOT / "cases" / self.year / self.slug
        return ROOT / "cases" / self.year

    @property
    def detail_path(self) -> Path:
        if self.url.endswith("/"):
            return self.case_folder / "index.html"
        return self.case_folder / f"case-{self.slug}.html"

    @property
    def markdown_path(self) -> Path:
        if self.url.endswith("/"):
            return self.case_folder / "index.md"
        return self.case_folder / f"case-{self.slug}.md"

    @property
    def thumbnail_path(self) -> Path:
        if self.url.endswith("/"):
            return self.case_folder / "thumb.jpg"
        return self.case_folder / f"{self.slug}.jpg"


@dataclass
class ImageItem:
    path: Path
    alt: str
    caption: str = ""
    reviewed: bool = False


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
                content=str(data.get("content", "")).strip(),
                source_url=source_url,
                instagram_url=str(data.get("instagram_url", "")).strip(),
                images=list(data.get("images") or []),
                image_plan=list(data.get("image_plan") or data.get("image_manifest") or data.get("image_alt_plan") or []),
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
        if existing_slug.startswith("case-"):
            return existing_slug
        return f"case-{existing_slug}"
    base = title or "new-case"
    cleaned = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    cleaned = cleaned.lower()
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in cleaned)
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    cleaned = cleaned[:48].strip("-")
    year = extract_year(date_text)
    if cleaned:
        return f"case-{year}-{cleaned}"
    return f"case-{year}-new-case"


def case_folder_slug(data: BlogData) -> str:
    return normalize_slug(data.slug, data.date, data.title)


def case_url_for(data: BlogData) -> str:
    slug = case_folder_slug(data)
    year = data.year or extract_year(data.date)
    return f"cases/{year}/{slug}/"


def sitemap_url_for(data: BlogData) -> str:
    return f"{SITE_BASE_URL.rstrip('/')}/{case_url_for(data).lstrip('/')}"


def thumbnail_path_for(data: BlogData) -> str:
    return f"cases/{data.year or extract_year(data.date)}/{case_folder_slug(data)}/thumb.jpg"


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
        slug_match = re.search(r"case-([a-z0-9\-]+)(?:\.html|/)", href)
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
                url=href if href.startswith("/") else f"/{href.lstrip('/')}",
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
    ordered = sorted(
        merged.values(),
        key=lambda item: (item.date, item.added_at, item.slug),
        reverse=True,
    )
    return ordered, duplicate, replaced


def build_case_feature_card(entry: CaseEntry, is_latest: bool = False) -> str:
    img = entry.highlight_image or entry.thumb or "/images/gallery/case_hero.jpg"
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


def gather_case_images(entry: CaseEntry) -> list[Path]:
    if not entry.image_folder.exists():
        return []
    allowed = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    images = []
    for path in sorted(entry.image_folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in allowed:
            continue
        lower = path.name.lower()
        if any(keyword in lower for keyword in IMAGE_REJECT_KEYWORDS):
            continue
        images.append(path)
    return images[:MAX_DETAIL_IMAGES]


def case_image_caption(entry: CaseEntry, index: int, total: int) -> str:
    if "차단기" in entry.title or "정전" in entry.title or entry.category == "전기수리":
        captions = [
            "정전 원인을 확인하기 위해 분전반 내부 상태를 먼저 점검했습니다.",
            "누전과 단락 가능성을 확인하며 각 회로의 흐름을 살폈습니다.",
            "계측기로 전류 흐름을 확인하면서 이상 구간을 좁혀갔습니다.",
            "차단기와 배선 연결 상태를 가까이에서 다시 확인했습니다.",
            "분전반 전체 구성을 살피며 교체 후 안정성을 점검했습니다.",
            "콘센트 구간까지 확인해 다른 이상이 남아 있지 않은지 살폈습니다.",
            "교체 작업 후 차단기 동작과 전기 공급 상태를 최종 확인했습니다.",
        ]
    else:
        captions = [
            "현장 상태를 먼저 살펴본 사진입니다.",
            "문제 원인이 되는 부분을 자세히 확인한 모습입니다.",
            "필요한 부위를 보강하고 정리하는 과정입니다.",
            "현장 상황에 맞춰 다시 고정하는 작업입니다.",
            "틈새와 마감 상태를 함께 점검한 모습입니다.",
            "작업 후 흔들림이나 불안 요소가 없는지 확인했습니다.",
            "현장 최종 확인 후 안전하게 마무리한 모습입니다.",
        ]
    if total <= 1:
        return "현장 확인 후 정리된 모습입니다."
    if index < len(captions):
        return captions[index]
    return f"작업 과정 사진 {index + 1}"


def _story_candidates(blog: BlogData) -> list[str]:
    source = blog.content or ""
    blocks = [re.sub(r"\s+", " ", line).strip() for line in source.splitlines()]
    if len(blocks) < 4:
        blocks = [
            re.sub(r"\s+", " ", part).strip()
            for part in re.split(r"(?<=[.!?。])\s+|\s{2,}", source)
            if part and part.strip()
        ]
    title_tokens = [token for token in re.split(r"[\s,，.·/]+", blog.title or "") if len(token) >= 3]
    candidates: list[str] = []
    for line in blocks:
        if not line or len(line) < 18 or line.startswith("#"):
            continue
        if blog.title and line == blog.title:
            continue
        if title_tokens:
            overlap = sum(1 for token in title_tokens[:6] if token and token in line)
            if overlap >= 3:
                continue
        if line not in candidates:
            candidates.append(line)
    return candidates


def _pick_story_line(candidates: list[str], keywords: tuple[str, ...]) -> str:
    for line in candidates:
        if any(keyword in line for keyword in keywords):
            return line
    return ""


def _trim_story_snippet(text: str, limit: int = 52) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip("“”\"'<>")
    if len(text) <= limit:
        return text
    return text[:limit].rstrip(" ,.·/:-") + "..."


def build_case_story(blog: BlogData) -> str:
    title = blog.title or "현장 점검 사례"
    is_electric = any(token in title for token in ("정전", "차단기", "분전반", "전기")) or blog.category == "전기수리"
    if is_electric:
        paragraphs = [
            "<p>호계동 교육원에서 전체 전기가 멈췄다는 연락을 받고 현장으로 갔습니다. 수업이 진행되는 공간은 조명과 콘센트가 바로 복구되어야 하므로, 단순히 스위치를 다시 올리는 방식으로는 해결할 수 없다고 판단했습니다.</p>",
            "<p>먼저 분전반을 열어 메인 차단기와 각 회로의 흐름을 확인했습니다. 전기가 끊긴 원인이 외부 공급 문제가 아니라 차단기 내부와 연결부 쪽 이상으로 이어질 가능성이 보여, 무리한 통전보다 원인 확인을 우선했습니다.</p>",
            "<p>계측기로 누전 여부와 단락 가능성을 확인하면서 문제가 되는 구간을 좁혀갔습니다. 오래 사용한 차단기는 겉으로는 멀쩡해 보여도 내부 접점이 약해질 수 있어, 현장 사용량과 회로 구성을 함께 보고 교체 범위를 정했습니다.</p>",
            "<p>기존 누전차단기를 정리한 뒤 현장에 맞는 규격으로 교체하고, 배선 체결 상태를 다시 맞췄습니다. 교체 후에는 바로 마무리하지 않고 교육원 내부 콘센트와 분전반 동작을 순서대로 확인해 같은 문제가 반복될 가능성을 줄였습니다.</p>",
            "<p>전원을 다시 올렸을 때 조명과 전기 사용이 정상으로 돌아오는 것을 확인했습니다. 전기 문제는 보이지 않는 곳에서 시작되는 경우가 많기 때문에, 정전이나 차단기 내려감이 반복된다면 빠르게 점검받는 것이 가장 안전합니다.</p>",
        ]
    else:
        paragraphs = [
            f"<p>{blog.summary or title}</p>",
            "<p>현장에 도착한 뒤에는 눈에 보이는 증상만 보지 않고, 문제가 시작된 위치와 주변 상태를 함께 확인했습니다. 작은 불편처럼 보여도 원인을 놓치면 같은 문제가 다시 반복될 수 있기 때문입니다.</p>",
            "<p>작업은 필요한 부분을 먼저 정리하고, 현장 상태에 맞춰 순서대로 진행했습니다. 무리하게 넓은 범위를 건드리기보다 실제 원인이 되는 부분을 정확히 잡는 데 집중했습니다.</p>",
            "<p>마무리 단계에서는 사용 중 불편이 남지 않도록 다시 점검했습니다. 고객님이 바로 안심하고 사용할 수 있는 상태인지 확인한 뒤 현장을 정리했습니다.</p>",
        ]
    return "\n        ".join(paragraphs)


def build_summary_markdown_body(entry: CaseEntry, blog: BlogData, summary: str, image_items: list[ImageItem]) -> str:
    """사용자 요약문 중심으로 정리된 본문을 만든다.

    블로그 원문은 참고 데이터일 뿐, 정리되지 않은 원문 덤프를 그대로 상세페이지에 넣지 않는다.
    이미지 배열과 alt는 image_manifest.json 또는 blog_fetch_result.json의 image_plan을 우선한다.
    """
    lines: list[str] = []
    lines += [
        "## 현장 확인",
        "현장에서는 눈에 보이는 증상만 확인하지 않고, 문제가 시작된 위치와 주변 상태를 함께 살폈습니다.",
        "작은 불편처럼 보여도 원인을 놓치면 같은 문제가 다시 반복될 수 있기 때문입니다.",
        "",
    ]
    if image_items:
        first = image_items[0]
        lines += [f"![{first.alt}](./{first.path.name})", ""]

    lines += [
        "## 작업 과정",
        "작업은 필요한 부분을 먼저 정리하고, 현장 상태에 맞춰 순서대로 진행했습니다.",
        "무리하게 넓은 범위를 건드리기보다 실제 원인이 되는 부분을 정확히 잡는 데 집중했습니다.",
        "",
    ]
    if len(image_items) > 1:
        second = image_items[1]
        lines += [f"![{second.alt}](./{second.path.name})", ""]

    for item in image_items[2:-1]:
        lines += [f"![{item.alt}](./{item.path.name})", ""]

    lines += [
        "## 마무리 점검",
        "마무리 단계에서는 사용 중 불편이 남지 않도록 다시 점검했습니다.",
        "고객님이 바로 안심하고 사용할 수 있는 상태인지 확인한 뒤 현장을 정리했습니다.",
    ]

    if len(image_items) > 2:
        last = image_items[-1]
        lines += ["", f"![{last.alt}](./{last.path.name})", ""]

    lines += [
        "## 상담 안내",
        "비슷한 증상이나 확인이 필요한 부분이 있다면 전화로 바로 상담할 수 있습니다.",
    ]
    return "\n".join(lines).strip() + "\n"


def build_case_markdown(entry: CaseEntry, blog: BlogData | None, summary: str, images: list[Path]) -> str:
    blog = blog or BlogData(title=entry.title, date=entry.date, year=entry.year, slug=entry.slug, category=entry.category, summary=summary)
    blog.summary = summary
    image_items = build_image_items(entry, images, blog)
    markdown_images = [f"./{item.path.name}" for item in image_items]
    tags = [
        "울산집수리",
        entry.category or "시공사례",
        "오박사만능인테리어",
    ]
    front_matter = [
        "---",
        f'title: "{entry.title}"',
        f'description: "{summary}"',
        f'date: "{entry.date}"',
        f'category: "{entry.category or "시공사례"}"',
        f'slug: "{entry.slug}"',
        f'canonical: "{entry.sitemap_url}"',
        'thumbnail: "./thumb.jpg"',
        "images:",
    ]
    for image in markdown_images:
        front_matter.append(f"  - \"{image}\"")
    front_matter.append("tags:")
    for tag in tags:
        front_matter.append(f'  - "{tag}"')
    front_matter.append("---")

    raw_content = (blog.content or "").strip()
    if raw_content and is_curated_markdown_content(raw_content):
        body, placeholder_errors = normalize_markdown_image_placeholders(raw_content, [item.path for item in image_items])
        if placeholder_errors:
            raise ValueError("; ".join(placeholder_errors))
    else:
        body = build_summary_markdown_body(entry, blog, summary, image_items)

    body = re.sub(
        r"(?ms)^## 현장 요약\s+.*?(?=^## 현장 확인\b)",
        "",
        body,
    )

    return "\n".join(front_matter + ["", body]).strip() + "\n"

def parse_markdown_front_matter(markdown_text: str) -> tuple[dict[str, str], str]:
    text = markdown_text.strip()
    if not text.startswith("---"):
        return {}, markdown_text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, markdown_text
    header = parts[1].strip().splitlines()
    body = parts[2].lstrip("\n")
    meta: dict[str, str] = {}
    current_key = ""
    list_key = ""
    for line in header:
        if not line.strip():
            continue
        if line.startswith("  - "):
            value = line[4:].strip().strip('"')
            if list_key:
                meta.setdefault(list_key, "")
                meta[list_key] += ("\n" if meta[list_key] else "") + value
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip('"')
            current_key = key
            list_key = key if value == "" else ""
            if value:
                meta[key] = value
            else:
                meta[key] = ""
    return meta, body


def _html_escape(value: str) -> str:
    return html.escape(str(value or ""), quote=True)


def _is_html_line(line: str) -> bool:
    return bool(re.match(r"^</?(p|div|section|article|figure|img|ul|ol|li|h[1-6]|hr|br|blockquote|table|a|span)\b", line.strip(), re.I))


def _image_filename(src: str) -> str:
    src = (src or "").strip().split("?", 1)[0].split("#", 1)[0]
    return Path(src).name


def _image_sources_in_markdown(markdown_text: str) -> set[str]:
    return {_image_filename(match.group(2)) for match in re.finditer(r"!\[(.*?)\]\((.*?)\)", markdown_text or "")}


def is_curated_markdown_content(markdown_text: str) -> bool:
    """사용자가 정리한 Markdown 원고인지, 블로그 원문 덤프인지 구분한다.

    네이버 원문 수집 텍스트를 그대로 HTML에 밀어 넣으면 한 문단으로 뭉개지는 문제가 생긴다.
    제목/소제목/이미지 마크다운이 있는 경우만 '정리된 원고'로 보고 그대로 사용한다.
    """
    text = markdown_text or ""
    return bool(
        re.search(r"(?m)^#{1,3}\s+", text)
        or re.search(r"!\[.*?\]\(.*?\)", text)
        or re.search(r"(?m)^![^\[\n].+?$", text)
    )


def image_manifest_path(entry: CaseEntry) -> Path:
    return entry.case_folder / "image_manifest.json"


def load_image_manifest(entry: CaseEntry, blog: BlogData | None = None) -> list[dict[str, object]]:
    if blog and blog.image_plan:
        return list(blog.image_plan)
    path = image_manifest_path(entry)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(raw, dict):
        raw = raw.get("images") or raw.get("items") or []
    return list(raw) if isinstance(raw, list) else []


def write_image_review_todo(entry: CaseEntry, images: list[Path]) -> Path | None:
    """Codex/사용자가 눈으로 보고 순서와 alt를 확정할 수 있는 TODO 파일을 만든다."""
    if not images:
        return None
    todo_path = entry.case_folder / "image_manifest.todo.json"
    if todo_path.exists() or image_manifest_path(entry).exists():
        return todo_path
    todo_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "note": "이미지를 눈으로 확인한 뒤 order/use/alt/caption/reviewed 값을 확정하고 파일명을 image_manifest.json으로 바꾸세요.",
        "images": [
            {
                "file": image.name,
                "order": idx + 1,
                "use": idx < MAX_DETAIL_IMAGES,
                "alt": _contextual_alt(entry, "", image.name),
                "caption": _contextual_alt(entry, "", image.name),
                "reviewed": False,
            }
            for idx, image in enumerate(images[:MAX_DETAIL_IMAGES])
        ],
    }
    todo_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return todo_path


def build_image_items(entry: CaseEntry, images: list[Path], blog: BlogData | None = None) -> list[ImageItem]:
    """이미지 순서와 alt를 만든다.

    우선순위:
    1. image_manifest.json 또는 blog_fetch_result.json의 image_plan
    2. 파일명 순서 + 문맥형 자동 alt

    실제 apply 품질은 1번을 권장한다. 자동 alt는 preview/초안용 안전망이다.
    """
    image_map = {image.name: image for image in images}
    plan = load_image_manifest(entry, blog)
    items: list[ImageItem] = []
    if plan:
        normalized_plan = []
        for raw in plan:
            if not isinstance(raw, dict):
                continue
            file_name = str(raw.get("file") or raw.get("name") or raw.get("src") or "").strip()
            file_name = _image_filename(file_name)
            if not file_name or file_name not in image_map:
                continue
            use = raw.get("use", True)
            if str(use).lower() in {"false", "0", "no", "n"}:
                continue
            order = raw.get("order", 999)
            try:
                order_int = int(order)
            except Exception:
                order_int = 999
            normalized_plan.append((order_int, raw, file_name))
        for _, raw, file_name in sorted(normalized_plan, key=lambda item: item[0]):
            path = image_map[file_name]
            alt = str(raw.get("alt") or raw.get("caption") or "").strip()
            caption = str(raw.get("caption") or alt).strip()
            reviewed = bool(raw.get("reviewed") or raw.get("checked") or raw.get("confirmed"))
            final_alt = _contextual_alt(entry, alt, path.name)
            items.append(ImageItem(path=path, alt=final_alt, caption=caption or final_alt, reviewed=reviewed))
        return items[:MAX_DETAIL_IMAGES]

    write_image_review_todo(entry, images)
    return [
        ImageItem(
            path=image,
            alt=_contextual_alt(entry, "", image.name),
            caption=_contextual_alt(entry, "", image.name),
            reviewed=False,
        )
        for image in images[:MAX_DETAIL_IMAGES]
    ]


def has_reviewed_image_manifest(entry: CaseEntry, blog: BlogData | None, images: list[Path]) -> bool:
    plan = load_image_manifest(entry, blog)
    if not plan:
        write_image_review_todo(entry, images)
        return False
    items = build_image_items(entry, images, blog)
    if not items:
        return False
    for item in items:
        alt = item.alt.strip()
        if not item.reviewed:
            return False
        if len(alt) < 12:
            return False
        if re.match(r"작업 과정 사진 \d+", alt):
            return False
        if alt in {
            "현장 상태를 먼저 살펴본 사진입니다.",
            "문제 원인이 되는 부분을 자세히 확인한 모습입니다.",
            "필요한 부위를 보강하고 정리하는 과정입니다.",
        }:
            return False
    return True


def _contextual_alt(entry: CaseEntry | None, raw_alt: str, src: str = "") -> str:
    raw_alt = re.sub(r"\s+", " ", str(raw_alt or "")).strip()
    generic = {
        "",
        "현장 상태를 먼저 살펴본 사진입니다.",
        "문제 원인이 되는 부분을 자세히 확인한 모습입니다.",
        "필요한 부위를 보강하고 정리하는 과정입니다.",
        "현장 상황에 맞춰 다시 고정하는 작업입니다.",
        "틈새와 마감 상태를 함께 점검한 모습입니다.",
        "작업 후 흔들림이나 불안 요소가 없는지 확인했습니다.",
        "현장 최종 확인 후 안전하게 마무리한 모습입니다.",
    }
    if raw_alt and raw_alt not in generic and not re.match(r"작업 과정 사진 \d+", raw_alt):
        if entry and entry.title and raw_alt not in entry.title and len(raw_alt) < 28:
            return f"{entry.title} {raw_alt}"
        return raw_alt
    if not entry:
        return raw_alt or _image_filename(src) or "시공 사례 이미지"
    title = entry.title or "오박사만능인테리어 시공 사례"
    category = entry.category or "집수리"
    name = _image_filename(src)
    number_match = re.search(r"(\d+)", name)
    number = int(number_match.group(1)) if number_match else 0
    if number <= 1:
        suffix = "현장 상태 확인"
    elif number == 2:
        suffix = "문제 원인 점검"
    elif number == 3:
        suffix = "작업 과정"
    elif number == 4:
        suffix = "보강 및 정리 과정"
    elif number == 5:
        suffix = "마감 상태 확인"
    else:
        suffix = "완료 후 최종 점검"
    return f"{title} {category} {suffix}"


def normalize_markdown_image_placeholders(markdown_text: str, images: list[Path] | None = None) -> tuple[str, list[str]]:
    image_names = [f"./{image.name}" for image in (images or [])]
    errors: list[str] = []
    cursor = 0

    def replace_line(match: re.Match[str]) -> str:
        nonlocal cursor
        alt = match.group(1).strip()
        if cursor >= len(image_names):
            errors.append(f"이미지 자리표시가 실제 이미지 수보다 많습니다: {alt}")
            return match.group(0)
        src = image_names[cursor]
        cursor += 1
        return f"![{alt}]({src})"

    normalized = re.sub(r"(?m)^!([^\[\n].+?)\s*$", replace_line, markdown_text or "")
    return normalized, errors


def markdown_text_to_html(markdown_text: str, entry: CaseEntry | None = None) -> str:
    output: list[str] = []
    lines = (markdown_text or "").splitlines()
    paragraph: list[str] = []
    list_items: list[str] = []
    skipped_leading_title = False

    def flush_paragraph() -> None:
        if paragraph:
            output.append(f"<p>{_html_escape(' '.join(paragraph).strip())}</p>")
            paragraph.clear()

    def flush_list() -> None:
        if list_items:
            output.append("<ul>")
            for item in list_items:
                output.append(f"  <li>{_html_escape(item)}</li>")
            output.append("</ul>")
            list_items.clear()

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            flush_list()
            continue
        if line == "---":
            flush_paragraph()
            flush_list()
            output.append("<hr />")
            continue
        if _is_html_line(line):
            flush_paragraph()
            flush_list()
            output.append(line)
            continue
        if line.startswith("### "):
            flush_paragraph()
            flush_list()
            output.append(f"<h3>{_html_escape(line[4:].strip())}</h3>")
            continue
        if line.startswith("## "):
            flush_paragraph()
            flush_list()
            output.append(f"<h2>{_html_escape(line[3:].strip())}</h2>")
            continue
        if line.startswith("# "):
            flush_paragraph()
            flush_list()
            skipped_leading_title = True
            continue
            continue
        if line.startswith("- "):
            flush_paragraph()
            list_items.append(line[2:].strip())
            continue
        img_match = re.match(r"!\[(.*?)\]\((.*?)\)", line)
        if img_match:
            flush_paragraph()
            flush_list()
            raw_alt, src = img_match.groups()
            alt = _contextual_alt(entry, raw_alt, src)
            output.append("<figure>")
            output.append(f'  <img src="{_html_escape(src)}" alt="{_html_escape(alt)}" loading="lazy" />')
            output.append(f"  <figcaption>{_html_escape(alt)}</figcaption>")
            output.append("</figure>")
            continue
        paragraph.append(line)

    flush_paragraph()
    flush_list()
    return "\n".join(output)


def detail_image_rel_path(entry: CaseEntry, image_path: Path) -> str:
    return f"/cases/{entry.year}/{entry.slug}/{image_path.name}"


def render_case_detail_template(
    entry: CaseEntry,
    images: list[Path],
    blog: BlogData | None = None,
    summary: str = "",
    markdown_body: str = "",
) -> str:
    template = read_text(CASE_DETAIL_TEMPLATE_PATH)
    chosen_summary = summary or (blog.summary if blog else "") or entry.summary or entry.title
    hero_image = detail_image_rel_path(entry, images[0]) if images else (entry.thumb if entry.thumb else "/images/gallery/case_hero.jpg")
    story_blog = blog or BlogData(title=entry.title, date=entry.date, year=entry.year, slug=entry.slug, category=entry.category, summary=chosen_summary, source_url=entry.source_url, instagram_url=entry.instagram_url)
    story_blog.summary = chosen_summary

    image_items = build_image_items(entry, images, blog)

    # index.md가 단일 원본이다. markdown_body가 있으면 그것을 우선 렌더링한다.
    source_markdown = (markdown_body or "").strip()
    if not source_markdown:
        raw_content = (blog.content or "").strip() if blog else ""
        if raw_content and is_curated_markdown_content(raw_content):
            source_markdown, placeholder_errors = normalize_markdown_image_placeholders(raw_content, [item.path for item in image_items])
            if placeholder_errors:
                raise ValueError("; ".join(placeholder_errors))
        else:
            source_markdown = build_summary_markdown_body(entry, story_blog, chosen_summary, image_items)

    content_image_names = _image_sources_in_markdown(source_markdown)
    has_inline_images = bool(content_image_names)
    case_story_html = markdown_text_to_html(source_markdown, entry)

    gallery_items: list[str] = []
    # 본문에 이미지가 들어가 있으면 같은 이미지를 하단 갤러리에 중복 출력하지 않는다.
    gallery_candidates = [] if has_inline_images else image_items
    for item in gallery_candidates:
        rel = detail_image_rel_path(entry, item.path)
        label = item.caption or item.alt
        gallery_items.append(
            "\n".join([
                "<figure>",
                f'  <img src="{_html_escape(rel)}" alt="{_html_escape(item.alt)}" loading="lazy" />',
                f"  <figcaption>{_html_escape(label)}</figcaption>",
                "</figure>",
            ])
        )
    if not gallery_items and not has_inline_images:
        label = _contextual_alt(entry, f"{entry.title} 대표 이미지", hero_image)
        gallery_items.append(
            "\n".join([
                "<figure>",
                f'  <img src="{_html_escape(hero_image)}" alt="{_html_escape(label)}" loading="lazy" />',
                f"  <figcaption>{_html_escape(label)}</figcaption>",
                "</figure>",
            ])
        )
    instagram_button = ""
    if entry.instagram_url:
        instagram_button = f'<a class="button case-btn-white" href="{entry.instagram_url}" target="_blank" rel="noopener">인스타 보기</a>'
    source_url = (blog.source_url if blog and blog.source_url else entry.source_url)
    instagram_url = (blog.instagram_url if blog and blog.instagram_url else entry.instagram_url)
    source_button = f'<a class="button case-btn-white" href="{source_url or "#"}" target="_blank" rel="noopener">블로그 원문 보기</a>' if source_url else ""
    if instagram_url:
        instagram_button = f'<a class="button case-btn-white" href="{instagram_url}" target="_blank" rel="noopener">인스타 보기</a>'
    absolute_canonical = entry.sitemap_url
    absolute_og_image = f"{SITE_BASE_URL.rstrip('/')}{hero_image}" if hero_image.startswith("/") else f"{SITE_BASE_URL.rstrip('/')}/{hero_image.lstrip('/')}"
    replacements = {
        "{{TITLE}}": entry.title,
        "{{DATE}}": entry.date,
        "{{CATEGORY}}": entry.category or "시공사례",
        "{{SUMMARY}}": chosen_summary,
        "{{SOURCE_URL}}": source_url or "#",
        "{{SOURCE_BUTTON}}": source_button,
        "{{INSTAGRAM_BUTTON}}": instagram_button,
        "{{GALLERY_IMAGES}}": "\n        ".join(gallery_items),
        "{{BREADCRUMB_TITLE}}": entry.title,
        "{{META_DESCRIPTION}}": chosen_summary,
        "{{OG_IMAGE}}": absolute_og_image,
        "{{CANONICAL_URL}}": absolute_canonical,
        "{{THUMBNAIL}}": hero_image,
        "{{THUMBNAIL_TEXT}}": entry.thumb or "없음",
        "{{TAGS}}": ",".join(filter(None, [entry.category, entry.title, entry.slug.replace("-", ",")])),
        "{{SLUG}}": entry.slug,
        "{{CASE_URL}}": entry.case_url,
        "{{CASE_STORY}}": case_story_html,
        "{{GALLERY_SECTION}}": "",
    }
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    return rendered

def build_case_detail_html(entry: CaseEntry, images: list[Path], blog: BlogData | None = None, summary: str = "", markdown_body: str = "") -> str:
    return render_case_detail_template(entry, images, blog, summary, markdown_body)


def gather_case_images_for_blog(entry: CaseEntry, blog: BlogData | None = None) -> list[Path]:
    if blog and blog.images:
        selected: list[Path] = []
        for rel_path in blog.images:
            normalized = str(rel_path).lstrip("/\\")
            path = ROOT / normalized
            if path.exists() and path.is_file():
                selected.append(path)
        if selected:
            return selected[:MAX_DETAIL_IMAGES]
    return gather_case_images(entry)


def collect_missing_case_details(cases: list[CaseEntry]) -> list[CaseEntry]:
    return [
        case
        for case in cases
        if case.case_url.endswith("/") and (not case.detail_path.exists() or not case.markdown_path.exists())
    ]


def ensure_case_thumbnail(entry: CaseEntry, images: list[Path]) -> None:
    if not images:
        return
    thumb_path = entry.thumbnail_path
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    if thumb_path.exists():
        return
    first_image = images[0]
    shutil.copyfile(first_image, thumb_path)


def write_case_markdown(entry: CaseEntry, blog: BlogData | None, summary: str, images: list[Path]) -> Path:
    markdown_path = entry.markdown_path
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_text = build_case_markdown(entry, blog, summary, images)
    markdown_path.write_text(markdown_text, encoding="utf-8")
    return markdown_path


def write_missing_case_details(
    cases: list[CaseEntry],
    overwrite_paths: set[Path] | None = None,
    blog: BlogData | None = None,
    summary: str = "",
) -> list[Path]:
    created: list[Path] = []
    overwrite_paths = overwrite_paths or set()
    for case in cases:
        if not case.case_url.endswith("/"):
            continue
        detail_path = case.detail_path
        markdown_path = case.markdown_path
        if detail_path.exists() and markdown_path.exists() and detail_path not in overwrite_paths:
            continue
        detail_path.parent.mkdir(parents=True, exist_ok=True)
        current_blog = blog if blog and (case.slug == blog.slug or case.date == blog.date) else None
        images = gather_case_images_for_blog(case, current_blog)
        chosen_summary = summary or (current_blog.summary if current_blog else "") or case.summary or case.title
        ensure_case_thumbnail(case, images)
        markdown_path = write_case_markdown(case, current_blog, chosen_summary, images)
        _, markdown_body = parse_markdown_front_matter(read_text(markdown_path))
        detail_path.write_text(build_case_detail_html(case, images, current_blog, chosen_summary, markdown_body), encoding="utf-8")
        created.append(detail_path)
    return created


def make_case_entry_from_blog(data: BlogData) -> CaseEntry:
    thumb = data.thumbnail or thumbnail_path_for(data)
    if thumb and not thumb.startswith("/"):
        thumb = f"/{thumb.lstrip('/')}"
    return CaseEntry(
        date=data.date or datetime.now().strftime("%Y-%m-%d"),
        added_at=datetime.now().isoformat(timespec="seconds"),
        title=data.title,
        summary=data.summary,
        slug=case_folder_slug(data),
        category=data.category,
        url=case_url_for(data),
        thumb=thumb,
        source_url=data.source_url,
        instagram_url=data.instagram_url,
        highlight_image=thumb,
    )


def case_entry_to_dict(entry: CaseEntry) -> dict[str, str]:
    record = {
        "title": entry.title,
        "date": entry.date,
        "slug": entry.slug,
        "category": entry.category,
        "summary": entry.summary,
        "url": entry.case_url,
        "case_url": entry.case_url,
        "thumbnail": entry.thumb,
        "thumb": entry.thumb,
        "source_url": entry.source_url,
        "instagram_url": entry.instagram_url,
    }
    if entry.added_at:
        record["added_at"] = entry.added_at
    return record


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
            case_url = str(item.get("url") or item.get("case_url") or "").strip()
            if not slug and case_url:
                m = re.search(r"case-([a-z0-9\-]+)(?:\.html|/)", case_url)
                if m:
                    slug = m.group(1)
            if not slug:
                slug = normalize_slug("", date, title)
            entries.append(
                CaseEntry(
                    date=date,
                    added_at=str(item.get("added_at", "")).strip(),
                    title=title,
                    summary=summary,
                    slug=slug,
                    category=category,
                    url=case_url,
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
    highlights = "\n".join(build_case_feature_card(entry, is_latest=(idx == 0)) for idx, entry in enumerate(cases[:2]))
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


def validate_blog_data_for_generation(data: BlogData, summary: str) -> list[str]:
    errors: list[str] = []
    required_text = {
        "title": data.title,
        "date": data.date,
        "slug": data.slug,
        "category": data.category,
        "summary": summary,
        "source_url": data.source_url,
    }
    for key, value in required_text.items():
        if not str(value or "").strip():
            errors.append(f"error: blog_fetch_result.json 필수값 누락 - {key}")
    if not data.images:
        errors.append("error: blog_fetch_result.json 필수값 누락 - images")
    if not str(data.thumbnail or "").strip():
        errors.append("error: blog_fetch_result.json 필수값 누락 - thumbnail")
    return errors


def preview_image_review_report(entry: CaseEntry, blog: BlogData | None, images: list[Path]) -> list[str]:
    items = build_image_items(entry, images, blog)
    manifest = image_manifest_path(entry)
    todo = entry.case_folder / "image_manifest.todo.json"
    lines = [
        f"본문/갤러리 후보 이미지 수: {len(items)}",
        f"image_manifest.json 존재 여부: {'예' if manifest.exists() else '아니오'}",
        f"image_manifest.todo.json 경로: {todo.as_posix() if todo.exists() else '없음'}",
    ]
    for idx, item in enumerate(items, start=1):
        lines.append(f"- {idx:02d}. {item.path.name} | alt={item.alt} | reviewed={'예' if item.reviewed else '아니오'}")
    return lines


def parse_args() -> dict[str, object]:
    import argparse

    parser = argparse.ArgumentParser(description="오박사 홈페이지 preview/인덱스 동기화")
    parser.add_argument("--preview", action="store_true", help="preview 결과를 생성")
    parser.add_argument("--write-index", action="store_true", help="preview 대신 cases_index.json을 실제로 갱신")
    parser.add_argument("--apply", action="store_true", help="preview 결과를 실제 운영 파일에 반영")
    parser.add_argument("--summary", default="", help="사용자가 직접 제공한 150~200자 요약문")
    args = parser.parse_args()
    return {"preview": bool(args.preview), "write_index": bool(args.write_index), "apply": bool(args.apply), "summary": str(args.summary).strip()}


def inject_cases_pagination(html_text: str) -> str:
    pager_html = """
<div class="case-pagination" aria-label="시공사례 페이지 이동">
  <button type="button" class="case-page-btn" data-page-action="prev">이전</button>
  <div class="case-page-info" data-page-info>1 / 1</div>
  <button type="button" class="case-page-btn" data-page-action="next">다음</button>
</div>
""".strip()
    script_html = """
<script>
document.addEventListener('DOMContentLoaded',function(){
  var PAGE_SIZE = 10;
  var allRows = Array.prototype.slice.call(document.querySelectorAll('.case-row[data-category]'));
  var filterButtons = Array.prototype.slice.call(document.querySelectorAll('.case-filter button'));
  var pageInfo = document.querySelector('[data-page-info]');
  var prevBtn = document.querySelector('[data-page-action="prev"]');
  var nextBtn = document.querySelector('[data-page-action="next"]');
  var activeFilter = 'all';
  var currentPage = 1;

  function filteredRows(){
    return allRows.filter(function(row){
      var cats = row.getAttribute('data-category') || '';
      return activeFilter === 'all' || cats.indexOf(activeFilter) > -1;
    });
  }

  function totalPages(rows){
    return Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  }

  function syncPager(rows){
    var pages = totalPages(rows);
    if(currentPage > pages) currentPage = pages;
    if(currentPage < 1) currentPage = 1;
    var start = (currentPage - 1) * PAGE_SIZE;
    var end = start + PAGE_SIZE;
    allRows.forEach(function(row){ row.style.display = 'none'; });
    rows.forEach(function(row, idx){ row.style.display = (idx >= start && idx < end) ? 'grid' : 'none'; });
    if(pageInfo) pageInfo.textContent = currentPage + ' / ' + pages;
    if(prevBtn) prevBtn.disabled = currentPage <= 1;
    if(nextBtn) nextBtn.disabled = currentPage >= pages;
  }

  filterButtons.forEach(function(btn){
    btn.addEventListener('click',function(){
      filterButtons.forEach(function(b){ b.classList.remove('is-active'); });
      btn.classList.add('is-active');
      activeFilter = btn.getAttribute('data-filter') || 'all';
      currentPage = 1;
      syncPager(filteredRows());
    });
  });

  if(prevBtn){
    prevBtn.addEventListener('click', function(){
      currentPage -= 1;
      syncPager(filteredRows());
    });
  }
  if(nextBtn){
    nextBtn.addEventListener('click', function(){
      currentPage += 1;
      syncPager(filteredRows());
    });
  }

  syncPager(filteredRows());
});
</script>
""".strip()
    if pager_html not in html_text:
        html_text = html_text.replace("<!-- AUTO:CASE_LIST_END -->", f"<!-- AUTO:CASE_LIST_END -->\n{pager_html}", 1)
    if "data-page-action=\"prev\"" not in html_text:
        html_text = html_text.replace("</body></html>", f"{script_html}\n</body></html>", 1)
    else:
        html_text = re.sub(r"<script>\s*document\.querySelectorAll\\\('\\.case-filter button'\\\).*?</script>", script_html, html_text, flags=re.S)
    return html_text


def write_preview_files(data: BlogData, cases: list[CaseEntry]) -> list[Path]:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    index_path = PREVIEW_DIR / "index.preview.html"
    cases_path = PREVIEW_DIR / "cases.preview.html"
    sitemap_path = PREVIEW_DIR / "sitemap.preview.xml"
    index_json_path = CASES_INDEX_PREVIEW_PATH
    index_path.write_text(render_index_preview(data, cases[0] if cases else CaseEntry(date=data.date, title=data.title, summary=data.summary, slug=case_folder_slug(data), category=data.category, thumb=data.thumbnail, source_url=data.source_url, instagram_url=data.instagram_url)), encoding="utf-8")
    cases_path.write_text(inject_cases_pagination(render_cases_preview(cases)), encoding="utf-8")
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
    chosen_summary = args["summary"].strip()
    ok, data, source_path = load_blog_data()
    if not chosen_summary:
        print("error: --summary가 필요합니다. 150~200자 요약문을 제공해 주세요.")
        return 1
    data.summary = chosen_summary
    validation_errors = validate_blog_data_for_generation(data, chosen_summary)
    if validation_errors:
        for error in validation_errors:
            print(error)
        print("완료 메시지: 필수값 누락으로 preview/apply 중단")
        return 1
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
    new_case_images = gather_case_images_for_blog(new_case, data)
    print("[image review]")
    for line in preview_image_review_report(new_case, data, new_case_images):
        print(line)
    if args["apply"] and not has_reviewed_image_manifest(new_case, data, new_case_images):
        print("error: image_manifest.json 또는 blog_fetch_result.json image_plan 기준의 이미지 순서/alt 검수 정보가 필요합니다.")
        print("error: 이미지를 눈으로 확인한 뒤 image_manifest.todo.json을 image_manifest.json으로 정리하고 다시 실행하세요.")
        print("완료 메시지: 이미지 배열/alt 검수 누락으로 실제 반영 중단")
        return 1
    merged_cases, duplicate_found, replaced = merge_cases(existing_cases, new_case)
    preview_files = write_preview_files(data, merged_cases)
    thumbnail_used = bool(data.thumbnail)
    missing_case_details = collect_missing_case_details(merged_cases)
    created_case_details: list[Path] = []

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
        overwrite_paths = set(FORCE_REGENERATE_DETAIL_PATHS)
        overwrite_paths.add(new_case.detail_path)
        created_case_details = write_missing_case_details(merged_cases, overwrite_paths, data, chosen_summary)
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
    print(f"하이라이트 사례 수: {min(2, len(merged_cases))}")
    print(f"sitemap URL 수: {len({case.sitemap_url for case in merged_cases})}")
    print(f"thumbnail 사용 여부: {'예' if thumbnail_used else '아니오'}")
    print(f"backup 생성 여부: {'예' if backup_created else '아니오'}")
    if backup_path:
        print(f"backup 파일: {backup_path.as_posix()}")
    print(f"누락 상세 HTML 수: {len(missing_case_details)}")
    if missing_case_details:
        print("생성 예정 상세 HTML:")
        for case in missing_case_details:
            print(f"- {case.detail_path.as_posix()}")
    if created_case_details:
        print("실제 생성된 상세 HTML:")
        for detail_path in created_case_details:
            print(f"- {detail_path.as_posix()}")
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
