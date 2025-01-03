# Use an official Python runtime as a parent image.
FROM python:3.12

# Install system dependencies, including Tesseract
RUN apt-get update \
    && apt-get -y install tesseract-ocr \
    && apt-get -y install libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container.
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the FastAPI app code into the container
COPY . .

# Expose the port the app runs on.
EXPOSE 8000


# Command to run Gunicorn with Uvicorn workers
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:8080"]
