# DEPLOY_RULES.md

오박사만능인테리어 배포 및 Git 규칙

---

## 01 Git 흐름

- 안전성이 검증된 수정사항만 `git status --short`, `git diff --name-only`, `git diff --stat`, `git add .`, `git commit`, `git push` 순서로 진행한다.
- 커밋 메시지는 짧고 명확하게 작성한다.
- `git push -f`, `git reset --hard`, `git clean -fd`, `git rebase --skip`, `git merge --strategy-option ours`, `git merge --strategy-option theirs`, `git pull --rebase`는 사용하지 않는다.

---

## 02 자동 커밋 및 배포

- 신규 시공사례 생성, 이미지 추가, `index.html` 갱신, `cases.html` 갱신, `sitemap.xml` 갱신이 포함된 작업은 GitHub 업데이트까지 자동으로 진행한다.
- 작업 완료 기준은 로컬 생성이 아니라 GitHub Pages 반영 준비 완료 상태다.
- `git push` 완료 후 가능한 경우 GitHub Pages URL 접속 여부를 확인한다.
- 확인 대상은 메인 페이지, 시공사례 목록 페이지, 신규 시공사례 상세 페이지다.

---

## 03 자동 push 금지

- 승인 없는 삭제, `AGENTS.md`와 `SITE_UPDATE_GUIDE.md` 외 대량 문서 변경, `images/gallery` 전체 변경, `images/cases` 전체 일괄 변경, `.gitignore` 전체 교체, `package-lock`/`node_modules`/대용량 zip 포함, `git status` 충돌 상태가 있으면 자동 push를 중단하고 보고한다.
- `git status`에서 예상하지 못한 대량 변경, 승인되지 않은 삭제, merge conflict, push 권한 오류, 원격 주소 비정상, 요청 범위를 벗어난 변경이 있으면 자동 push를 중단하고 보고한다.

---

## 04 완료 보고

- 작업 완료 보고에는 `git diff --name-only` 결과, `git diff --stat` 결과, `git commit` 메시지, `git push` 성공 여부, GitHub Pages 반영 상태, 수정 파일 목록, 생성 이미지 목록, 백업 폴더 경로를 포함한다.
- 완료 보고는 백업 폴더 경로, 생성 파일, 수정 파일, 삭제 파일 여부, `git commit` 메시지, `git push` 결과, GitHub Pages 반영 상태 중심으로 간단명료하게 한다.

