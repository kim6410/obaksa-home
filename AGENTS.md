# AGENTS.md

오박사만능인테리어 정적 홈페이지 운영 최상위 기준서

버전: v4.1

적용 대상: `obaksa-home` 프로젝트

목적: 기존 홈페이지를 깨뜨리지 않고, 시공사례와 콘텐츠를 안정적으로 누적하며, 모바일 방문자가 편하게 문의할 수 있는 구조를 유지한다.

신규 시공사례 작업은 사전 승인된 표준 작업이다.

조회, 이미지 분석, 파일 생성, HTML 생성, Git Push까지를 하나의 연속 작업으로 간주한다.

중간 승인 요청은 오류, 삭제, 위험 작업, 범위 이탈이 있을 때만 수행한다.

---

## 01 프로젝트 운영 철학

- 최우선 목표는 기존 홈페이지를 절대 깨뜨리지 않는 것이다.
- 안정성이 기능보다 우선한다.
- 수정 범위는 최소화한다.
- 요청하지 않은 구조 변경, 디자인 리뉴얼, 대규모 리팩토링은 금지한다.

---

## 02 AGENTS 우선순위

- `AGENTS.md`는 이 프로젝트의 최상위 기준 문서다.
- 다른 문서와 충돌하면 `AGENTS.md`를 우선 적용한다.
- 새 파일이 추가되거나 프로젝트 구조, 빌드 프로세스, 배포 방식이 변경되면 먼저 `AGENTS.md`를 갱신한다.
- `AGENTS.md`와 실제 프로젝트 구조가 다르면 작업 전에 차이점을 보고한다.
- 이 문서를 읽고 실제 구조와의 정합성을 확인한 뒤 작업을 시작한다.

---

## 03 작업 시작 절차

1. `AGENTS.md` 전체 읽기
2. `git status --short` 실행
3. 프로젝트 루트 파일 및 폴더 구조 확인
4. 주요 파일 목록과 실제 파일 목록 비교
5. 누락 파일, 신규 파일, 비정상 구조 변경 발견 시 선보고
6. 다중 파일 수정, 공통 CSS/JS 수정, 배포/동기화 작업이 포함될 경우 상위 폴더에 원본 전체 복사 백업 생성
7. 작업 착수 전 단문 보고

---

## 04 승인 정책

- 안전한 작업은 사용자 승인 없이 자동 진행한다.
- 파일 읽기, 디렉터리 탐색, `git status`, `git diff` 확인은 자동 진행한다.
- `Remove-Item`, `git reset --hard`, `git clean -fd`, `git push -f`, `.git` 삭제, `images` 전체 삭제, `cases` 전체 삭제, `gallery` 전체 삭제, 프로젝트 구조 변경, 대량 파일 삭제는 반드시 사용자 승인을 받는다.
- 삭제가 필요한 경우에는 삭제 목록 출력, 삭제 이유 설명, 사용자 승인 순서로 진행한다.

---

## 04-1 중간 승인 최소화 규칙

- 작업 시작 전 백업이 완료된 경우, 일반 홈페이지 운영 작업은 중간 승인 없이 자동 진행한다.
- 아래 작업은 안전 작업으로 간주하며 사용자에게 반복 확인하지 않는다.
  - `Get-Item`
  - `Get-ChildItem`
  - `Get-Content`
  - `Select-String`
  - `Test-Path`
  - `New-Item`
  - `Copy-Item`
  - `Move-Item`
  - `Set-Content`
  - `Add-Content`
  - HTML 파일 생성
  - CSS 파일 수정
  - JS 파일 수정
  - 이미지 복사
  - 이미지 압축
  - 이미지 리사이징
  - 원본 이미지를 `original` 폴더에 복사
  - `thumb.jpg` 생성
  - `before/after` 이미지 생성
  - `index.html` 갱신
  - `cases.html` 갱신
  - `sitemap.xml` 갱신
  - JSON-LD 생성
  - `git status`
  - `git diff`
  - `git add`
  - `git commit`
  - `git push`
- 위 작업은 신규 시공사례 생성, 이미지 정리, 기존 페이지 갱신, GitHub Pages 배포에 필요한 정상 작업이므로 중간 확인 없이 끝까지 수행한다.
- 신규 시공사례 생성 작업은 반복 수행되는 정형 작업으로 간주한다.
- 아래 작업은 사용자의 별도 승인 없이 자동 진행한다.
  - 신규 HTML 생성
  - 신규 이미지 폴더 생성
  - `original` 폴더 생성
  - JSON-LD 생성
  - `sitemap.xml` URL 추가
  - `upload_images` 이미지 읽기
  - 원본 이미지 복사
  - 이미지 압축
  - 이미지 리사이징
  - `thumb.jpg` 생성
  - `before-XX.jpg` 생성
  - `after-XX.jpg` 생성
  - `instagram-thumb.jpg` 생성
  - `index.html` 수정
  - `cases.html` 수정
  - `sitemap.xml` 수정
  - `data-date` 기준 정렬
  - 최신 사례 카드 갱신
  - `git status`
  - `git diff`
  - `git add .`
  - `git commit`
  - `git push`
- 위 작업은 신규 시공사례 등록 프로세스의 일부이므로 중간 확인 없이 자동 수행한다.
- 아래 작업은 백업이 있어도 반드시 사용자 승인을 받는다.
  - `Remove-Item`
  - `git reset --hard`
  - `git clean -fd`
  - `git push -f`
  - `.git` 폴더 삭제
  - 프로젝트 루트 삭제
  - `images` 폴더 전체 삭제
  - `images/gallery` 전체 삭제
  - `images/cases` 전체 삭제
  - `cases` 폴더 전체 삭제
  - 대량 파일 삭제
  - 원격 저장소 주소 변경
  - 브랜치 삭제
  - GitHub 저장소 삭제
- 위험 작업이 아닌 일반 운영 작업은 사용자의 중간 컨펌을 기다리지 말고 자동으로 진행한다.
- 작업 완료 후에만 결과를 보고한다.

---

## 05 백업 정책

- 여러 파일을 동시에 수정하거나 공통 CSS/JS를 건드릴 때는 백업을 수행한다.
- 백업 위치는 프로젝트 루트의 상위 폴더다.
- 백업 폴더명 형식은 `obaksa-home_backup_YYYYMMDD_HHMMSS`다.
- 백업 방식은 원본 구조 전체 복사 방식이다.
- 백업 제외 대상은 `.git`, `node_modules`, 기존 ZIP 파일, `*.bak`, `*.tmp`, `*.log`, `__MACOSX`, `.DS_Store`다.
- 백업이 완료되면 최종 보고서에 백업 폴더 절대 경로를 기록한다.
- 작업 도중 깨짐, 구문 오류, 파일 유실, 레이아웃 붕괴, 검증 실패가 발생하면 즉시 추가 작업을 중단한다.

---

## 06 Git 정책

- Git 충돌이 발생하면 임의 병합하지 않는다.
- 안전성이 검증된 수정사항만 `git status --short`, `git diff --name-only`, `git diff --stat`, `git add .`, `git commit`, `git push` 순서로 진행한다.
- 커밋 메시지는 짧고 명확하게 작성한다.
- `git push -f`, `git reset --hard`, `git clean -fd`, `git rebase --skip`, `git merge --strategy-option ours`, `git merge --strategy-option theirs`, `git pull --rebase`는 사용하지 않는다.
- 신규 시공사례 생성, 이미지 추가, `index.html` 갱신, `cases.html` 갱신, `sitemap.xml` 갱신이 포함된 작업은 GitHub 업데이트까지 자동으로 진행한다.
- 작업 완료 기준은 로컬 생성이 아니라 GitHub Pages 반영 준비 완료 상태다.
- `git status`에서 예상하지 못한 대량 변경, 승인되지 않은 삭제, merge conflict, push 권한 오류, 원격 주소 비정상, 요청 범위를 벗어난 변경이 있으면 자동 push를 중단하고 보고한다.

---

## 07 프로젝트 구조

- 루트 기준 주요 파일은 `index.html`, `about.html`, `cases.html`, `community.html`, `contact.html`, `channels.html`, `services.html`, `footer.html`, `assets/`, `images/`, `sitemap.xml`, `robots.txt`, `make-release.ps1`, `AGENTS.md`다.
- `README.md`와 `make-chatgpt-package.bat`은 존재할 때만 관리한다.
- `SITE_UPDATE_GUIDE.md`는 참고 문서 및 보조 관리 문서로 유지한다.
- `STYLE_GUIDE.md`, `IMAGE_RULES.md`, `DEPLOY_RULES.md`는 세부 규칙 문서다.
- `images/cases/`와 `images/gallery/`는 핵심 이미지 자산이다.

---

## 08 시공사례 운영 요약

- 신규 시공사례 제목은 `[지역명/동네명] + [문제 상황] + [해결 방법]`을 따른다.
- 블로그 URL이 제공되면 제목, 날짜, `slug`, 태그, 요약문을 자동 추출 또는 생성한다.
- 네이버 블로그 URL은 `STYLE_GUIDE.md`의 PostView 본문 수집 규칙에 따라 실제 본문을 우선 추출한다.
- 시공사례 자동등록의 현재 기준 실행 파일은 저장소 루트의 `go.py`다.
- 외부 경로 `G:\OneDrive\01_울산오박사인테리어\obaksa_site\go.py`는 과거 경로로만 참고한다.
- 실행 형식은 `python go.py "[블로그 URL]" "[인스타 URL]"`를 기본으로 한다.
- 신규 시공사례 생성 시 블로그 URL과 인스타 URL이 제공되면 먼저 `python go.py "[블로그 URL]" "[인스타 URL]"`를 실행해 본문과 메타를 수집한다.
- 수집된 제목, 날짜, 본문을 기준으로 시공사례 HTML을 생성한다.
- 본문 수집이 성공하면 사용자가 본문 원고를 별도로 제공하지 않아도 된다.
- 본문 수집이 실패한 경우에만 사용자에게 원문 제공을 요청한다.
- 사용자가 별도로 제목, 날짜, `slug`, 태그, 요약문을 제공하지 않아도 된다.
- 시공사례 목록의 단일 원본 데이터는 `cases_index.json`이다.
- `index.html`, `cases.html`, `sitemap.xml` 생성과 갱신은 항상 `cases_index.json`을 기준으로 한다.
- `cases.html` 파싱은 초기화 또는 fallback 용도로만 사용한다.
- 신규 시공사례 HTML에는 `<article>` 최상위에 `data-title`, `data-date`, `data-category`, `data-tags`, `data-slug`, `data-summary`, `data-thumb`를 포함한다.
- `index.html`에는 최신 시공사례 1개만 노출한다.
- `cases.html` 상단 하이라이트 미리보기 카드는 최신 시공사례 2개만 노출한다.
- 신규 게시물이 추가되면 기존 1번은 2번으로 밀리고, 기존 2번은 하단 전체 리스트로 내려간다.
- `cases.html` 갱신 시 모든 시공사례는 `data-date` 기준 내림차순으로 정렬한다.
- 이미지 대기 폴더는 항상 `G:\OneDrive\01_울산오박사인테리어\obaksa_site\upload_images`를 사용한다.
- 작업 시작 시 해당 `upload_images` 폴더를 확인한다.
- 승인 요청 금지 문구는 사용하지 않는다.
- 예시: `계속 진행할까요?`, `파일 생성해도 될까요?`, `이미지를 복사해도 될까요?`, `git commit 해도 될까요?`, `git push 해도 될까요?`, `index.html 수정해도 될까요?`, `cases.html 갱신해도 될까요?`

### 08-1 시공사례 자동등록 검수

- 오박사 자동등록은 `apply`, `commit`, `push` 전에 반드시 검수 단계를 거친다.
- `go.py`가 수집한 제목, 요약, 이미지가 실제 시공사례용으로 적합한지 확인한 뒤에만 다음 단계로 진행한다.
- 검수용 정보는 `blog_fetch_result.json`과 `sync_homepage.py`의 로그 또는 리포트에서만 사용하고, 고객에게 보이는 HTML 본문에는 남기지 않는다.
- `blog_fetch_result.json`에는 검수용으로 아래 항목이 있으면 좋다.
  - `title`
  - `date`
  - `category`
  - `summary`
  - `source_url`
  - `instagram_url`
  - `thumbnail`
  - `images_raw_count`
  - `images_used_count`
  - `filtered_images`
  - `rejected_images`
- 이미지 필터링은 수집 단계와 렌더 단계에서 모두 한 번씩 점검한다.
- 아래 성격의 이미지는 제외한다.
  - 지도 캡처
  - 캐릭터
  - 스티커
  - 로고
  - 프로필
  - 아이콘
  - 너무 작은 이미지
- 자동 생성 상세 페이지는 반드시 `templates/case-detail-template.html`을 사용하고, `sync_homepage.py` 내부에서 HTML 구조를 직접 생성하지 않는다.
- 고객용 상세 페이지에는 아래 성격의 내부 문구를 절대 출력하지 않는다.
  - `자동 생성된 페이지`
  - `cases_index.json`
  - `sync_homepage.py`
  - `상세 URL`
  - `썸네일 경로`
  - `내부 시스템 안내`
  - `개발용 안내문`
- 위 문구가 고객용 페이지에 발견되면 `apply`, `commit`, `push`를 중단한다.
- go.py로 수집한 이미지와 본문은 바로 최종본으로 쓰지 않고, 사람이 실제 시공 관련성, 해상도, 중복 여부, 지도/프로필/아이콘 제외 여부를 보고 선별한다.
- 선별된 이미지에만 작업 전, 작업 중, 작업 후 흐름과 설명을 붙여 고객용 상세 페이지를 만든다.
- 사용하지 않는 이미지는 최종 상세 페이지와 운영 산출물에서 제외한다.
- 아래 키워드가 파일명이나 URL에 포함되면 제외한다.
  - `map`
  - `profile`
  - `sticker`
  - `emoji`
  - `icon`
  - `logo`
  - `kakao`
  - `naver_map`
- `sync_homepage.py` preview 단계에서는 아래 항목을 보고할 수 있어야 한다.
  - 제목
  - 날짜
  - 분류
  - 요약
  - 사용 이미지 수
  - 제외 이미지 수
  - `thumbnail`
  - 생성 예정 상세 페이지
  - 개발용 문구 포함 여부
  - 빈 링크 여부
  - sitemap 중복 여부
- `--apply` 전 안전 조건은 다음과 같다.
  - 사용 이미지가 1장 이상일 것
  - `thumbnail`이 존재할 것
  - 상세 페이지에 개발용 문구가 없을 것
  - `cases_index.json`, `sync_homepage.py` 같은 내부 문구가 상세 페이지에 노출되지 않을 것
  - `href=""`, `href="#"`, `src=""`, `undefined`, `null`이 없을 것
  - sitemap 중복이 없을 것
- 시공사례 자동등록의 기본 순서는 `preview → 검수 → apply → commit → push`다.
- `preview` 단계에서는 자동 생성 결과와 검수 리포트만 확인하고, 실제 운영 파일은 수정하지 않는다.
- `apply`는 검수를 통과한 경우에만 실행한다.
- `commit`과 `push`는 `apply` 이후 검수 결과를 다시 확인한 뒤 진행한다.
- 고객용 상세페이지의 블로그 원문과 인스타 링크는 텍스트 목록이 아니라 버튼 형태로 보여준다.
- `현장 요약`은 제목과 summary만 반복하지 말고, 도입-문제-작업-마무리 흐름이 읽히는 기승전결 형태로 작성한다.
- 위 조건을 만족하지 않으면 `--apply`와 이후의 `git commit`, `git push`를 진행하지 않는다.

---

## 09 완료 조건

- 작업 완료 기준은 로컬 생성이 아니라 GitHub Pages 반영 준비 완료 상태다.
- `git push` 완료 후 가능한 경우 GitHub Pages URL 접속 여부를 확인한다.
- 완료 보고는 백업 폴더 경로, 생성 파일, 수정 파일, 삭제 파일 여부, `git commit` 메시지, `git push` 결과, GitHub Pages 반영 상태 중심으로 간단명료하게 한다.
- 작업이 모두 끝난 뒤에만 결과를 보고한다.
- 중간 진행 상황 보고는 하지 않는다.
- 오류 발생 시에만 보고한다.
