FROM python:3.13.2-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
# Ensure requirements.txt is in the Master subdirectory of the build context
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Upgrade pip and install dependencies without caching
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code from the Master directory into the container at /app
COPY . .

# Run client.py and then master.py when the container launches
CMD ["sh", "-c", "python client.py && python master.py"]
