# Backend

Java 25 + Spring Boot 4.1.1 + Gradle + PostgreSQL/Flyway 기반 API가 위치한다.

Slice 0 bootstrap 전에는 구현 파일을 추가하지 않는다. bootstrap 후 권장 시작 구조는 다음과 같다.

```text
backend/
├─ build.gradle.kts
├─ settings.gradle.kts
├─ gradlew
├─ gradle/wrapper/
└─ src/
   ├─ main/java/
   ├─ main/resources/db/migration/
   └─ test/java/
```

패키지는 계층만 나열하는 전역 구조보다 도메인·기능 응집도를 우선한다. 상세 구조는 첫 backend Issue에서 확정한다.
