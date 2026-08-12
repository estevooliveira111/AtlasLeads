# Use the official Playwright Python image
FROM mcr.microsoft.com/playwright/python:v1.52.0-jammy

# Set the working directory in the container
WORKDIR /app

# Copy only what's needed to build/install the package first (better layer caching)
COPY pyproject.toml README.md ./
COPY src ./src

# Install the package and its dependencies
RUN pip install --no-cache-dir .

# Install Playwright browsers (already in the image, but ensures everything is set)
RUN playwright install chromium

# Create the output directory
RUN mkdir -p output

# Set environment variable to run Playwright headlessly
ENV HEADLESS=true

# Command to run the scraper
# You can override the arguments when running the container
ENTRYPOINT ["atlasleads"]
CMD ["-s", "restaurantes em São Paulo", "-t", "10"]
