# 설치

> 🌐 [English](install.en.md) | **한국어**

## 요구 사항

- Python **3.11+** (엔진 의존성 `pyrewire` 가 요구)
- **pyrewire 1.0.3+** (`pip install -r requirements.txt`)
- Claude Code CLI
- **git** — 마켓플레이스 설치가 내부적으로 `git clone`을 사용합니다. Windows에서는 **Git for Windows**를 설치하세요.

## 설치

factlog는 **Claude Code 플러그인**입니다. Claude Code 세션에서 이 저장소의
마켓플레이스로부터 설치합니다.

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

`setup` 은 `doctor` 실행, 엔진 의존성(`pyrewire`) 설치, KB 스캐폴딩, 환경 재점검을
한 명령으로 수행합니다. KB는 기본적으로 홈 디렉터리 아래 `~/wiki` 에 만들어지며
(다른 위치는 `/factlog setup --target <경로>`), setup 요약에 그 **절대경로**가
출력됩니다. 이후 검증할 문서는 그 폴더의 **`sources/`** 에 넣습니다(위
[KB 폴더 구조](concepts.md#kb-폴더-구조--내-파일은-어디에-넣나) 참고).

Windows에서 `python` / `python3` 실행 파일 문제로 `setup` 이 실패하면 상세 레퍼런스의
[Windows Python 실행 파일](../reference/windows.md#windows-python-실행-파일) 절을 참고하십시오.

### 로컬 설치 (개발용)

로컬 클론에 대해 개발하려면, 작업 트리 자체를 마켓플레이스로 등록하십시오.

*Claude Code에서 실행:*

```
/plugin marketplace add ~/git/semantic-reasoning/factlog
/plugin install factlog@semantic-reasoning
/reload-plugins
/factlog setup
```

### `/factlog setup` 이 하는 일

`setup` 은 이전에 분리돼 있던 설치 후 단계들을 한 명령으로 합칩니다. 수동으로 하면
동등하게 다음과 같습니다.

*터미널에서 실행:*

```bash
pip install -r ~/git/semantic-reasoning/factlog/requirements.txt   # pyrewire>=1.0.3,<2.0
python3 -m factlog doctor          # checks Python 3.11+ and pyrewire
python3 -m factlog init --target ~/wiki   # scaffold the KB layout
```
