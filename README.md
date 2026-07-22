# factlog

> 🌐 [English](README.en.md) | **한국어**

> facts + logic — 문서에 적힌 주장을 **출처가 붙은 사실**로 정리하고, 그 사실들끼리
> 어긋나는 곳을 기계적으로 찾아 주는 도구입니다.
>
> 보고서·논문·발표자료가 쌓이면 "이 숫자 어디서 나왔더라", "지난달 문서와 올해
> 문서가 서로 다른 말을 하는데" 같은 문제가 생깁니다. factlog는 문서에서 주장을
> 뽑아내 **어느 파일 어느 절에서 왔는지 출처를 붙이고**, 승인된 것만 모아 모순을
> 검사합니다.
>
> factlog는 AI가 뽑아낸 주장을 그대로 믿지 않습니다. 판단이 필요한 사실은 검토
> 큐에 쌓이고, 사람이 `factlog accept` 로 승인해야 검증 엔진의 입력이 됩니다.
> 자세한 구분은 [candidate vs accepted 신뢰 경계](docs/guide/concepts.md)를 보세요.

![factlog 동작 방식: Claude가 제안하고, 엔진이 검증하며, 사람이 확인합니다](docs/how-it-works.svg)

## 예시 — 문서 한 줄이 무엇으로 바뀌나

`sources/` 에 넣어 둔 문서에 이런 문장이 있다고 합시다.

```text
Claude Code is a command-line tool developed by Anthropic ...
```

`/factlog sync` 는 여기서 사실을 뽑아냅니다. 출처가 파일과 절 단위로 따라붙고,
사람의 판단이 필요한 것은 `needs_review` 로 검토 큐에 들어갑니다.

```csv
subject,relation,object,source,status,confidence,note
Anthropic,develops,Claude Code,sources/example.md#what-is-claude-code,needs_review,0.90,inferred from developed_by relation
```

터미널에서 사람이 승인하면, 그때 검증 엔진의 입력이 됩니다.

```console
$ factlog accept "Anthropic" develops "Claude Code"    # 또는 python3 -m factlog accept ...
  Anthropic / develops / Claude Code  [needs_review → accepted]  ← sources/example.md#what-is-claude-code
factlog accept: 1 row(s) → accepted; accepted.dl recompiled
```

승인된 사실은 엔진 입력 파일 `facts/accepted.dl` 에 Datalog 사실로 기록됩니다.

```datalog
relation("Anthropic", "develops", "Claude Code").
```

이제 이 사실을 근거로 질문에 답하거나, 다른 사실과 모순되지 않는지 검사할 수
있습니다. 전체 흐름을 직접 따라가 보려면
[빠른 시작 튜토리얼](examples/sample-kb/README.md)을 보세요.

## 어떤 문서를 넣을 수 있나

마크다운만이 아닙니다. `sources/` 에 원본 그대로 넣어 두면 `/factlog sync` 가
필요한 것을 자동으로 텍스트로 변환합니다. 원본 파일은 손대지 않습니다.

| | 형식 | 준비물 |
|---|---|---|
| **바로 읽음** | `.md` · `.txt` · `.csv` · `.rst` · `.org` · 소스 코드 | 없음 |
| **자동 변환 (내장)** | `.hwp` · `.hwpx` (한글) · `.pptx` (PowerPoint) | 없음 — `.hwp` 만 `pyhwp`+pandoc 필요 |
| **자동 변환 (외부 도구)** | `.pdf` · `.docx` · `.odt` · `.html` · `.epub` · `.rtf` | pandoc (`.docx` `.odt` `.html` `.epub`) · poppler (`.pdf`) · textutil (`.rtf` — **macOS 전용**) |

`.xlsx` 와 이미지는 변환하지 않습니다(시트는 `.csv` 로 내보내 주세요). 표에서는
같은 체인을 쓰는 확장자 별칭(`.htm`, `.markdown`)을 생략했습니다. 형식별 변환기
체인과 폴백, 변환기가 없을 때의 동작은
[소스 파일 형식](docs/reference/sources.md)에 정리되어 있습니다.

## 설치

factlog는 [Claude Code](https://code.claude.com) **플러그인**입니다. 시작하기 전에
다음이 준비되어 있어야 합니다.

- Python **3.11+** (엔진 의존성 `pyrewire` 가 요구)
- **pyrewire 1.0.3+** (`pip install -r requirements.txt`)
- Claude Code CLI
- **git** — 마켓플레이스 설치가 내부적으로 `git clone`을 사용합니다. Windows에서는 **Git for Windows**를 설치하세요.

준비되었으면 Claude Code 세션에서 이 저장소의 마켓플레이스로부터 설치합니다.

*Claude Code에서 실행:*

```
/plugin marketplace add https://github.com/semantic-reasoning/factlog
/plugin install factlog@semantic-reasoning
/reload-plugins
/factlog setup                     # one-shot: deps + doctor + init, in-session
```

위 명령은 **한 줄씩 실행**하십시오. 여러 줄을 한 번에 붙여 넣으면 Claude Code가
마켓플레이스 등록과 설치를 순서대로 처리하지 못할 수 있습니다.

설치가 성공해도 현재 세션에는 새 `/factlog ...` 명령이 즉시 로드되지 않을 수
있습니다. `/plugin install` 다음에 `/reload-plugins` 를 실행한 뒤 `/factlog setup`
을 실행하십시오.

로컬 설치(개발용), `/factlog setup` 이 하는 일, PEP 668 venv 안내, Windows Python
실행 파일 문제는 [설치 가이드](docs/guide/install.md)를 보세요.

## 두 개의 입구 — slash command 와 CLI

factlog는 세션 안에서는 `/factlog ...` slash command로 쓰고, 검토·승인 같은 사람의
게이트는 터미널에서 Python CLI(`python3 -m factlog ...`)로 직접 실행합니다. 두 입구
모두 같은 결정론 엔진을 호출합니다 — slash command · Python CLI · 검증 엔진, 이
셋이 한 도구입니다.

추출과 질의 초안은 LLM(세션 안의 Claude)이 맡고, 검증은 Datalog/wirelog 기반의
**결정론적 엔진**이 맡습니다. 같은 accepted 사실 집합과 같은 쿼리에는 언제나 같은
검증 결과가 나옵니다. 반면 문서에서 사실을 뽑아내는 추출 단계는 비결정적이라, 다시
돌리면 결과가 달라질 수 있습니다. 무엇이 보장되고 무엇이 보장되지 않는지는
[결정론과 한계](docs/guide/determinism.md)에 정리되어 있습니다.

## 빠른 시작

처음이라면 자기 데이터 없이 흐름을 한 번 완주해 보는
[빠른 시작 튜토리얼](examples/sample-kb/README.md)부터 시작하세요.

## 문서

상세 문서는 [`docs/`](docs/README.md) 에 있습니다.

- [개념](docs/guide/concepts.md) — 개요, KB 폴더 구조, candidate vs accepted 신뢰 경계, 명령 한눈에 보기
- [설치](docs/guide/install.md) — 요구 사항, 마켓플레이스·로컬 설치, `/factlog setup`
- [사용 사례](docs/guide/use-cases.md) — 보고서·슬라이드·논문·wiki의 일반 작업 흐름
- [소스 파일 형식](docs/reference/sources.md) — 지원 형식, 변환기 체인, 변환 실패 시 동작
- [결정론과 한계](docs/guide/determinism.md) — 무엇이 보장되고 무엇이 보장되지 않는지
- [Slash command 사용법](docs/reference/slash-commands.md) · [사실 검토](docs/reference/review.md) — 상세 레퍼런스

## 라이선스

Apache-2.0 — [LICENSE](LICENSE) 와 [NOTICE](NOTICE) 참조.
