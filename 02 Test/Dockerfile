# =============================================================================
# Dockerfile - Kogito DMN Service (Quarkus)
# =============================================================================
# Multi-stage build:
#   Stage 1: Compilación Maven del proyecto Quarkus + Kogito con archivos DMN
#   Stage 2: Imagen ligera de ejecución con JRE 17
# =============================================================================

# --- Stage 1: Build ---
FROM maven:3.9.6-eclipse-temurin-17 AS build

WORKDIR /app

# Copiar pom.xml primero para cachear dependencias
COPY kogito-app/pom.xml ./pom.xml
RUN mvn dependency:go-offline -B

# Copiar código fuente y archivos DMN
COPY kogito-app/src ./src

# Compilar el proyecto Quarkus
RUN mvn package -DskipTests -B

# --- Stage 2: Runtime ---
FROM eclipse-temurin:17-jre-jammy

WORKDIR /app

# Copiar artefactos del fast-jar de Quarkus
COPY --from=build /app/target/quarkus-app/lib/ ./lib/
COPY --from=build /app/target/quarkus-app/*.jar ./
COPY --from=build /app/target/quarkus-app/app/ ./app/
COPY --from=build /app/target/quarkus-app/quarkus/ ./quarkus/

EXPOSE 8080

ENV JAVA_OPTS="-Xms128m -Xmx512m"

CMD ["java", "-jar", "quarkus-run.jar"]
