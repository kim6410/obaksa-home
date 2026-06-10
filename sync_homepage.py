from __future__ import annotations

import html
import json
import os
import re
import shutil
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from alt_generator import (
    HOME_ALT_SETTINGS,
    IMAGE_REJECT_KEYWORDS,
    MAX_DETAIL_IMAGES,
    _clean_alt_text,
    _contextual_alt,
    _home_generate_alt_with_ollama,
    _home_prepare_image_for_ollama,
    build_image_items,
    generate_home_image_manifest,
    image_manifest_path,
    load_image_manifest,
    refresh_live_case_alt_texts,
    seo_alt_base,
    seo_case_cover_alt,
    seo_case_image_alt,
    write_image_review_todo,
)


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


# ============================================================
# 홈페이지 이미지 ALT 자동 생성 설정
# - 네이버 블로그 도우미의 Ollama 비전 ALT 생성 로직을 홈페이지 사례 등록용으로 이식했다.
# - 로컬 Ollama가 켜져 있으면 image_manifest.json을 자동 생성하고,
#   꺼져 있으면 기존 SEO fallback/todo 흐름으로 안전하게 돌아간다.
# ============================================================
HOME_ALT_SETTINGS = {
    "enabled": os.getenv("HOME_ALT_OLLAMA", "1") not in {"0", "false", "False", "no"},
    "ollama_url": os.getenv("OLLAMA_URL", "http://127.0.0.1:11434/api/generate"),
    "ollama_vision_model": os.getenv("OLLAMA_VISION_MODEL", "gemma3:4b"),
    "ollama_use_gpu": True,
    "ollama_num_gpu": -1,
    "ollama_keep_alive": "30m",
    "ollama_temperature": 0.45,
    "ollama_num_predict": 110,
    "ollama_json_format": True,
    "timeout_seconds": int(os.getenv("HOME_ALT_TIMEOUT", "240")),
    "request_pause_seconds": float(os.getenv("HOME_ALT_PAUSE", "0.8")),
    "resize_before_ollama": True,
    "resize_max_px": 1024,
    "resize_quality": 85,
    "required_business": "오박사만능인테리어",
    "default_location": "울산",
    "default_site_context": "생활밀착형 집수리 및 인테리어 시공 현장",
    "auto_review": True,
}


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
            date_text = parse_case_date(str(data.get("date", "")).strip())
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


def _clean_alt_text(value: str) -> str:
    """ALT 문구를 검색 친화적으로 다듬는다.

    - 불필요한 "사진/이미지/모습" 표현 제거
    - 공백 정리
    - 너무 긴 문장은 60자 안쪽으로 정리
    """
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"\s*(사진|이미지|모습)\s*", " ", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text[:60].rstrip(" ,·-/.")


def _is_generic_alt(value: str) -> bool:
    text = _clean_alt_text(value)
    if not text:
        return True
    generic_phrases = {
        "현장 상태를 먼저 살펴본",
        "문제 원인이 되는 부분을 자세히 확인한",
        "필요한 부위를 보강하고 정리하는 과정",
        "현장 상황에 맞춰 다시 고정하는 작업",
        "틈새와 마감 상태를 함께 점검한",
        "작업 후 흔들림이나 불안 요소가 없는지 확인했습니다",
        "현장 최종 확인 후 안전하게 마무리한",
        "시공 사례",
        "작업 과정",
        "대표",
    }
    if text in generic_phrases:
        return True
    if re.match(r"작업 과정\s*\d*", text):
        return True
    # 너무 짧은 ALT는 이미지 검색 문맥이 부족하므로 자동 보강한다.
    return len(text) < 12


def _extract_case_location(title: str) -> str:
    title = re.sub(r"\s+", " ", title or "").strip()
    # 예: 울산 북구 매곡동, 울산 남구 삼산동, 울산 울주군 범서읍
    match = re.search(r"(울산\s*(?:중구|남구|동구|북구|울주군)(?:\s*[가-힣A-Za-z0-9]+(?:동|읍|면|리))?)", title)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()
    match = re.search(r"((?:경주|양산|부산|대구|포항|하남|양주|남양주|구리)\s*[가-힣A-Za-z0-9]+(?:동|읍|면|리|구)?)", title)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()
    return ""


def _extract_case_place(title: str) -> str:
    title = re.sub(r"\s+", " ", title or "").strip()
    place_keywords = (
        "월드메르디앙", "에일린의뜰", "무지개아파트", "대하그린파크", "라온호텔",
        "현대파라다이스", "동산에이스빌", "골든하이츠빌", "교육원", "상가", "주택",
    )
    for keyword in place_keywords:
        if keyword in title:
            return keyword
    match = re.search(r"([가-힣A-Za-z0-9]+(?:아파트|빌라|맨션|상가|주택|호텔|교육원))", title)
    return match.group(1) if match else ""


def _extract_case_work(title: str) -> str:
    title = title or ""
    work_keywords = [
        "환풍기", "세면대", "수전", "해바라기 샤워기", "샤워기", "변기", "소변기",
        "차단기", "누전차단기", "분전반", "전기", "조명", "콘센트",
        "도어락", "문틀", "문", "걸레받이", "도배", "장판", "싱크대",
        "누수", "배관", "방수", "곰팡이", "결로", "보일러", "타일",
    ]
    for keyword in work_keywords:
        if keyword in title:
            if keyword == "전기" and ("차단기" in title or "분전반" in title):
                continue
            return keyword
    return "집수리"


def _extract_case_issue(title: str) -> str:
    title = title or ""
    issue_keywords = [
        "탄내", "타는 냄새", "소음", "진동", "누수", "막힘", "역류", "곰팡이",
        "결로", "정전", "차단기 내려감", "고장", "파손", "부식", "떨어짐",
        "흔들림", "악취", "물샘", "교체", "수리",
    ]
    for keyword in issue_keywords:
        if keyword in title:
            return keyword
    return "문제"


def _case_context_prefix(title: str, include_place: bool = False) -> str:
    location = _extract_case_location(title)
    place = _extract_case_place(title) if include_place else ""
    prefix = " ".join(part for part in [location, place] if part).strip()
    return prefix


def seo_alt_base(title: str) -> str:
    """대표 카드용 짧은 SEO 베이스 문구를 만든다."""
    text = re.sub(r"\s+", " ", (title or "")).strip()
    if " 원인과 " in text:
        text = text.split(" 원인과 ", 1)[0].strip()
    text = re.sub(r"\s+(후기|사례|현장|작업)$", "", text).strip()
    return _clean_alt_text(text[:46].rstrip(" ,·-/"))


def seo_case_cover_alt(title: str) -> str:
    """홈/목록 대표 이미지 ALT.

    지역명 + 작업명 + 핵심 문제를 넣되, 대표 카드에서는 너무 길지 않게 유지한다.
    """
    prefix = _case_context_prefix(title, include_place=True)
    work = _extract_case_work(title)
    issue = _extract_case_issue(title)
    if prefix:
        return _clean_alt_text(f"{prefix} {work} {issue} 해결 사례")
    return _clean_alt_text(f"오박사만능인테리어 {work} {issue} 해결 사례")


def seo_case_image_alt(title: str, index: int) -> str:
    """상세 이미지용 SEO ALT를 생성한다.

    원칙:
    1. 같은 페이지 안에서 ALT 문장 반복을 줄인다.
    2. 지역명은 일부 컷에만 넣고, 나머지는 증상/부품/작업 단계를 구체화한다.
    3. 검색어는 넣되 "사진/이미지/모습" 같은 빈 단어는 쓰지 않는다.
    4. 20~60자 범위에 들어오도록 정리한다.
    """
    title = re.sub(r"\s+", " ", title or "").strip()
    prefix = _case_context_prefix(title, include_place=True)
    short_prefix = _case_context_prefix(title, include_place=False)
    work = _extract_case_work(title)
    issue = _extract_case_issue(title)

    if "환풍기" in work or "환풍기" in title:
        issue_word = "탄내" if "탄내" in title else ("소음" if "소음" in title else issue)
        templates = [
            f"{prefix or short_prefix} 욕실 환풍기 {issue_word} 원인 점검",
            "노후 환풍기 모터 과열 흔적 확인",
            f"환풍기 {issue_word} 원인 확인을 위한 내부 배선 점검",
            "노후 욕실 환풍기 철거 전 커버 분해",
            "환풍기 내부 먼지와 부품 상태 확인",
            "욕실 환풍기 신규 제품 설치 과정",
            "환풍기 덕트 연결부 밀봉 마감 점검",
            "교체 완료 후 환풍기 흡입력 테스트",
            f"화장실 환풍기 {issue_word} 해결 후 정상 작동 확인",
            f"{short_prefix or '욕실'} 환풍기 교체 최종 마감 점검",
            "환풍기 교체 후 소음과 냄새 재점검",
        ]
    elif any(token in title for token in ("차단기", "분전반", "정전", "전기")):
        templates = [
            f"{prefix or short_prefix} 정전 원인 분전반 점검",
            "누전차단기 내려감 원인 확인",
            "분전반 내부 배선 체결 상태 점검",
            "차단기 교체 전 회로 이상 여부 확인",
            "노후 차단기와 배선 연결부 정리",
            "전기 공급 복구 후 콘센트 전압 확인",
            "차단기 교체 완료 후 정상 작동 점검",
            f"{short_prefix or '현장'} 전기 수리 최종 안전 확인",
        ]
    elif any(token in title for token in ("누수", "배관", "수전", "물샘")):
        templates = [
            f"{prefix or short_prefix} 누수 원인 현장 점검",
            "수전 연결부 물샘 원인 확인",
            "노후 배관 부식과 누수 지점 확인",
            "누수 부품 철거 전 상태 점검",
            "새 부품 교체와 연결부 재정비",
            "수압 테스트로 물샘 재발 여부 확인",
            f"{short_prefix or '욕실'} 누수 수리 완료 후 마감 점검",
        ]
    elif any(token in title for token in ("세면대", "변기", "소변기", "도기")):
        templates = [
            f"{prefix or short_prefix} 욕실 도기 파손 상태 점검",
            "세면대 고정 불량과 흔들림 원인 확인",
            "노후 도기 철거 전 안전 점검",
            "욕실 도기 교체 위치와 배관 확인",
            "새 세면대 설치와 긴다리 고정 작업",
            "배수 연결부 누수 테스트",
            f"{short_prefix or '욕실'} 도기 교체 완료 후 안전 점검",
        ]
    elif any(token in title for token in ("문틀", "문", "도어락", "걸레받이")):
        templates = [
            f"{prefix or short_prefix} 문틀 손상 상태 점검",
            "노후 문틀과 마감재 이격 확인",
            "손상 부위 철거 전 상태 확인",
            "문틀 보강과 수평 조정 작업",
            "마감재 재시공과 틈새 정리",
            f"{short_prefix or '현장'} 문틀 수리 완료 후 개폐 점검",
        ]
    else:
        templates = [
            f"{prefix or short_prefix} {work} {issue} 현장 점검",
            f"{work} 문제 원인 확인",
            f"노후 부품 철거 전 상태 점검",
            f"{work} 교체와 보강 작업 과정",
            f"마감 상태와 안전성 확인",
            f"{short_prefix or '현장'} {work} 수리 완료 후 점검",
        ]

    template = templates[min(max(index, 0), len(templates) - 1)]
    alt = _clean_alt_text(template)
    if len(alt) < 20:
        alt = _clean_alt_text(f"{short_prefix or '오박사만능인테리어'} {alt}")
    return alt


def parse_case_date(raw: str) -> str:
    raw = (raw or "").strip()
    # Naver/Instagram often expose relative dates like "14분 전".
    # Normalize those to today so the newest case stays at the top.
    if re.match(r"20\d{2}\.\d{2}\.\d{2}", raw):
        return raw.replace(".", "-")
    if re.match(r"20\d{2}-\d{2}-\d{2}", raw):
        return raw
    if any(token in raw for token in ("분 전", "시간 전", "일 전", "방금", "오늘")):
        return datetime.now().strftime("%Y-%m-%d")
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
    # Keep the case board and homepage in newest-first order.
    # Date is the primary sort key, then added_at, then slug for stability.
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
        f'  <img src="{img}" alt="{seo_case_cover_alt(entry.title)}">',
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
    if not plan and images and HOME_ALT_SETTINGS.get("enabled", True):
        generated_path = generate_home_image_manifest(entry, images, blog, overwrite=False)
        if generated_path and generated_path.exists():
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
    """수동 ALT와 자동 ALT를 함께 살리는 최종 보정 함수.

    - image_manifest.json에 사람이 검수한 ALT가 있으면 우선 존중한다.
    - 비어 있거나 너무 일반적인 ALT만 자동 SEO ALT로 교체한다.
    - 자동 ALT는 파일명 숫자 또는 이미지 순서를 이용해 단계별로 다르게 만든다.
    """
    cleaned_raw_alt = _clean_alt_text(raw_alt)
    if not entry:
        return cleaned_raw_alt or _image_filename(src) or "오박사만능인테리어 시공 사례"

    if cleaned_raw_alt and not _is_generic_alt(cleaned_raw_alt):
        return cleaned_raw_alt

    name = _image_filename(src)
    number_match = re.search(r"(\d+)", name)
    number = int(number_match.group(1)) - 1 if number_match else 0
    return seo_case_image_alt(entry.title or "오박사만능인테리어 시공 사례", max(number, 0))


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
    asset_prefix = "../../../" if entry.case_url.endswith("/") else ""
    template = template.replace("{{ASSET_PREFIX}}", asset_prefix)
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


def normalize_case_dir_input(case_dir_input: str) -> Path:
    case_dir = Path(str(case_dir_input).strip().strip('"').strip("'"))
    if not case_dir.is_absolute():
        case_dir = (ROOT / case_dir).resolve()
    return case_dir


def load_case_image_plan(case_dir: Path) -> list[dict[str, object]]:
    manifest_path = case_dir / "image_manifest.json"
    if not manifest_path.exists():
        return []
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(raw, dict):
        raw = raw.get("images") or raw.get("items") or []
    return list(raw) if isinstance(raw, list) else []


def case_entry_from_markdown_meta(case_dir: Path, meta: dict[str, str]) -> CaseEntry:
    title = meta.get("title", "").strip() or case_dir.name
    date = parse_case_date(meta.get("date", "").strip())
    year = extract_year(date)
    slug = normalize_slug(meta.get("slug", "").strip(), date, title)
    category = meta.get("category", "").strip() or "시공사례"
    summary = meta.get("description", "").strip() or meta.get("summary", "").strip() or title
    source_url = meta.get("source_blog", "").strip() or meta.get("source_url", "").strip() or meta.get("source", "").strip()
    instagram_url = meta.get("instagram", "").strip() or meta.get("instagram_url", "").strip()
    thumb = f"cases/{year}/{slug}/thumb.jpg"
    return CaseEntry(
        date=date,
        title=title,
        summary=summary,
        slug=slug,
        category=category,
        url=f"cases/{year}/{slug}/",
        thumb=thumb,
        source_url=source_url,
        instagram_url=instagram_url,
        highlight_image=thumb,
    )


def rebuild_case_from_folder(case_dir_input: str) -> tuple[CaseEntry, BlogData, str, list[Path]]:
    case_dir = normalize_case_dir_input(case_dir_input)
    markdown_path = case_dir / "index.md"
    if not markdown_path.exists():
        raise FileNotFoundError(f"missing index.md: {markdown_path.as_posix()}")
    meta, markdown_body = parse_markdown_front_matter(read_text(markdown_path))
    entry = case_entry_from_markdown_meta(case_dir, meta)
    existing_cases, _ = load_cases_index()
    matched_existing = next((case for case in existing_cases if case.case_url == entry.case_url), None)
    if matched_existing:
        entry.added_at = matched_existing.added_at
        if not entry.source_url:
            entry.source_url = matched_existing.source_url
        if not entry.instagram_url:
            entry.instagram_url = matched_existing.instagram_url
    image_plan = load_case_image_plan(case_dir)
    images = gather_case_images(entry)
    blog = BlogData(
        title=entry.title,
        date=entry.date,
        year=entry.year,
        slug=entry.slug,
        category=entry.category,
        summary=entry.summary,
        content=markdown_body,
        source_url=entry.source_url,
        instagram_url=entry.instagram_url,
        image_plan=image_plan,
        thumbnail=entry.thumb,
        source_path=markdown_path,
    )
    detail_html = build_case_detail_html(entry, images, blog, entry.summary, markdown_body)
    entry.detail_path.parent.mkdir(parents=True, exist_ok=True)
    entry.detail_path.write_text(detail_html, encoding="utf-8")
    return entry, blog, markdown_body, images


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
        f'        <img src="{thumb}" alt="{seo_case_cover_alt(data.title)}" loading="lazy" />',
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
        f'  <img src="{thumb}" alt="{seo_case_cover_alt(data.title)}">',
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
    parser.add_argument("--rebuild-case", default="", help="지정한 case 폴더만 재빌드")
    parser.add_argument("--summary", default="", help="사용자가 직접 제공한 150~200자 요약문")
    args = parser.parse_args()
    return {"preview": bool(args.preview), "write_index": bool(args.write_index), "apply": bool(args.apply), "rebuild_case": str(args.rebuild_case).strip(), "summary": str(args.summary).strip()}


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


def refresh_live_case_alt_texts() -> list[Path]:
    updated_paths: list[Path] = []
    case_paths = sorted(ROOT.glob("cases/20??/case-*/index.html"))
    for html_path in case_paths:
        try:
            text = read_text(html_path)
        except Exception:
            continue
        title_match = re.search(r'<h1>([^<]+)</h1>', text)
        if not title_match:
            title_match = re.search(r'<title>([^<]+)</title>', text)
        if not title_match:
            continue
        case_title = html.unescape(title_match.group(1))
        pattern = re.compile(r'(<img\b[^>]*\bsrc="[^"]+"[^>]*\balt=")[^"]*(")', re.I)
        img_index = 0

        def repl(match: re.Match[str]) -> str:
            nonlocal img_index
            alt = seo_case_image_alt(case_title, img_index)
            img_index += 1
            return f"{match.group(1)}{alt}{match.group(2)}"

        updated = pattern.sub(repl, text)
        if updated != text:
            html_path.write_text(updated, encoding="utf-8")
            updated_paths.append(html_path)

    live_pages = [ROOT / "index.html", ROOT / "cases.html"]
    for html_path in live_pages:
        if not html_path.exists():
            continue
        text = read_text(html_path)
        updated = text
        if html_path.name == "index.html":
            m = re.search(r'<h2>([^<]+)</h2>\s*<p>([^<]+)</p>\s*<div class="ob-latest-case-card">.*?<img src="([^"]+)" alt="[^"]*" loading="lazy" />', text, re.S)
            if m:
                title = html.unescape(m.group(1))
                alt = seo_case_cover_alt(title)
                updated = re.sub(r'(<div class="ob-latest-case-card">.*?<img src="[^"]+" alt=")[^"]*(" loading="lazy" />)', r"\1" + alt + r"\2", text, count=1, flags=re.S)
        else:
            updated = re.sub(r'(<article class="case-feature-card">\s*<img src="[^"]+" alt=")[^"]*(">)', lambda m: f"{m.group(1)}{seo_case_cover_alt(re.search(r'<h2>([^<]+)</h2>', m.group(0)).group(1) if re.search(r'<h2>([^<]+)</h2>', m.group(0)) else '')}{m.group(2)}", text, flags=re.S)
        if updated != text:
            html_path.write_text(updated, encoding="utf-8")
            updated_paths.append(html_path)

    return updated_paths


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
    mode = "rebuild-case" if args["rebuild_case"] else ("apply" if args["apply"] else ("write-index" if args["write_index"] else "preview"))
    if args["rebuild_case"]:
        return main_rebuild_case(str(args["rebuild_case"]))
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
        FORCE_REGENERATE_DETAIL_PATHS.add(new_case.detail_path)
        FORCE_REGENERATE_DETAIL_PATHS.update(created_case_details)
        refresh_live_case_alt_texts()
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


def main_rebuild_case(case_dir_input: str) -> int:
    try:
        entry, blog, markdown_body, images = rebuild_case_from_folder(case_dir_input)
    except Exception as exc:
        print(f"error: rebuild-case failed - {exc}")
        return 1

    existing_cases, data_source = load_cases_index()
    merged_cases, duplicate_found, replaced = merge_cases(existing_cases, entry)
    if any(case.case_url == entry.case_url for case in existing_cases):
        merged_cases = sorted(merged_cases, key=lambda item: (item.date, item.added_at, item.slug), reverse=True)
    preview_files = write_preview_files(blog, merged_cases)
    preview_ok, preview_errors = validate_preview_outputs()
    if not preview_ok:
        print("완료 메시지: preview 검증 실패로 실제 반영 중단")
        for error in preview_errors:
            print(f"- {error}")
        return 1

    backup_created, backup_path, backup_files = backup_and_apply_live_files()
    write_cases_index_file(merged_cases, CASES_INDEX_PATH)
    _normalize_folder_case_html_outputs()
    _ensure_case_build_bats()
    FORCE_REGENERATE_DETAIL_PATHS.add(entry.detail_path)
    refresh_live_case_alt_texts()

    print(f"mode: rebuild-case")
    print(f"case_dir: {normalize_case_dir_input(case_dir_input).as_posix()}")
    print(f"rebuild target: {entry.detail_path.as_posix()}")
    print(f"기존 데이터 소스: {data_source}")
    print(f"기존 사례 수: {len(existing_cases)}")
    print(f"중복 갱신 여부: {'예' if replaced or duplicate_found else '아니오'}")
    print(f"정렬 후 전체 사례 수: {len(merged_cases)}")
    print(f"sitemap URL 수: {len({case.sitemap_url for case in merged_cases})}")
    print(f"backup 생성 여부: {'예' if backup_created else '아니오'}")
    if backup_path:
        print(f"backup 파일: {backup_path.as_posix()}")
    if backup_files:
        print("backup files:")
        for backup_file in backup_files:
            print(backup_file.as_posix())
    print(f"preview files:")
    for preview_file in preview_files:
        print(preview_file.as_posix())
    print("완료 메시지: case 재빌드 및 운영 파일 반영 완료")
    return 0


_ORIGINAL_MAIN = main


def _normalize_folder_case_html_outputs() -> None:
    replacements = (
        ('href="/assets/', 'href="../../../assets/'),
        ('src="/assets/', 'src="../../../assets/'),
        ('href="/index.html"', 'href="../../../index.html"'),
        ('href="/about.html"', 'href="../../../about.html"'),
        ('href="/services.html"', 'href="../../../services.html"'),
        ('href="/cases.html"', 'href="../../../cases.html"'),
        ('href="/community.html"', 'href="../../../community.html"'),
        ('href="/contact.html"', 'href="../../../contact.html"'),
        ('href="/cases/', 'href="../../../cases/'),
        ('src="/cases/', 'src="../../../cases/'),
    )
    for html_path in ROOT.glob("cases/20??/case-*/index.html"):
        text = html_path.read_text(encoding="utf-8")
        if 'href="/assets/' not in text and 'src="/assets/' not in text and 'href="/index.html"' not in text and 'href="/cases.html"' not in text and 'href="/cases/' not in text and 'src="/cases/' not in text:
            continue
        updated = text
        for old, new in replacements:
            updated = updated.replace(old, new)
        if updated != text:
            html_path.write_text(updated, encoding="utf-8")


def _ensure_case_build_bats() -> None:
    bat_template = """@echo off
setlocal
chcp 65001 >nul
title 오박사 시공사례 재빌드

set "CASE_DIR=%~dp0"
set "PROJECT_ROOT=G:\\OneDrive\\01_울산오박사인테리어\\obaksa_site\\obaksa-home"

echo.
echo Current case folder:
echo %CASE_DIR%
echo.
echo Rebuilding index.md and image_manifest.json into HTML...
echo.

pushd "%PROJECT_ROOT%"
python sync_homepage.py --rebuild-case "%CASE_DIR%"
set EXIT_CODE=%ERRORLEVEL%
popd
echo.
echo Rebuild complete.
echo Commit / push separately if you want to publish the change.
echo.
pause
exit /b %EXIT_CODE%
"""
    for html_path in ROOT.glob("cases/20??/case-*/index.html"):
        folder = html_path.parent
        if not folder.exists():
            continue
        bat_path = folder / "build.bat"
        if bat_path.exists() and bat_path.read_text(encoding="utf-8", errors="ignore") == bat_template:
            continue
        bat_path.write_text(bat_template, encoding="utf-8")


def main(*args, **kwargs):  # type: ignore[override]
    result = _ORIGINAL_MAIN(*args, **kwargs)
    if result == 0:
        _normalize_folder_case_html_outputs()
        _ensure_case_build_bats()
    return result


ALT_MIN_LENGTH = 20
ALT_MAX_LENGTH = 60
ALT_STAGE_LABELS = [
    "현장 점검",
    "분해 전 상태",
    "철거 중 배선 확인",
    "교체 전 커버 제거",
    "부품 상태 확인",
    "교체 중 설치",
    "덕트 밀봉 마감",
    "흡입력 시험",
    "문제 해결 후 점검",
    "최종 완료 확인",
]


def _normalize_alt_spacing(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _trim_alt_noise(text: str) -> str:
    text = _normalize_alt_spacing(text)
    text = text.replace("사진", "").replace("이미지", "").replace("모습", "")
    return _normalize_alt_spacing(text)


def _alt_stage_label(index: int) -> str:
    if index < 0:
        index = 0
    if index >= len(ALT_STAGE_LABELS):
        return ALT_STAGE_LABELS[-1]
    return ALT_STAGE_LABELS[index]


def _fit_alt_length(title: str, alt: str, index: int = 0, include_place: bool = True) -> str:
    alt = _trim_alt_noise(alt)
    location = _extract_case_location(title)
    place = _extract_case_place(title) if include_place else ""
    work = _extract_case_work(title)
    issue = _extract_case_issue(title)
    stage = _alt_stage_label(index)

    candidates = []
    for parts in [
        [location, place, work, issue, stage],
        [location, work, issue, stage],
        [location, work, stage],
        [location, issue, stage],
        [location, place, work, stage],
        [location, work],
        [location, stage],
    ]:
        candidate = _trim_alt_noise(_normalize_alt_spacing(" ".join(part for part in parts if part)))
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    if alt and alt not in candidates:
        candidates.insert(0, alt)

    for candidate in candidates:
        if ALT_MIN_LENGTH <= len(candidate) <= ALT_MAX_LENGTH:
            return candidate

    for candidate in candidates:
        if len(candidate) > ALT_MAX_LENGTH:
            shortened = candidate
            for token in [place, "현장", "점검", "최종", "완료", "확인", "문제 해결 후", "교체", "설치"]:
                if token:
                    shortened = shortened.replace(token, "")
            shortened = _normalize_alt_spacing(shortened)
            if len(shortened) > ALT_MAX_LENGTH:
                shortened = shortened[:ALT_MAX_LENGTH].rstrip(" ,.-/")
            if len(shortened) >= ALT_MIN_LENGTH:
                return shortened

    base = candidates[0] if candidates else _normalize_alt_spacing(f"{location or '울산'} {work or '집수리'} {stage}")
    if len(base) < ALT_MIN_LENGTH:
        base = _normalize_alt_spacing(f"{location or '울산'} {place or ''} {work or '집수리'} {stage}")
    if len(base) > ALT_MAX_LENGTH:
        base = base[:ALT_MAX_LENGTH].rstrip(" ,.-/")
    return base


def seo_case_cover_alt(title: str) -> str:
    title = _normalize_alt_spacing(title)
    base = _normalize_alt_spacing(
        " ".join(
            part
            for part in [
                _extract_case_location(title),
                _extract_case_place(title),
                _extract_case_work(title),
                _extract_case_issue(title),
                "문제 해결 완료",
            ]
            if part
        )
    )
    return _fit_alt_length(title, base, 0, include_place=True)


def seo_case_image_alt(title: str, index: int) -> str:
    title = _normalize_alt_spacing(title)
    base = _normalize_alt_spacing(
        " ".join(
            part
            for part in [
                _extract_case_location(title),
                _extract_case_place(title),
                _extract_case_work(title),
                _extract_case_issue(title),
                _alt_stage_label(index),
            ]
            if part
        )
    )
    if not base:
        base = _normalize_alt_spacing(f"울산 집수리 {_alt_stage_label(index)}")
    return _fit_alt_length(title, base, index=index, include_place=True)



def _home_alt_clean_text(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"^\s*```(?:json|JSON)?\s*", "", value)
    value = re.sub(r"\s*```\s*$", "", value).strip()
    json_match = re.search(r"\{.*?\}", value, flags=re.S)
    if json_match:
        try:
            obj = json.loads(json_match.group(0))
            if isinstance(obj, dict):
                extracted = obj.get("alt") or obj.get("ALT") or obj.get("text") or obj.get("description")
                if extracted:
                    value = str(extracted).strip()
        except Exception:
            pass
    value = re.sub(r"^\s*(ALT\s*[:：]|대체\s*텍스트\s*[:：]|alt\s*=)\s*", "", value, flags=re.I)
    value = value.strip().strip('"\'`“”‘’')
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if lines:
        value = lines[0]
    value = re.sub(r"^\s*\d+[\).]\s*", "", value)
    value = re.sub(r"[\"'`“”‘’]", "", value)
    value = re.sub(r"[.!?。]+$", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > 90:
        value = value[:90].rstrip()
    return value


def _home_extract_field_loose(text: str, field: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    patterns = [
        rf'["\']?{re.escape(field)}["\']?\s*[:：=]\s*["\']([^"\'\n\r}}]+)',
        rf'["\']?{re.escape(field)}["\']?\s*[:：=]\s*(.+?)(?:\n|,\s*["\']?(?:analysis|alt|reason|caption|summary)["\']?\s*[:：=]|}}|$)',
    ]
    for pat in patterns:
        m = re.search(pat, value, flags=re.I | re.S)
        if m:
            got = str(m.group(1) or "").strip().strip('"\'`“”‘’ ,')
            got = re.sub(r"\s+", " ", got).strip()
            if got:
                return got
    label_map = {
        "alt": ["ALT", "대체텍스트", "대체 텍스트", "이미지 ALT", "alt"],
        "analysis": ["analysis", "분석", "사진분석", "사진 분석", "상황", "설명"],
    }
    for label in label_map.get(field.lower(), []):
        m = re.search(rf'{re.escape(label)}\s*[:：]\s*(.+?)(?:\n|$)', value, flags=re.I | re.S)
        if m:
            got = str(m.group(1) or "").strip().strip('"\'`“”‘’ ,')
            got = re.sub(r"\s+", " ", got).strip()
            if got:
                return got
    return ""


def _home_parse_ollama_payload(text: str) -> dict[str, str]:
    value = str(text or "").strip()
    value = re.sub(r"^\s*```(?:json|JSON)?\s*", "", value)
    value = re.sub(r"\s*```\s*$", "", value).strip()
    json_match = re.search(r"\{.*\}", value, flags=re.S)
    if json_match:
        raw_json = json_match.group(0)
        for candidate in [raw_json, re.sub(r",\s*([}\]])", r"\1", raw_json.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'"))]:
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict):
                    return {
                        "alt": str(obj.get("alt") or obj.get("ALT") or obj.get("text") or obj.get("description") or "").strip(),
                        "analysis": str(obj.get("analysis") or obj.get("reason") or obj.get("caption") or obj.get("summary") or "").strip(),
                        "raw": value,
                    }
            except Exception:
                pass
    loose_alt = _home_extract_field_loose(value, "alt")
    loose_analysis = _home_extract_field_loose(value, "analysis")
    if not loose_alt:
        for ln in [line.strip(" -•\t") for line in value.splitlines() if line.strip()]:
            if ("오박사" in ln or "울산" in ln or "상가" in ln or "현장" in ln) and len(ln) >= 12:
                loose_alt = ln
                break
    return {"alt": _home_alt_clean_text(loose_alt or value), "analysis": _home_alt_clean_text(loose_analysis), "raw": value}


def _home_strip_business_noise(value: str, business: str = "") -> str:
    value = str(value or "")
    business = str(business or "").strip()
    if business:
        value = value.replace(business, " ")
    value = re.sub(r"오박사만능(?:인(?:테(?:리(?:어)?)?)?)?", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" -,.·/")
    value = re.sub(r"^(에서|의|이|가)\s*", "", value).strip()
    return value


def _home_looks_like_broken_alt(text: str) -> bool:
    value = str(text or "")
    if not value.strip():
        return True
    if re.search(r"KakaoTalk[_\s-]*\d", value, flags=re.I):
        return True
    if re.search(r"\{\s*[\"']?(analysis|alt)[\"']?\s*[:：]", value, flags=re.I):
        return True
    if value.count("{") or value.count("}"):
        return True
    if len(re.sub(r"\s+", "", value)) < 8:
        return True
    return False


def _home_finalize_alt_suffix(alt: str, business: str = "", max_len: int = 68) -> str:
    alt = re.sub(r"\s+", " ", str(alt or "")).strip()
    business = str(business or "").strip()
    if not alt or _home_looks_like_broken_alt(alt):
        return ""
    if not business:
        return alt[:max_len].rstrip(" ,./-·")
    suffix = f" - {business}"
    alt = _home_strip_business_noise(alt, business)
    alt = re.sub(r"^(에서\s*)?(진행하는|시공하는)\s*", "", alt).strip()
    alt = re.sub(r"\b현장에서\s*,?\s*", "현장 ", alt).strip()
    alt = re.sub(r"\s+", " ", alt).strip(" -,.·/")
    if not alt:
        return suffix.strip(" -")
    max_body_len = max(18, max_len - len(suffix))
    if len(alt) > max_body_len:
        parts = [x.strip(" ,./-·") for x in re.split(r"[,，/]|\s+-\s+", alt) if x.strip(" ,./-·")]
        preferred = ""
        for part in parts:
            if len(part) <= max_body_len and any(k in part for k in ["울산", "상가", "욕실", "환풍기", "콘센트", "배선", "시트지", "유리", "폐자재", "벽면", "누수", "수전", "문틀"]):
                preferred = part
                break
        alt = preferred or re.sub(r"(에서|으로|하고|하며|중인|있는|진행하는|만들어|바꾸는|모습)$", "", alt[:max_body_len]).rstrip(" ,./-·")
    alt = _home_strip_business_noise(alt, business)
    return f"{alt}{suffix}"


def _home_normalize_alt(raw_alt: str, title: str = "", business: str = "") -> str:
    business = business or str(HOME_ALT_SETTINGS.get("required_business", "오박사만능인테리어"))
    alt = _home_alt_clean_text(raw_alt)
    alt = re.sub(r"(상가)\s+\1", r"\1", alt)
    alt = re.sub(r"(창고)\s+\1", r"\1", alt)
    alt = re.sub(r"\s+", " ", alt).strip()
    finalized = _home_finalize_alt_suffix(alt, business=business, max_len=68)
    if finalized:
        return finalized
    return seo_case_image_alt(title or "울산 집수리", 0)


def _home_alt_from_analysis_fallback(analysis: str, entry: CaseEntry | None, order: int = 1) -> str:
    title = entry.title if entry else ""
    location = _extract_case_location(title) or str(HOME_ALT_SETTINGS.get("default_location", "울산"))
    business = str(HOME_ALT_SETTINGS.get("required_business", "오박사만능인테리어"))
    source = _home_alt_clean_text(analysis)
    candidates = [
        (("깨진 유리" in source or "유리 조각" in source), "깨진 유리 조각을 안전하게 정리한 현장"),
        ((("유리" in source or "출입문" in source) and ("시트" in source or "필름" in source)), "유리문 시트지를 꼼꼼하게 정리한 현장"),
        ((("시트" in source or "필름" in source) and ("제거" in source or "벗" in source)), "기존 시트지를 꼼꼼하게 제거하는 현장"),
        ((("콘센트" in source) and ("조립" in source or "박스" in source)), "콘센트 박스를 정밀하게 조립하는 현장"),
        ((("콘센트" in source or "전선" in source or "배선" in source)), "전기 배선을 안전하게 정리하는 현장"),
        ((("벽지" in source or "도배" in source)), "기존 벽지를 꼼꼼하게 제거하는 현장"),
        ((("바닥" in source and ("폐기물" in source or "폐자재" in source or "비닐" in source))), "바닥 폐자재를 깔끔하게 정리한 현장"),
        ((("호스" in source or "자재" in source)), "호스와 자재를 정돈하며 준비하는 현장"),
        ((("환풍기" in source or "덕트" in source)), "환풍기 부품 상태를 꼼꼼하게 점검한 현장"),
        ((("수전" in source or "배관" in source or "누수" in source)), "누수 원인을 확인하며 배관을 점검한 현장"),
    ]
    label = ""
    for cond, text in candidates:
        if cond:
            label = text
            break
    if not label:
        fallback = ["시공 전 현장을 꼼꼼하게 점검한 모습", "자재와 작업 부위를 정돈하는 과정", "문제 부위를 확인하며 보수하는 현장", "마감 상태를 확인하는 작업 과정"]
        label = fallback[(max(1, int(order or 1)) - 1) % len(fallback)]
    return _home_finalize_alt_suffix(f"{location} {label}", business=business)


def _home_make_alt_prompt(entry: CaseEntry, blog: BlogData | None, image_order: int, total_images: int) -> str:
    title = entry.title or (blog.title if blog else "") or "오박사만능인테리어 시공 사례"
    summary = (blog.summary if blog else "") or entry.summary or ""
    content = re.sub(r"\s+", " ", (blog.content if blog else "") or "").strip()[:700]
    location = _extract_case_location(title) or str(HOME_ALT_SETTINGS.get("default_location", "울산"))
    business = str(HOME_ALT_SETTINGS.get("required_business", "오박사만능인테리어"))
    site_context = str(HOME_ALT_SETTINGS.get("default_site_context", "생활밀착형 집수리 및 인테리어 시공 현장"))
    return f"""
너는 10년 차 온라인 마케터이자 홈페이지 SEO용 이미지 ALT 생성 전문가다.

다음 시공 현장 사진을 분석해서 홈페이지 상세페이지에 들어갈 이미지 ALT를 딱 한 줄로 만들어라.

[필수 포함 키워드]
- 지역: {location}
- 업체명: {business}

[사진 분석 기준]
- 본문보다 사진에 실제 보이는 사물, 자재, 공구, 작업자의 행동을 우선 설명한다.
- 사진 속 가장 구체적인 사물 1개를 반드시 반영한다.
- 같은 사례 안의 다른 사진과 같은 표현을 반복하지 않는다.
- 사진에 없는 작업을 억지로 만들지 않는다.

[홈페이지 사례 제목]
{title}

[요약]
{summary}

[본문 참고]
{content}

[이미지 순서]
{image_order} / {total_images}

[기본 현장 맥락]
{site_context}

[출력 규칙]
- 반드시 JSON 한 개만 출력: {{"analysis":"...", "alt":"..."}}
- analysis: 사진에 보이는 핵심 사물과 상황을 객관적으로 묘사.
- alt: 30~55자 내외의 자연스럽고 구체적인 서술형 구.
- 파일명은 절대 쓰지 않는다.
- 업체명은 문장 맨 끝에 ' - {business}' 형태로 한 번만 붙인다.
- 문장 앞에는 업체명을 쓰지 않는다.
- '사진', '이미지' 같은 빈 단어는 쓰지 않는다.

[좋은 예시]
{{"analysis":"작업자가 파란 전선 롤을 두고 배선 위치를 확인 중", "alt":"울산 북구 상가 휴게실의 꼼꼼한 콘센트 전기 배선 작업 - 오박사만능인테리어"}}
{{"analysis":"욕실 환풍기 커버를 분리하고 내부 먼지와 부품을 확인 중", "alt":"울산 욕실 환풍기 내부 부품을 꼼꼼하게 점검한 과정 - 오박사만능인테리어"}}
{{"analysis":"바닥에 폐자재와 비닐봉투가 있고 잔재를 모아둔 상태", "alt":"울산 상가 바닥 폐자재를 깔끔하게 정리한 현장 - 오박사만능인테리어"}}
""".strip()


def _home_prepare_image_for_ollama(image_path: Path) -> tuple[Path, str]:
    if not HOME_ALT_SETTINGS.get("resize_before_ollama", True):
        return image_path, "원본 이미지 사용"
    try:
        from PIL import Image
    except Exception:
        return image_path, "Pillow 미설치: 원본 이미지 사용"
    max_px = int(HOME_ALT_SETTINGS.get("resize_max_px", 1024))
    quality = int(HOME_ALT_SETTINGS.get("resize_quality", 85))
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            w, h = img.size
            longest = max(w, h)
            if longest <= max_px:
                return image_path, f"원본 이미지 사용({w}x{h})"
            scale = max_px / float(longest)
            new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
            img = img.resize(new_size, Image.LANCZOS)
            tmp_dir = Path(tempfile.gettempdir()) / "obaksa_home_alt_ollama_resized"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = tmp_dir / f"{image_path.stem}_{new_size[0]}x{new_size[1]}.jpg"
            img.save(tmp_path, "JPEG", quality=quality, optimize=True)
            return tmp_path, f"리사이즈 완료 {w}x{h} → {new_size[0]}x{new_size[1]}"
    except Exception as exc:
        return image_path, f"리사이즈 실패: 원본 사용({exc})"


def _home_generate_alt_with_ollama(image_path: Path, entry: CaseEntry, blog: BlogData | None, order: int, total: int) -> tuple[bool, str, str, str]:
    if not HOME_ALT_SETTINGS.get("enabled", True):
        return False, "", "", "HOME_ALT_OLLAMA 비활성화"
    if not image_path.exists() or not image_path.is_file():
        return False, "", "", f"이미지 파일 없음: {image_path.as_posix()}"
    try:
        import base64
        import urllib.request
        send_path, resize_note = _home_prepare_image_for_ollama(image_path)
        image_b64 = base64.b64encode(send_path.read_bytes()).decode("utf-8")
        options = {
            "temperature": float(HOME_ALT_SETTINGS.get("ollama_temperature", 0.45)),
            "num_predict": int(HOME_ALT_SETTINGS.get("ollama_num_predict", 110)),
        }
        if HOME_ALT_SETTINGS.get("ollama_use_gpu", True):
            options["num_gpu"] = int(HOME_ALT_SETTINGS.get("ollama_num_gpu", -1))
        payload = {
            "model": HOME_ALT_SETTINGS.get("ollama_vision_model", "gemma3:4b"),
            "prompt": _home_make_alt_prompt(entry, blog, order, total),
            "images": [image_b64],
            "stream": False,
            "keep_alive": HOME_ALT_SETTINGS.get("ollama_keep_alive", "30m"),
            "options": options,
        }
        if HOME_ALT_SETTINGS.get("ollama_json_format", True):
            payload["format"] = "json"
        req = urllib.request.Request(
            str(HOME_ALT_SETTINGS.get("ollama_url", "http://127.0.0.1:11434/api/generate")),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=int(HOME_ALT_SETTINGS.get("timeout_seconds", 240))) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        parsed = json.loads(raw)
        response_text = parsed.get("response", "")
        obj = _home_parse_ollama_payload(response_text)
        analysis = _home_alt_clean_text(obj.get("analysis", ""))
        raw_alt = _home_alt_clean_text(obj.get("alt", ""))
        if not raw_alt or _home_looks_like_broken_alt(raw_alt):
            alt = _home_alt_from_analysis_fallback(analysis, entry, order)
            return True, alt, analysis, f"{resize_note} / ALT 추출 실패 방어: analysis 기반 대체 ALT 생성"
        alt = _home_normalize_alt(raw_alt, title=entry.title, business=str(HOME_ALT_SETTINGS.get("required_business", "오박사만능인테리어")))
        if not alt:
            alt = _home_alt_from_analysis_fallback(analysis, entry, order)
        return True, alt, analysis, f"{resize_note} / Ollama {HOME_ALT_SETTINGS.get('ollama_vision_model', 'gemma3:4b')} / AI 원문 우선"
    except Exception as exc:
        return False, "", "", f"Ollama 처리 예외: {exc}"


def generate_home_image_manifest(entry: CaseEntry, images: list[Path], blog: BlogData | None = None, overwrite: bool = False) -> Path | None:
    """사례 폴더의 이미지들을 읽어 image_manifest.json을 자동 생성한다.

    기존 image_manifest.json이 있으면 기본적으로 보존한다.
    Ollama 실패 컷은 파일명으로 떨어지지 않고 기존 SEO/fallback ALT를 넣는다.
    """
    if not images:
        return None
    manifest_path = image_manifest_path(entry)
    if manifest_path.exists() and not overwrite:
        return manifest_path
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    total = min(len(images), MAX_DETAIL_IMAGES)
    items: list[dict[str, object]] = []
    for idx, image in enumerate(images[:MAX_DETAIL_IMAGES], start=1):
        ok, alt, analysis, note = _home_generate_alt_with_ollama(image, entry, blog, idx, total)
        if not ok or not alt:
            alt = seo_case_image_alt(entry.title or "울산 집수리", idx - 1)
            if not analysis:
                analysis = "Ollama 미사용 또는 응답 실패로 홈페이지 SEO fallback ALT 적용"
            note = f"{note} / SEO fallback 적용"
        alt = _home_normalize_alt(alt, title=entry.title, business=str(HOME_ALT_SETTINGS.get("required_business", "오박사만능인테리어")))
        items.append({
            "file": image.name,
            "order": idx,
            "use": True,
            "alt": alt,
            "caption": alt,
            "analysis": analysis,
            "reviewed": bool(HOME_ALT_SETTINGS.get("auto_review", True)),
            "source": "ollama" if ok else "seo_fallback",
            "note": note,
        })
        pause = float(HOME_ALT_SETTINGS.get("request_pause_seconds", 0.8) or 0)
        if pause > 0:
            time.sleep(pause)
    payload = {
        "note": "Ollama 비전 분석 기반 자동 생성. 필요하면 alt/caption을 눈으로 검수해 수정하세요.",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "images": items,
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def _contextual_alt(entry: CaseEntry | None, raw_alt: str, src: str = "") -> str:
    """홈페이지 이미지 ALT 최종 보정.

    1. image_manifest.json 또는 blog_fetch_result.json의 AI ALT를 우선 존중한다.
    2. 비어 있거나 파일명/깨진 JSON이면 SEO fallback을 사용한다.
    3. 업체명은 뒤에 한 번만 붙이고 잘리지 않게 정리한다.
    """
    cleaned_raw_alt = _home_alt_clean_text(raw_alt)
    if entry and cleaned_raw_alt and not _home_looks_like_broken_alt(cleaned_raw_alt):
        return _home_normalize_alt(cleaned_raw_alt, title=entry.title, business=str(HOME_ALT_SETTINGS.get("required_business", "오박사만능인테리어")))
    if not entry:
        fallback = cleaned_raw_alt or _image_filename(src) or "울산 집수리 점검"
        return _home_normalize_alt(fallback, business=str(HOME_ALT_SETTINGS.get("required_business", "오박사만능인테리어")))
    name = _image_filename(src)
    match = re.search(r"(?:_|-)(\d+)(?:\.[A-Za-z0-9]+)?$", name) or re.search(r"(\d+)", name)
    index = max(int(match.group(1)) - 1, 0) if match else 0
    return seo_case_image_alt(entry.title or "울산 집수리", index)


def build_image_items(entry: CaseEntry, images: list[Path], blog: BlogData | None = None) -> list[ImageItem]:
    """이미지 순서와 ALT를 만든다.

    우선순위:
    1. image_manifest.json 또는 blog_fetch_result.json의 image_plan에 있는 AI/수동 ALT
    2. manifest가 없고 Ollama 사용 가능하면 이미지를 읽어 image_manifest.json 자동 생성
    3. Ollama가 꺼져 있거나 실패하면 기존 SEO fallback + todo 생성
    """
    image_map = {image.name: image for image in images}
    plan = load_image_manifest(entry, blog)

    # 홈페이지 폴더에 manifest가 없으면 네이버 블로그 도우미에서 이식한 Ollama ALT 생성기를 한 번 돌린다.
    if not plan and images and HOME_ALT_SETTINGS.get("enabled", True):
        generated_path = generate_home_image_manifest(entry, images, blog, overwrite=False)
        if generated_path and generated_path.exists():
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
        for order_int, raw, file_name in sorted(normalized_plan, key=lambda item: item[0]):
            path = image_map[file_name]
            alt_raw = str(raw.get("alt") or raw.get("caption") or "").strip()
            caption_raw = str(raw.get("caption") or alt_raw).strip()
            fallback_index = max(order_int - 1, 0)
            alt = _contextual_alt(entry, alt_raw, path.name)
            if not alt or _is_generic_alt(alt):
                alt = seo_case_image_alt(entry.title or "울산 집수리", fallback_index)
            caption = _contextual_alt(entry, caption_raw or alt, path.name)
            reviewed = bool(raw.get("reviewed") or raw.get("checked") or raw.get("confirmed") or HOME_ALT_SETTINGS.get("auto_review", True))
            items.append(ImageItem(path=path, alt=alt, caption=caption or alt, reviewed=reviewed))
        return items[:MAX_DETAIL_IMAGES]

    write_image_review_todo(entry, images)
    return [
        ImageItem(
            path=image,
            alt=seo_case_image_alt(entry.title or "울산 집수리", idx),
            caption=seo_case_image_alt(entry.title or "울산 집수리", idx),
            reviewed=False,
        )
        for idx, image in enumerate(images[:MAX_DETAIL_IMAGES])
    ]


def markdown_text_to_html(markdown_text: str, entry: CaseEntry | None = None) -> str:
    output: list[str] = []
    lines = (markdown_text or "").splitlines()
    paragraph: list[str] = []
    list_items: list[str] = []

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
            output.append(f'  <img src="{_html_escape(src)}" alt="{_html_escape(alt)}" data-alt-source="auto" loading="lazy" />')
            output.append(f"  <figcaption>{_html_escape(alt)}</figcaption>")
            output.append("</figure>")
            continue
        paragraph.append(line)

    flush_paragraph()
    flush_list()
    return "\n".join(output)


def _extract_case_title_from_html(text: str, fallback: str = "") -> str:
    patterns = [
        r"<h1[^>]*>(.*?)</h1>",
        r'<meta\s+property="og:title"\s+content="([^"]+)"',
        r"<title>(.*?)</title>",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I | re.S)
        if not match:
            continue
        title = re.sub(r"<[^>]+>", "", match.group(1))
        title = html.unescape(title)
        title = _normalize_alt_spacing(title)
        if title:
            return title
    return fallback


def refresh_live_case_alt_texts() -> None:
    targets = sorted({path for path in FORCE_REGENERATE_DETAIL_PATHS if path and path.suffix.lower() == ".html"})
    if not targets:
        return

    for html_path in targets:
        if not html_path.exists():
            continue
        original = html_path.read_text(encoding="utf-8")
        title = _extract_case_title_from_html(original, html_path.stem)
        if not title:
            continue

        image_index = 0

        def replace_img(match: re.Match[str]) -> str:
            nonlocal image_index
            tag = match.group(0)
            if 'data-alt-source="manual"' in tag.lower():
                return tag
            alt = seo_case_image_alt(title, image_index)
            image_index += 1
            if re.search(r'data-alt-source="[^"]*"', tag, flags=re.I):
                tag = re.sub(r'data-alt-source="[^"]*"', 'data-alt-source="auto"', tag, count=1, flags=re.I)
            else:
                tag = tag.replace("<img ", '<img data-alt-source="auto" ', 1)
            if re.search(r'alt="[^"]*"', tag, flags=re.I):
                tag = re.sub(r'alt="[^"]*"', f'alt="{_html_escape(alt)}"', tag, count=1, flags=re.I)
            else:
                tag = tag[:-1] + f' alt="{_html_escape(alt)}">'
            return tag

        updated = re.sub(r"<img\b[^>]*>", replace_img, original, flags=re.I | re.S)
        if updated != original:
            html_path.write_text(updated, encoding="utf-8")

    FORCE_REGENERATE_DETAIL_PATHS.clear()

if __name__ == "__main__":
    raise SystemExit(main())
