FROM node:22-alpine
WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY tsconfig.json ./
COPY src ./src
EXPOSE 6060
CMD ["npx", "tsx", "src/index.ts"]
