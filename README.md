# Dynamixel ID Setter

> **XC330 모터 ID를 빠르고 간편하게 변경하는 초경량 크로스 플랫폼 GUI 툴**

공식 Dynamixel Wizard의 무거운 기능 없이, **연결 → 스캔 → ID 변경** 핵심 워크플로우만 수행합니다.

| Feature | Detail |
|---------|--------|
| Protocol | Dynamixel Protocol 2.0 |
| Target Motor | ROBOTIS XC330 (TTL) |
| GUI | PyQt5 (Dark Theme) |
| Platforms | Windows · Ubuntu · macOS |

---

## 🚀 Quick Start — 실행 방법 (사용자용)

본 툴은 파이썬 설치 없이 실행 가능한 **독립형 바이너리(Standalone Executable)** 빌드를 지원합니다.

### 1. 직접 빌드하여 사용하기 (가장 확실한 방법)
현재 프로젝트에는 빌드 스크립트가 포함되어 있습니다. 본인의 OS에서 다음 스크립트를 실행하면 `dist/` 폴더 내에 실행 파일이 생성됩니다.
- **Windows:** `build.bat` 실행
- **Linux / macOS:** `./build.sh` 실행

### 2. 배포된 바이너리 사용
개발자가 빌드 후 GitHub [Releases](../../releases) 탭에 업로드한 경우, 해당 탭에서 본인의 OS에 맞는 파일을 다운로드하여 즉시 사용할 수 있습니다. (현재는 소스코드와 빌드 스크립트가 제공되는 단계입니다.)

### Ubuntu / Linux
```bash
chmod +x DynamixelIDSetter
./DynamixelIDSetter
```
> 시리얼 포트 권한이 필요할 수 있습니다:
> ```bash
> sudo usermod -aG dialout $USER
> # 로그아웃 후 재로그인
> ```

### macOS
```bash
chmod +x DynamixelIDSetter
./DynamixelIDSetter
```
> **보안 경고 해제:**
> `시스템 설정 → 개인정보 보호 및 보안 → "확인 없이 열기"` 를 클릭하거나,
> 터미널에서 실행:
> ```bash
> xattr -d com.apple.quarantine DynamixelIDSetter
> ```

---

## ⚠️ 하드웨어 연결 주의사항

> **반드시 모터를 1대만 연결한 상태에서 ID를 변경하세요!**
>
> 같은 ID를 가진 모터가 여러 대 연결되면 통신 충돌이 발생하여 정상적인 ID 변경이 불가능합니다.

### 사용 순서
1. XC330 모터 **1대만** USB2Dynamixel / U2D2 에 연결
2. 프로그램 실행 → 포트 선택 → **Open**
3. **Scan** 클릭 → 현재 ID 확인
4. New ID 입력 → **Set Target ID** 클릭
5. 로그에서 성공 메시지 확인 후, 다음 모터 연결

---

## 🛠 개발자 빌드 가이드

### 1. 환경 설정

```bash
# 가상환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### 2. 소스 실행

```bash
python main.py
```

### 3. 독립 실행 파일 빌드

#### Linux / macOS
```bash
chmod +x build.sh
./build.sh
# 결과: dist/DynamixelIDSetter
```

#### Windows
```cmd
build.bat
REM 결과: dist\DynamixelIDSetter.exe
```

#### 직접 빌드 명령어
```bash
pyinstaller --onefile --noconsole --name DynamixelIDSetter --clean main.py
```

### 4. 프로젝트 구조

```
robotis_dynamixel_set/
├── main.py              # 메인 애플리케이션 (GUI + 통신 로직)
├── requirements.txt     # Python 의존성
├── build.sh             # Linux/macOS 빌드 스크립트
├── build.bat            # Windows 빌드 스크립트
└── README.md            # 이 문서
```

---

## 📋 기술 상세

| 항목 | 값 |
|------|-----|
| ID Address | `7` (1 Byte, EEPROM) |
| Torque Enable Address | `64` (1 Byte) |
| 스캔 범위 | ID 0 ~ 252 |
| 기본 Baudrate | 57600 bps |
| 지원 Baudrate | 9600, 57600, 115200, 1M, 2M, 3M, 4M |

**ID 변경 시퀀스:** Torque Off → ID 쓰기 → 새 ID로 Ping 검증

---

## License

MIT License
