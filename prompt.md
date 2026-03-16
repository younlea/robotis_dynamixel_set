**[Role & Objective]**
당신은 로보틱스, GUI 애플리케이션 개발, 그리고 크로스 플랫폼 배포에 능숙한 수석 파이썬 개발자입니다. 
윈도우(Windows), 우분투(Ubuntu), 맥(macOS) 환경에서 모두 동작하는 **Dynamixel 모터 ID 설정 전용 초경량 GUI 툴**을 개발하고, 사용자가 파이썬 환경 설정 없이 바로 실행할 수 있도록 **독립 실행형 바이너리(Standalone Executable) 빌드 구성 및 README 문서화**까지 완료해야 합니다.
공식 Dynamixel Wizard의 무거운 기능들을 배제하고, 오직 "연결 -> 현재 ID 스캔 -> 새로운 ID 부여" 라는 핵심 목적만 빠르고 직관적으로 수행할 수 있어야 합니다.

**[Tech Stack]**
- Language: Python 3
- GUI Framework: PyQt5
- Hardware Interface: `dynamixel_sdk`, `pyserial`
- Target Hardware: ROBOTIS Dynamixel XC330 (TTL 통신, Protocol 2.0)
- Packaging: `PyInstaller`

**[Functional Requirements]**
1. **Cross-Platform Serial Port Scanning:**
   - 실행 중인 OS를 감지하여 사용 가능한 시리얼 포트를 드롭다운 메뉴에 자동으로 목록화합니다. (Windows: `COM*`, Ubuntu: `/dev/ttyUSB*`, `/dev/ttyACM*`, macOS: `/dev/tty.usbserial*`, `/dev/tty.usbmodem*`)
   - UI에 "Refresh" 버튼을 두어 포트 목록을 갱신할 수 있게 하세요.

2. **Dynamixel Communication Logic (Protocol 2.0):**
   - XC330 모델에 맞춰 **Protocol 2.0**을 사용합니다.
   - Baudrate 선택 기능을 제공하되, 기본값은 `57600`으로 설정하세요.
   - 모터 스캔 시, ID 0부터 252까지 Ping을 보내어 응답하는 모터의 ID를 찾습니다.
   - **ID 변경 로직 주의사항 (중요):**
     - XC330의 ID Control Table Address는 `7` (1 Byte) 입니다.
     - EEPROM 영역인 ID를 변경하려면 반드시 Torque Enable(Address `64`, 1 Byte) 값이 `0` (Off) 상태여야 합니다.
     - 시퀀스: Torque Off -> ID Write -> 변경된 ID로 Ping 테스트하여 성공 여부 확인.

3. **UI/UX Layout (PyQt5):**
   화면은 작고 깔끔하게 구성하며, 다음 구역을 포함합니다.
   - **Section 1: Connection** (Port, Baudrate, Open/Close 토글)
   - **Section 2: Scan & Status** (Scan 버튼, 발견된 모터 ID 리스트. "ID 셋팅 시 모터를 1대만 연결하세요" 경고 문구 포함)
   - **Section 3: Setup ID** (현재 ID 표시, 0~252 입력 가능한 New ID 필드, Set Target ID 버튼)
   - **Section 4: Log Viewer** (QPlainTextEdit으로 연결 상태, Ping 결과, 에러 메시지 등을 출력)

4. **Error Handling & Stability:**
   - 포트 연결 실패, 케이블 분리 등 예외 상황에서 앱이 크래시되지 않도록 `try-except` 처리를 철저히 하세요.

**[Packaging & Release Requirements]**
사용자가 Python이나 모듈을 일일이 설치할 필요 없이 즉시 실행할 수 있도록 패키징해야 합니다.
1. `PyInstaller`를 사용하여 Windows, Ubuntu, macOS 각각에서 단일 실행 파일(One-file executable)을 만드는 명령어 또는 빌드 스크립트(`build.bat` 및 `build.sh`)를 작성해 주세요.
2. 실행 시 콘솔 창이 뜨지 않도록 Windowed mode(GUI only) 옵션을 포함하세요 (예: `--noconsole` 또는 `--windowed`).

**[Documentation Requirements (README.md)]**
최종 결과물과 함께 마크다운 형식의 `README.md` 파일을 작성해 주세요. 다음 내용이 반드시 포함되어야 합니다:
- 프로젝트 소개 및 목적
- **OS별 릴리즈 바이너리 실행 방법 (사용자용)** (예: "Release 탭에서 다운로드 후 실행...", macOS의 경우 보안 권한 허용 방법 등)
- 하드웨어 연결 주의사항 (동일 ID 충돌 방지를 위해 반드시 1대씩 연결하여 설정할 것)
- **개발자를 위한 소스코드 빌드 방법** (Python 가상환경 설정, 요구 패키지 설치, PyInstaller 빌드 명령어 등)

**[Deliverables]**
1. 메인 파이썬 소스 코드 (`main.py`)
2. 빌드 스크립트 (`build.bat`, `build.sh` 또는 구체적인 PyInstaller 명령어)
3. 상세하게 작성된 `README.md` 파일