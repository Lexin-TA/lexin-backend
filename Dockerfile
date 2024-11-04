# Use an official Python runtime as a parent image.
FROM python:3.12

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

# Command to run the FastAPI app with uvicorn.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
