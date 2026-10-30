# Build from the REPOSITORY ROOT:  docker build -f apps/web/Dockerfile -t pathforge-web .
# NEXT_PUBLIC_API_URL is compiled into the browser bundle: set it to the URL the BROWSER uses to reach the API.
FROM node:20-alpine AS build
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
ARG NEXT_PUBLIC_API_URL=http://localhost:8000/api
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
RUN addgroup -S web && adduser -S web -G web && chown -R web:web /app
USER web
EXPOSE 3000
CMD ["node", "server.js"]
