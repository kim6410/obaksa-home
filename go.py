# go.py
# 네이버 블로그 본문 자동 추출기 v3.1 - Codex 연동용 오류 수정판
#
# 사용 예시:
# python go_v3.py "https://blog.naver.com/obarksa110/224294908335"
# python go_v3.py "https://blog.naver.com/obarksa110/224294908335" --json --txt --delay 1.2
#
# 생성 파일:
# - blog_fetch_result.json
# - blog_fetch_result.txt

import argparse
import html
import json
import re
import sys
import time
import os
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://blog.naver.com/",
    "Connection": "keep-alive",
}

DOWNLOAD_IMAGES = True
MAX_IMAGES = 12
IMAGE_BASE_DIR = Path("assets/images/cases")


CONTENT_SELECTORS = [
    ".se-main-container",
    "#postViewArea",
    ".post-view",
    ".area_view",
    ".post_ct",
    ".se_textarea",
    ".se_component_wrap",
    ".se_doc_viewer",
]

TITLE_SELECTORS = [
    ".se-title-text",
    ".se_title",
    ".pcol1.itemSubjectBoldfont",
    ".htitle",
    "title",
]

DATE_SELECTORS = [
    ".se_publishDate",
    ".date",
    ".pcol2",
    ".blog2_container .date",
]

CATEGORY_KEYWORDS = {
    "욕실수리": ["욕실", "화장실", "수전", "샤워기", "환풍기", "세면대", "변기", "슬라이드바"],
    "방화문수리": ["방화문", "현관문", "도어클로저", "힌지", "경첩"],
    "도어락": ["도어락", "번호키", "디지털키", "전자키"],
    "조명교체": ["LED", "조명", "전등", "모듈", "센서등"],
    "누수복구": ["누수", "물샘", "방수", "배관"],
    "도배장판": ["도배", "장판", "벽지", "바닥재"],
    "집수리": ["대문", "방문", "문짝", "문틀", "집수리", "경첩", "목문"],
}

SLUG_WORDS = [
    ("대문", "gate"),
    ("방문", "door"),
    ("문짝", "door"),
    ("문틀", "door-frame"),
    ("경첩", "hinge"),
    ("환풍기", "fan"),
    ("힘펠", "himpel"),
    ("수전", "faucet"),
    ("샤워기", "shower"),
    ("세면대", "sink"),
    ("변기", "toilet"),
    ("누수", "leak"),
    ("교체", "replacement"),
    ("수리", "repair"),
    ("설치", "install"),
]


# -----------------------------
# 텍스트 정리
# -----------------------------
def clean_text(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\u200b", "")
    text = text.replace("\xa0", " ")

    lines = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)

    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def normalize_date(date_text: str) -> str:
    """네이버 날짜 문자열을 YYYY-MM-DD로 변환한다."""
    if not date_text:
        return ""

    match = re.search(r"(20\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})", date_text)
    if match:
        y, m, d = match.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    match = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", date_text)
    if match:
        y, m, d = match.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    return date_text.strip()


def extract_tags(content: str, title: str = "") -> list[str]:
    text = f"{title}\n{content}"
    found = re.findall(r"#([0-9A-Za-z가-힣_\-]+)", text)

    tags = []
    for tag in found:
        tag = tag.strip()
        if tag and tag not in tags:
            tags.append(tag)

    if tags:
        return tags

    # 해시태그가 없을 때 후보 키워드 생성
    candidates = [
        "울산집수리", "울산북구집수리", "오박사만능인테리어",
        "욕실수리", "환풍기교체", "대문수리", "방문수리", "수전교체",
        "울산인테리어",
    ]
    for c in candidates:
        if c in text and c not in tags:
            tags.append(c)

    return tags[:20]


def guess_category(title: str, content: str) -> str:
    text = f"{title}\n{content}"
    best_category = "집수리"
    best_score = 0

    for category, words in CATEGORY_KEYWORDS.items():
        score = sum(text.count(word) for word in words)
        if score > best_score:
            best_score = score
            best_category = category

    return best_category


def make_slug(title: str, date_iso: str, content: str = "") -> str:
    words = []
    combined = f"{title}\n{content}"

    for ko, en in SLUG_WORDS:
        if ko in combined and en not in words:
            words.append(en)

    # 지역 단서 보강
    if "남외동" in combined and "namoe" not in words:
        words.insert(0, "namoe")
    if "중산동" in combined and "jungsan" not in words:
        words.insert(0, "jungsan")
    if "매곡동" in combined and "maegok" not in words:
        words.insert(0, "maegok")

    if not words:
        words = ["construction", "case"]

    base = "-".join(words[:4])
    date_part = date_iso if re.match(r"20\d{2}-\d{2}-\d{2}", date_iso or "") else datetime.now().strftime("%Y-%m-%d")
    slug = f"{date_part}-{base}"
    slug = re.sub(r"[^a-z0-9\-]", "", slug.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def make_summary(title: str, content: str, max_len: int = 150) -> str:
    """본문 앞부분에서 요약문을 만든다.

    주의:
    Python re는 길이가 다른 look-behind 패턴을 허용하지 않는다.
    따라서 look-behind 예시는 점을 이스케이프한 안전한 형태로 적는다.
    줄 단위 후보를 먼저 고른 뒤 안전하게 이어 붙인다.
    """
    text = clean_text(content)

    # 연락처/태그/지도 영역은 요약에서 제외
    text = re.split(r"문의\s*\n|#울산|태그|50m|© NAVER", text)[0]

    candidates: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if any(skip in line for skip in ["프로파일", "URL 복사", "본문 기타 기능", "접기/펴기"]):
            continue
        if line == title.strip():
            continue
        # 너무 짧은 키워드 나열은 요약 후보에서 제외
        if len(line) < 8:
            continue
        candidates.append(line)

    picked: list[str] = []
    for line in candidates:
        picked.append(line)
        joined = " ".join(picked)
        if len(joined) >= 80:
            break

    summary = " ".join(picked).strip() or title.strip()
    summary = re.sub(r"\s+", " ", summary).strip()

    if len(summary) > max_len:
        summary = summary[: max_len - 1].rstrip() + "…"

    return summary


def extract_date_parts(date_iso: str) -> tuple[str, str]:
    if re.match(r"20\d{2}-\d{2}-\d{2}", date_iso or ""):
        return date_iso[:4], date_iso[5:7]
    today = datetime.now().strftime("%Y-%m-%d")
    return today[:4], today[5:7]


def normalize_image_url(url: str, base_url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if not url:
        return ""
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return urljoin(base_url, url)
    return url


def is_probably_content_image(img_tag: Any) -> bool:
    if not img_tag:
        return False
    alt_text = " ".join(
        part for part in [
            img_tag.get("alt", ""),
            img_tag.get("title", ""),
            img_tag.get("aria-label", ""),
        ]
        if part
    ).lower()
    src_text = " ".join(
        part for part in [
            img_tag.get("src", ""),
            img_tag.get("data-src", ""),
            img_tag.get("data-lazy-src", ""),
            img_tag.get("data-original", ""),
        ]
        if part
    ).lower()

    if not src_text:
        return False

    skip_tokens = [
        "logo",
        "profile",
        "avatar",
        "icon",
        "spinner",
        "banner",
        "advert",
        "ad.",
        "ad/",
        "button",
    ]
    if any(token in alt_text for token in skip_tokens):
        return False
    if any(token in src_text for token in skip_tokens):
        return False
    return True


def extract_image_urls(soup: BeautifulSoup) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    for img in soup.find_all("img"):
        if not is_probably_content_image(img):
            continue

        for candidate in (
            img.get("data-original"),
            img.get("data-lazy-src"),
            img.get("data-src"),
            img.get("src"),
        ):
            normalized = normalize_image_url(str(candidate or ""), "https://blog.naver.com")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            urls.append(normalized)
            break

    return urls


def guess_image_extension(url: str, content_type: str | None) -> str:
    lowered = url.lower()
    if ".png" in lowered:
        return ".png"
    if ".gif" in lowered:
        return ".gif"
    if ".webp" in lowered:
        return ".webp"
    if content_type:
        content_type = content_type.lower()
        if "png" in content_type:
            return ".png"
        if "gif" in content_type:
            return ".gif"
        if "webp" in content_type:
            return ".webp"
    return ".jpg"


def download_images(session: requests.Session, image_urls: list[str], out_dir: Path, slug: str, date_iso: str) -> tuple[list[str], str]:
    if not DOWNLOAD_IMAGES or not image_urls:
        return [], ""

    year, month = extract_date_parts(date_iso)
    target_dir = out_dir / IMAGE_BASE_DIR / year / month / slug
    target_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[str] = []
    thumbnail = ""

    for index, image_url in enumerate(image_urls[:MAX_IMAGES], start=1):
        try:
            response = session.get(image_url, timeout=20, headers=HEADERS)
            response.raise_for_status()
            ext = guess_image_extension(image_url, response.headers.get("Content-Type"))
            file_path = target_dir / f"{index:02d}{ext}"
            if file_path.exists():
                print(f"경고: 기존 이미지 덮어쓰기 예정 - {file_path}")
            file_path.write_bytes(response.content)
            rel_path = file_path.relative_to(Path.cwd()).as_posix()
            downloaded.append(rel_path)
            if not thumbnail:
                thumbnail = rel_path
        except Exception as e:
            print(f"경고: 이미지 다운로드 실패 - {image_url} ({e})")

    return downloaded, thumbnail


# -----------------------------
# 네이버 블로그 수집
# -----------------------------
def fetch(session: requests.Session, url: str, delay: float) -> requests.Response:
    time.sleep(delay)
    response = session.get(url, timeout=15)
    response.raise_for_status()
    return response


def find_first_text(soup: BeautifulSoup, selectors: list[str]) -> str:
    for selector in selectors:
        el = soup.select_one(selector)
        if el:
            value = clean_text(el.get_text("\n"))
            if value:
                return value
    return ""


def find_content_container(soup: BeautifulSoup):
    for selector in CONTENT_SELECTORS:
        el = soup.select_one(selector)
        if el:
            return selector, el
    return "", None


def extract_postview_url(input_url: str, soup: BeautifulSoup) -> str:
    iframe = soup.find("iframe", {"id": "mainFrame"})

    if iframe and iframe.get("src"):
        return urljoin("https://blog.naver.com", iframe.get("src"))

    if "PostView.naver" in input_url:
        return input_url

    match = re.search(r"PostView\.naver\?[^\"']+", str(soup))
    if match:
        return urljoin("https://blog.naver.com/", match.group(0))

    return ""


def normalize_naver_url(url: str) -> str:
    """m.blog.naver.com URL을 blog.naver.com 기준으로 보정한다."""
    parsed = urlparse(url)
    if parsed.netloc == "m.blog.naver.com":
        return url.replace("https://m.blog.naver.com", "https://blog.naver.com")
    return url


def get_naver_blog_content(blog_url: str, delay: float = 1.2) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update(HEADERS)

    blog_url = normalize_naver_url(blog_url)

    result: dict[str, Any] = {
        "success": False,
        "input_url": blog_url,
        "real_url": "",
        "title": "",
        "date_raw": "",
        "date": "",
        "selector": "",
        "category": "",
        "slug": "",
        "summary": "",
        "tags": [],
        "images": [],
        "thumbnail": "",
        "content": "",
        "error": "",
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }

    try:
        first_response = fetch(session, blog_url, delay)
        first_soup = BeautifulSoup(first_response.text, "html.parser")

        real_url = extract_postview_url(blog_url, first_soup)
        if not real_url:
            result["error"] = "mainFrame 또는 PostView.naver 주소를 찾지 못했습니다."
            return result

        result["real_url"] = real_url

        second_response = fetch(session, real_url, delay)
        second_soup = BeautifulSoup(second_response.text, "html.parser")

        title = find_first_text(second_soup, TITLE_SELECTORS)
        date_raw = find_first_text(second_soup, DATE_SELECTORS)

        selector, content = find_content_container(second_soup)
        if not content:
            result["error"] = "본문 컨테이너를 찾지 못했습니다."
            return result

        for tag in content(["script", "style", "iframe", "noscript"]):
            tag.decompose()

        text = clean_text(content.get_text("\n"))
        if not text:
            result["error"] = "본문 텍스트가 비어 있습니다."
            return result

        date_iso = normalize_date(date_raw)
        tags = extract_tags(text, title)
        category = guess_category(title, text)
        slug = make_slug(title, date_iso, text)
        summary = make_summary(title, text)
        image_urls = extract_image_urls(content)
        downloaded_images: list[str] = []
        thumbnail = ""
        if image_urls:
            downloaded_images, thumbnail = download_images(session, image_urls, Path.cwd(), slug, date_iso)

        result.update(
            {
                "success": True,
                "title": title,
                "date_raw": date_raw,
                "date": date_iso,
                "selector": selector,
                "category": category,
                "slug": slug,
                "summary": summary,
                "tags": tags,
                "images": downloaded_images,
                "thumbnail": thumbnail,
                "content": text,
            }
        )
        return result

    except requests.exceptions.HTTPError as e:
        result["error"] = f"HTTP 오류: {e}"
        return result
    except requests.exceptions.Timeout:
        result["error"] = "요청 시간 초과"
        return result
    except requests.exceptions.RequestException as e:
        result["error"] = f"요청 오류: {e}"
        return result
    except Exception as e:
        result["error"] = f"예상치 못한 오류: {e}"
        return result


def save_json(data: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_txt(data: dict[str, Any], path: Path) -> None:
    lines = [
        "네이버 블로그 본문 수집 결과",
        "=" * 70,
        f"성공 여부: {data.get('success')}",
        f"입력 URL: {data.get('input_url')}",
        f"실제 본문 URL: {data.get('real_url')}",
        f"제목: {data.get('title')}",
        f"날짜 원문: {data.get('date_raw')}",
        f"날짜: {data.get('date')}",
        f"본문 선택자: {data.get('selector')}",
        f"카테고리: {data.get('category')}",
        f"slug: {data.get('slug')}",
        f"요약: {data.get('summary')}",
        f"태그: {', '.join(data.get('tags') or [])}",
        f"오류: {data.get('error')}",
        "=" * 70,
        "본문",
        "=" * 70,
        data.get("content", ""),
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="네이버 블로그 본문 자동 추출기 v3")
    parser.add_argument("url", nargs="?", default="https://blog.naver.com/obarksa110/224294908335")
    parser.add_argument("--json", action="store_true", help="blog_fetch_result.json 저장")
    parser.add_argument("--txt", action="store_true", help="blog_fetch_result.txt 저장")
    parser.add_argument("--delay", type=float, default=1.2, help="요청 사이 지연 시간(초)")
    parser.add_argument("--out-dir", default=".", help="결과 파일 저장 폴더")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print("네이버 블로그 본문 자동 수집 시작")
    print("=" * 70)

    data = get_naver_blog_content(args.url, delay=args.delay)

    json_path = out_dir / "blog_fetch_result.json"
    txt_path = out_dir / "blog_fetch_result.txt"

    # Codex 연동을 위해 기본적으로 JSON/TXT를 저장한다.
    save_json(data, json_path)
    save_txt(data, txt_path)

    print(f"성공 여부: {data['success']}")
    print(f"입력 URL: {data['input_url']}")
    print(f"실제 본문 URL: {data['real_url']}")
    print(f"제목: {data['title']}")
    print(f"날짜: {data['date']}")
    print(f"본문 선택자: {data['selector']}")
    print(f"카테고리: {data['category']}")
    print(f"slug: {data['slug']}")
    print(f"요약: {data['summary']}")
    print(f"태그: {', '.join(data.get('tags') or [])}")

    if data["error"]:
        print(f"오류: {data['error']}")

    print("=" * 70)
    print(f"JSON 저장: {json_path}")
    print(f"TXT 저장: {txt_path}")
    print("=" * 70)
    print("본문")
    print("=" * 70)
    print(data["content"])

    if not data["success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
