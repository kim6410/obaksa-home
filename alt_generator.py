from __future__ import annotations

import argparse
import base64
import json
import os
import re
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent

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
    "default_site_context": "아파트 빌라 주택 상가 인테리어 시공 현장",
    "auto_review": True,
}

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


@dataclass
class AltImageItem:
    path: Path
    alt: str
    caption: str = ""
    reviewed: bool = False


def _clean_alt_text(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"\s*(사진|이미지|모습)\s*", " ", text).strip()
    return re.sub(r"\s+", " ", text)[:60].rstrip(" ,.-/")


def _normalize_alt_spacing(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _image_filename(value: str) -> str:
    if not value:
        return ""
    return str(value).replace("\\", "/").split("/")[-1].strip()


def _home_alt_clean_text(value: str) -> str:
    return _clean_alt_text(value)


def _home_normalize_alt(value: str, title: str = "", business: str = "") -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if business and business in text:
        seen = False
        parts = [part.strip() for part in text.split("-") if part.strip()]
        normalized: list[str] = []
        for part in parts:
            if business in part:
                if seen:
                    continue
                seen = True
            normalized.append(part)
        text = " - ".join(normalized) if normalized else text
    if len(text) > 65:
        text = text[:65].rstrip(" ,.-/")
    return _clean_alt_text(text)


def _extract_case_location(title: str) -> str:
    title = re.sub(r"\s+", " ", title or "").strip()
    match = re.search(
        r"(울산\s*(?:중구|남구|동구|북구|울주군)|(?:서울|경기|부산|대구|인천|광주|대전|울산|세종|강원|충북|충남|전북|전남|경북|경남)\s*[가-힣A-Za-z0-9]+)",
        title,
    )
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def _extract_case_place(title: str) -> str:
    for keyword in ("아파트", "빌라", "주택", "상가", "오피스텔", "사무실", "매장"):
        if keyword in (title or ""):
            return keyword
    return ""


def _extract_case_work(title: str) -> str:
    for keyword in ("도배", "장판", "도장", "필름", "철거", "확장", "샷시", "전기", "조명", "타일", "욕실", "주방", "싱크대", "리모델링", "보수", "수리"):
        if keyword in (title or ""):
            return keyword
    return "인테리어"


def _extract_case_issue(title: str) -> str:
    for keyword in ("누수", "곰팡이", "파손", "노후", "결로", "오염", "불편", "하자", "변형"):
        if keyword in (title or ""):
            return keyword
    return "문제"


def _case_context_prefix(title: str, include_place: bool = False) -> str:
    parts = [_extract_case_location(title)]
    if include_place:
        parts.append(_extract_case_place(title))
    return " ".join(part for part in parts if part).strip()


def seo_alt_base(title: str) -> str:
    text = re.sub(r"\s+", " ", (title or "")).strip()
    if " 시공전 " in text:
        text = text.split(" 시공전 ", 1)[0].strip()
    text = re.sub(r"\s+(도배|장판|시공|작업|인테리어)$", "", text).strip()
    return _clean_alt_text(text[:46].rstrip(" ,-/"))


def seo_case_cover_alt(title: str) -> str:
    prefix = _case_context_prefix(title, include_place=True)
    work = _extract_case_work(title)
    issue = _extract_case_issue(title)
    base = f"{prefix} {work} {issue} 해결 현장" if prefix else f"오박사만능인테리어 {work} {issue} 해결 현장"
    return _clean_alt_text(base)


def seo_case_image_alt(title: str, index: int) -> str:
    prefix = _case_context_prefix(title, include_place=True)
    short_prefix = _case_context_prefix(title, include_place=False)
    work = _extract_case_work(title)
    issue = _extract_case_issue(title)
    if prefix:
        templates = [
            f"{prefix} {work} {issue} 전후 비교",
            f"{prefix} {work} 작업 전 확인",
            f"{prefix} {work} 작업 후 마감",
            f"{prefix} {work} 세부 마감 상태",
        ]
    else:
        templates = [
            f"{short_prefix or '오박사만능인테리어'} {work} {issue} 전후 비교",
            f"{work} 작업 전 확인",
            f"{work} 작업 후 마감",
            f"{work} 세부 마감 상태",
        ]
    return _clean_alt_text(templates[min(max(index, 0), len(templates) - 1)])


def _looks_like_filename_sentence(text: str) -> bool:
    text = _clean_alt_text(text).lower()
    return bool(re.search(r"\b(?:img|image|photo|picture|01|02|03|jpg|jpeg|png|webp)\b", text))


def _should_keep_ai_alt(raw_alt: str, business: str) -> bool:
    text = _clean_alt_text(raw_alt)
    if len(text) < 15:
        return False
    if business and business not in text:
        return False
    if _looks_like_filename_sentence(text):
        return False
    return True


def _home_make_alt_prompt(entry: Any, blog: Any, image_order: int, total_images: int) -> str:
    title = getattr(entry, "title", "") or getattr(blog, "title", "") or "오박사만능인테리어 시공 현장"
    summary = getattr(blog, "summary", "") or getattr(entry, "summary", "") or ""
    content = re.sub(r"\s+", " ", getattr(blog, "content", "") or "").strip()[:700]
    location = _extract_case_location(title) or HOME_ALT_SETTINGS["default_location"]
    business = HOME_ALT_SETTINGS["required_business"]
    site_context = HOME_ALT_SETTINGS["default_site_context"]
    return f"""
이미지 ALT 생성용 프롬프트입니다.

[필수 포함]
- 지역: {location}
- 업체명: {business}

[입력]
제목: {title}
요약: {summary}
본문: {content}
이미지 순서: {image_order} / {total_images}
현장 맥락: {site_context}

[출력 규칙]
- JSON만 출력: {{"analysis":"...", "alt":"..."}}
- alt는 30~55자 권장
- 파일명 기반 문구 사용 금지
- "{business}"는 자연스럽게 1회 포함
- "사진", "이미지" 같은 단어 금지
""".strip()


def _home_prepare_image_for_ollama(image_path: Path) -> tuple[Path, str]:
    if not HOME_ALT_SETTINGS["resize_before_ollama"]:
        return image_path, "원본 이미지 사용"
    try:
        from PIL import Image
    except Exception:
        return image_path, "Pillow 미설치: 원본 이미지 사용"
    max_px = int(HOME_ALT_SETTINGS["resize_max_px"])
    quality = int(HOME_ALT_SETTINGS["resize_quality"])
    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            w, h = img.size
            if max(w, h) <= max_px:
                return image_path, f"원본 이미지 사용({w}x{h})"
            scale = max_px / float(max(w, h))
            new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
            img = img.resize(new_size, Image.LANCZOS)
            tmp_dir = Path(tempfile.gettempdir()) / "obaksa_home_alt_ollama_resized"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = tmp_dir / f"{image_path.stem}_{new_size[0]}x{new_size[1]}.jpg"
            img.save(tmp_path, "JPEG", quality=quality, optimize=True)
            return tmp_path, f"리사이즈 완료 {w}x{h} -> {new_size[0]}x{new_size[1]}"
    except Exception as exc:
        return image_path, f"리사이즈 실패: 원본 사용({exc})"


def _home_parse_ollama_payload(response_text: str) -> dict[str, Any]:
    text = str(response_text or "").strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, flags=re.S)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"analysis": text, "alt": text}


def _home_alt_from_analysis_fallback(analysis: str, entry: Any, order: int) -> str:
    title = getattr(entry, "title", "") or "오박사만능인테리어 시공 현장"
    business = HOME_ALT_SETTINGS["required_business"]
    location = _extract_case_location(title) or HOME_ALT_SETTINGS["default_location"]
    candidates = [
        f"{location} {title} 작업 현장",
        f"{location} {business} 시공 과정",
        f"{title} 작업 전후 비교",
        f"{business} 세부 시공 장면",
    ]
    return _home_normalize_alt(candidates[(max(1, int(order or 1)) - 1) % len(candidates)], business=business)


def _home_generate_alt_with_ollama(image_path: Path, entry: Any, blog: Any, order: int, total: int) -> tuple[bool, str, str, str]:
    if not HOME_ALT_SETTINGS["enabled"]:
        return False, "", "", "HOME_ALT_OLLAMA 비활성화"
    if not image_path.exists() or not image_path.is_file():
        return False, "", "", f"이미지 파일 없음: {image_path.as_posix()}"
    try:
        send_path, resize_note = _home_prepare_image_for_ollama(image_path)
        image_b64 = base64.b64encode(send_path.read_bytes()).decode("utf-8")
        options = {
            "temperature": float(HOME_ALT_SETTINGS["ollama_temperature"]),
            "num_predict": int(HOME_ALT_SETTINGS["ollama_num_predict"]),
        }
        if HOME_ALT_SETTINGS["ollama_use_gpu"]:
            options["num_gpu"] = int(HOME_ALT_SETTINGS["ollama_num_gpu"])
        payload = {
            "model": HOME_ALT_SETTINGS["ollama_vision_model"],
            "prompt": _home_make_alt_prompt(entry, blog, order, total),
            "images": [image_b64],
            "stream": False,
            "keep_alive": HOME_ALT_SETTINGS["ollama_keep_alive"],
            "options": options,
        }
        if HOME_ALT_SETTINGS["ollama_json_format"]:
            payload["format"] = "json"
        req = urllib.request.Request(
            HOME_ALT_SETTINGS["ollama_url"],
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=int(HOME_ALT_SETTINGS["timeout_seconds"])) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        parsed = json.loads(raw)
        response_text = parsed.get("response", "")
        obj = _home_parse_ollama_payload(response_text)
        analysis = _clean_alt_text(obj.get("analysis", ""))
        raw_alt = str(obj.get("alt", "") or "").strip()
        if _should_keep_ai_alt(raw_alt, HOME_ALT_SETTINGS["required_business"]):
            alt = _home_normalize_alt(raw_alt, business=HOME_ALT_SETTINGS["required_business"])
            return True, alt, analysis, f"{resize_note} / Ollama {HOME_ALT_SETTINGS['ollama_vision_model']}"
        alt = _home_alt_from_analysis_fallback(analysis, entry, order)
        return True, alt, analysis, f"{resize_note} / analysis 기반 fallback"
    except Exception as exc:
        return False, "", "", f"Ollama 처리 예외: {exc}"


def _image_manifest_path_for_case_dir(case_dir: Path) -> Path:
    return case_dir / "image_manifest.json"


def image_manifest_path(entry_or_case_dir: Any) -> Path:
    if isinstance(entry_or_case_dir, Path):
        return _image_manifest_path_for_case_dir(entry_or_case_dir)
    folder = getattr(entry_or_case_dir, "image_folder", None)
    if callable(folder):
        folder = folder()
    if folder:
        return _image_manifest_path_for_case_dir(Path(folder))
    folder = getattr(entry_or_case_dir, "case_folder", None)
    if callable(folder):
        folder = folder()
    return _image_manifest_path_for_case_dir(Path(folder or ROOT))


def load_image_manifest(entry: Any, blog: Any = None) -> list[dict[str, Any]]:
    manifest_path = image_manifest_path(entry)
    if not manifest_path.exists():
        return []
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, dict) and isinstance(data.get("images"), list):
        return [item for item in data["images"] if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def write_image_review_todo(entry: Any, images: list[Path]) -> None:
    manifest_path = image_manifest_path(entry)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "note": "자동 ALT가 아직 생성되지 않았습니다.",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "images": [
            {"file": image.name, "order": idx + 1, "use": True, "alt": "", "caption": "", "reviewed": False, "source": "todo"}
            for idx, image in enumerate(images[:MAX_DETAIL_IMAGES])
        ],
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_generic_alt(value: str) -> bool:
    text = _clean_alt_text(value)
    return not text or len(text) < 12


def _contextual_alt(entry: Any, raw_alt: str, src: str = "") -> str:
    cleaned_raw_alt = _home_alt_clean_text(raw_alt)
    title = getattr(entry, "title", "") if entry is not None else ""
    business = HOME_ALT_SETTINGS["required_business"]
    if entry and cleaned_raw_alt and not _is_generic_alt(cleaned_raw_alt):
        return _home_normalize_alt(cleaned_raw_alt, business=business)
    if not entry:
        fallback = cleaned_raw_alt or _image_filename(src) or "오박사만능인테리어 시공 현장"
        return _home_normalize_alt(fallback, business=business)
    name = _image_filename(src)
    match = re.search(r"(?:_|-)(\d+)(?:\.[A-Za-z0-9]+)?$", name) or re.search(r"(\d+)", name)
    index = max(int(match.group(1)) - 1, 0) if match else 0
    return seo_case_image_alt(title or "오박사만능인테리어", index)


def build_image_items(entry: Any, images: list[Path], blog: Any = None) -> list[AltImageItem]:
    image_map = {image.name: image for image in images}
    plan = load_image_manifest(entry, blog)
    if not plan and images and HOME_ALT_SETTINGS["enabled"]:
        generated_path = generate_home_image_manifest(entry, images, blog, overwrite=False)
        if generated_path and generated_path.exists():
            plan = load_image_manifest(entry, blog)

    items: list[AltImageItem] = []
    if plan:
        normalized_plan = []
        for raw in plan:
            if not isinstance(raw, dict):
                continue
            file_name = _image_filename(str(raw.get("file") or raw.get("name") or raw.get("src") or ""))
            if not file_name or file_name not in image_map:
                continue
            if str(raw.get("use", True)).lower() in {"false", "0", "no", "n"}:
                continue
            try:
                order_int = int(raw.get("order", 999))
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
                alt = seo_case_image_alt(getattr(entry, "title", "") or "오박사만능인테리어", fallback_index)
            caption = _contextual_alt(entry, caption_raw or alt, path.name)
            reviewed = bool(raw.get("reviewed") or raw.get("checked") or raw.get("confirmed") or HOME_ALT_SETTINGS["auto_review"])
            items.append(AltImageItem(path=path, alt=alt, caption=caption or alt, reviewed=reviewed))
        return items[:MAX_DETAIL_IMAGES]

    write_image_review_todo(entry, images)
    return [
        AltImageItem(
            path=image,
            alt=seo_case_image_alt(getattr(entry, "title", "") or "오박사만능인테리어", idx),
            caption=seo_case_image_alt(getattr(entry, "title", "") or "오박사만능인테리어", idx),
            reviewed=False,
        )
        for idx, image in enumerate(images[:MAX_DETAIL_IMAGES])
    ]


def generate_home_image_manifest(entry: Any, images: list[Path], blog: Any = None, overwrite: bool = False) -> Path | None:
    if not images:
        return None
    manifest_path = image_manifest_path(entry)
    if manifest_path.exists() and not overwrite:
        return manifest_path
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    total = min(len(images), MAX_DETAIL_IMAGES)
    items: list[dict[str, Any]] = []
    for idx, image in enumerate(images[:MAX_DETAIL_IMAGES], start=1):
        ok, alt, analysis, note = _home_generate_alt_with_ollama(image, entry, blog, idx, total)
        if not ok or not alt:
            alt = seo_case_image_alt(getattr(entry, "title", "") or "오박사만능인테리어", idx - 1)
            if not analysis:
                analysis = "Ollama 실패, SEO fallback ALT 적용"
            note = f"{note} / SEO fallback 적용"
        alt = _home_normalize_alt(alt, business=HOME_ALT_SETTINGS["required_business"])
        items.append({
            "file": image.name,
            "order": idx,
            "use": True,
            "alt": alt,
            "caption": alt,
            "analysis": analysis,
            "reviewed": bool(HOME_ALT_SETTINGS["auto_review"]),
            "source": "ollama" if ok else "seo_fallback",
            "note": note,
        })
        pause = float(HOME_ALT_SETTINGS["request_pause_seconds"] or 0)
        if pause > 0:
            time.sleep(pause)
    payload = {
        "note": "Ollama 비전 분석 기반 자동 ALT 생성. 필요시 alt/caption을 검토해 수정하세요.",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "images": items,
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def _extract_title_from_html(text: str, fallback: str = "") -> str:
    for pattern in (r"<h1[^>]*>(.*?)</h1>", r'<meta\s+property="og:title"\s+content="([^"]+)"', r"<title>(.*?)</title>"):
        match = re.search(pattern, text, re.I | re.S)
        if match:
            title = re.sub(r"<[^>]+>", "", match.group(1))
            title = _normalize_alt_spacing(title)
            if title:
                return title
    return fallback


def _html_escape(value: str) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def refresh_live_case_alt_texts(targets: list[Path] | None = None) -> None:
    for html_path in [Path(p) for p in (targets or []) if Path(p).suffix.lower() == ".html"]:
        if not html_path.exists():
            continue
        original = html_path.read_text(encoding="utf-8")
        title = _extract_title_from_html(original, html_path.stem)
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


def _build_case_dir_images(case_dir: Path) -> list[Path]:
    allowed = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    images: list[Path] = []
    if not case_dir.exists():
        return images
    for path in sorted(case_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in allowed:
            continue
        if path.name.lower() == "thumb.jpg" or path.name == "image_manifest.json":
            continue
        if any(keyword in path.name.lower() for keyword in IMAGE_REJECT_KEYWORDS):
            continue
        images.append(path)
    return images[:MAX_DETAIL_IMAGES]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate image_manifest.json with Ollama ALT captions.")
    parser.add_argument("--case-dir", required=True, help="Case directory containing images.")
    parser.add_argument("--business", default=HOME_ALT_SETTINGS["required_business"])
    parser.add_argument("--location", default=HOME_ALT_SETTINGS["default_location"])
    parser.add_argument("--model", default=HOME_ALT_SETTINGS["ollama_vision_model"])
    parser.add_argument("--ollama-url", default=HOME_ALT_SETTINGS["ollama_url"])
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--preview", action="store_true")
    return parser.parse_args(argv)


def _apply_cli_settings(args: argparse.Namespace) -> None:
    HOME_ALT_SETTINGS["required_business"] = args.business
    HOME_ALT_SETTINGS["default_location"] = args.location
    HOME_ALT_SETTINGS["ollama_vision_model"] = args.model
    HOME_ALT_SETTINGS["ollama_url"] = args.ollama_url


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _apply_cli_settings(args)
    case_dir = Path(args.case_dir).expanduser().resolve()
    images = _build_case_dir_images(case_dir)
    if not images:
        print(f"No usable images found in {case_dir}")
        return 1
    if args.preview:
        print(f"Preview mode: would generate manifest for {len(images)} images in {case_dir}")
        for image in images:
            print(image.name)
        return 0
    manifest_path = generate_home_image_manifest(
        type("Entry", (), {"title": case_dir.name, "image_folder": case_dir, "case_folder": case_dir})(),
        images,
        blog=None,
        overwrite=args.overwrite,
    )
    print(str(manifest_path) if manifest_path else "manifest not created")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
