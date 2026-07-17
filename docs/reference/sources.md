# 소스 파일 형식

> 🌐 [English](sources.en.md) | **한국어**

## 소스 파일 형식

`/factlog sync` 는 `sources/` 아래의 각 파일을 **세션 내에서 텍스트로 읽어**
사실을 추출합니다. 내장 엔진(`merge_candidates.py`)은 모든 파일을 소스 *경로*로
추적하지만 내용은 결코 파싱하지 않습니다 — 따라서 추출 과정에서 텍스트를 읽어낼 수
있는 파일만 적재됩니다. 그러므로 바이너리 원본(예: `.docx`)은 그 자체만으로는
사실을 만들어 내지 못합니다.

| 형식 | 상태 | 비고 |
|--------|--------|-------|
| `.md`, `.markdown`, `.txt` | **직접 지원** | UTF-8 텍스트, 있는 그대로 읽음. 모든 추출 기준이 전제하는 형식입니다. |
| 그 밖의 UTF-8 텍스트 (`.rst`, `.org`, `.csv`, 소스 코드) | 평문으로 지원 | 별도 파싱 없이 원시 텍스트로 취급. |
| `.docx`, 바이너리 `.pdf`, `.odt`, `.epub`, `.html`, `.rtf` | **자동 변환** | `factlog ingest` 가 pandoc / textutil / pdftotext 로 텍스트 변환. |
| `.hwpx` (한컴 OWPML) | **자동 변환** | 내장 추출기(외부 도구 불필요) — zip 내부 `Contents/section*.xml` 텍스트를 읽음. |
| `.hwp` (구형 한컴, HWP 5.x) | **자동 변환** | `hwp5html`(pyhwp) → pandoc → markdown 경로, 표 보존. `pip install pyhwp` + pandoc 필요. 없으면 안내 메시지와 함께 보고. |
| `.pptx` (PowerPoint) | **자동 변환** | 내장 추출기(외부 도구 불필요) — zip 내부 `ppt/slides/slideN.xml` 의 슬라이드 텍스트를 순서대로 읽고, 슬라이드당 한 블록으로 변환. 발표자 노트는 제외, 표 셀은 셀당 한 줄로 펼쳐짐(행/열 그룹 구조는 보존 안 됨). |
| `.xlsx`, 이미지 | **변환 안 됨** | 내장 변환기 없음 — 안내 메시지와 함께 보고. 수동 변환 필요. |

`factlog ingest` 는 변환된 텍스트를 KB의 **`runs/sources/`** 디렉터리(다른 생성
런 아티팩트와 같은 위치)에 기록합니다 — 사용자의 원본이 그대로 남아 있어야 하는
**`sources/` 에는 결코 쓰지 않습니다**. 변환본 파일명은 **원본의 전체 파일명(확장자
포함) + 변환 확장자**로 만들어지므로(`report.hwpx` → `runs/sources/report.hwpx.md`,
`report.pptx` → `runs/sources/report.pptx.md`), 같은 폴더에 이름이 같고 확장자만 다른
두 원본이 하나의 변환본으로 **충돌해 유실되는 일이 없습니다**. 하위 디렉터리에 있는
원본은 그 하위 구조를 그대로 미러링하므로(`sources/sub/report.pdf` →
`runs/sources/sub/report.pdf.md`), 서로 다른 폴더의 동일 이름 파일도 충돌하지 않습니다.
원본은 손대지 않으며, 변환본에는 출처(provenance) 헤더(소스, 변환기, 날짜)가 붙습니다.
`sources/` 와 `runs/sources/` 모두 추출이 읽는 유효한 소스 루트입니다.

> **업그레이드 안내(#213):** 변환본 파일명 규칙이 바뀌었습니다. 예전에는 원본의
> **어간(stem)**만 써서 `report.pdf` → `runs/sources/report.md` 였지만, 이제는
> 원본의 **전체 이름**을 써서 `runs/sources/report.pdf.md` 로 만듭니다. 이 덕분에
> 같은 폴더의 `report.hwpx`·`report.pptx` 가 각각 별도 변환본으로 보존됩니다.
> 기존에 적재된 KB의 구(舊) 어간 변환본(`runs/sources/report.md`)은 `factlog
> sources`/`coverage`/`status` 가 **어간 기반 폴백으로 계속 원본과 짝지어** 인식하므로
> 조용히 유실되지 않습니다. 새 레이아웃으로 옮기려면 `factlog ingest --scan --force`
> 를 다시 실행하십시오(이후 남은 구 변환본은 `factlog eject --orphans` 로 정리).
> 특히 어간이 충돌하던 KB는 재적재해야 유실되었던 원본이 복원됩니다.

*터미널에서 실행:*

```bash
factlog ingest report.docx --target ~/wiki   # → ~/wiki/runs/sources/report.docx.md (pandoc)
factlog ingest --scan --target ~/wiki        # auto-convert every binary under sources/
```

`/factlog sync` 는 첫 단계로 `factlog ingest --scan` 을 실행하므로, `sources/` 에
넣어 둔 바이너리는 자동으로 변환됩니다(멱등적으로 — 바뀌지 않은 파일은 건너뜀).
바이너리에 `runs/sources/` 변환본이 없으면 `merge_candidates.py` 가 경고하여,
조용한 비적재(non-ingestion)가 드러나게 합니다.
