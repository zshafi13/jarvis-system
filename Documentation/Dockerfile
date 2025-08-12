# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app/DocGenSite

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r /app/DocGenSite/requirements.txt

# Expose the port MkDocs will serve on
EXPOSE 8000

# Command to build the MkDocs site
RUN mkdocs build --clean --site-dir /app/DocGenSite/site -f /app/DocGenSite/mkdocs.yml

# Default command to serve the MkDocs site
CMD ["mkdocs", "serve", "-a", "0.0.0.0:8000"]
