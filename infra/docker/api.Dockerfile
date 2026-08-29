# syntax=docker/dockerfile:1.12

FROM eclipse-temurin:25.0.4_7-jdk-noble@sha256:534968c051301957beae735e7ba1db54d99ddecf08746d3b9d4f318cc132dbc3 AS build

WORKDIR /workspace

COPY backend/gradle ./gradle
COPY backend/gradle.properties backend/gradlew backend/settings.gradle.kts backend/build.gradle.kts ./
RUN ./gradlew --no-daemon help

COPY backend/src/main ./src/main
RUN ./gradlew --no-daemon clean bootJar \
    && mkdir /out \
    && cp build/libs/our-ledger-backend-0.1.0-SNAPSHOT.jar /out/app.jar

COPY infra/docker/HttpHealthCheck.java /tmp/HttpHealthCheck.java
RUN javac --release 25 -d /out/healthcheck /tmp/HttpHealthCheck.java

FROM gcr.io/distroless/java25-debian13:nonroot@sha256:fce4a1d66284e8866c46113d9bdc286c46fb8c3c3f0a098f877034349e88debe AS runtime

WORKDIR /app

COPY --from=build --chown=65532:65532 /out/app.jar /app/app.jar
COPY --from=build --chown=65532:65532 /out/healthcheck /opt/healthcheck

USER 65532:65532
EXPOSE 8080
STOPSIGNAL SIGTERM

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
