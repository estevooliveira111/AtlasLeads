# Use the official Playwright Python image
FROM mcr.microsoft.com/playwright/python:v1.52.0-jammy

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (already in the image, but ensures everything is set)
RUN playwright install chromium

# Copy the rest of the application code
COPY . .

# Create the output directory
RUN mkdir -p "AtlasLeads"

# Set environment variable to run Playwright headlessly
ENV HEADLESS=true

# Command to run the scraper
# You can override the arguments when running the container
ENTRYPOINT ["python3", "main.py"]
CMD ["-s", "restaurantes em São Paulo", "-t", "10"]
