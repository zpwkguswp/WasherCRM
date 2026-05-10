# WasherCRM 모바일 앱 전환 계획서 (Cross-Platform: Android & iOS)

## 1. 개요 (Objective)
* 현재 웹 기반의 WasherCRM을 하이브리드 앱(Capacitor)으로 전환.
* 안드로이드와 iOS 양대 플랫폼 지원.
* 실시간 푸시 알림(Push Notifications) 시스템 구축을 통한 업무 효율성 증대.

## 2. 기술 스택 (Technology Stack)
* **App Framework**: [Capacitor](https://capacitorjs.com/) (웹 코드를 네이티브 앱으로 래핑)
* **Push Engine**: [Firebase Cloud Messaging (FCM)](https://firebase.google.com/docs/cloud-messaging) - Android/iOS 통합 알림 서버
* **Backend**: 기존 FastAPI (Python) 유지 및 알림 발송 로직 추가
* **Frontend**: 기존 HTML/JS/CSS 유지 (모바일 UI 최적화 작업 포함)

## 3. 단계별 이행 로드맵 (Implementation Phases)

| 단계 | 주요 작업 내용 | 비고 |
| :--- | :--- | :--- |
| **1단계: 인프라 구축** | Capacitor 초기화, Android/iOS 플랫폼 추가, Firebase 프로젝트 생성 | 개발 환경 세팅 |
| **2단계: UI/UX 최적화** | 모바일용 상단 상태바(Safe Area) 대응, 터치 반응 개선, 모바일 전용 CSS 적용 | `admin.html` 수정 |
| **3단계: 푸시 알림 연동** | 기기별 토큰 발급 로직 구현, 백엔드 DB에 토큰 저장 API 추가 | **핵심 기능** |
| **4단계: 백엔드 트리거** | 결제 완료/수리 배정/상태 변경 시 알림 자동 발송 로직 작성 | FastAPI 수정 |
| **5단계: 빌드 및 테스트** | APK(안드로이드) 및 앱 번들(iOS) 빌드, 기기 테스트 |  |

## 4. 플랫폼별 특이사항 (Android vs iOS)
* **Android**:
    * 상대적으로 개발 및 배포가 자유로움.
    * Firebase 연동이 간단함.
* **iOS (Apple)**:
    * **Mac PC가 필요함**: 최종 빌드를 위해서는 Xcode를 실행할 수 있는 Mac이 필수입니다.
    * **Apple Developer Program**: 연회비($99)가 있으며, 실제 기기 테스트 및 앱스토어 배포를 위해 필요합니다.
    * **APNs 연동**: Firebase를 통하더라도 애플의 알림 서버(APNs) 설정이 추가로 필요합니다.

## 5. 기대 효과
* **실시간 대응**: 세탁 수리 요청이 들어오면 기사님께 즉시 팝업 알림 발송.
* **브랜드 신뢰도**: 고객에게 "WasherCRM 앱"이라는 전문적인 이미지 제공.
* **접근성**: 홈 화면에 아이콘이 있어 브라우저를 열지 않고도 즉시 업무 처리 가능.
