# Stage 1: Build the application
FROM node:20-alpine AS build

WORKDIR /app

# Copy package files and install dependencies
COPY package*.json ./
RUN npm install

# Copy the rest of the application code
COPY . .

# Build the static files using Vite
RUN npm run build

# Stage 2: Serve the application
FROM nginx:stable-alpine

# Copy the build output from the first stage to Nginx's public folder
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# Expose port 80 for the web server
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
