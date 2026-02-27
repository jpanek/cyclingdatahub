#!/bin/bash

# Define the output file
OUTPUT_FILE="project_dump.txt"

# Clear the file if it exists
> "$OUTPUT_FILE"

echo "Dumping project files to $OUTPUT_FILE..."

# Find files, exclude hidden stuff and pycache
# Focused on .py, .html, and .sql files
find . -maxdepth 3 \
    -not -path '*/.*' \
    -not -path '*/__pycache__*' \
    -not -path './venv*' \
    \( -name "*.py" -o -name "*.html" -o -name "*.sql" \) | while read -r file; do
    
    # Remove the './' prefix for cleaner headers
    clean_path=${file#./}
    
    echo "# $clean_path" >> "$OUTPUT_FILE"
    cat "$file" >> "$OUTPUT_FILE"
    echo -e "\n---\n" >> "$OUTPUT_FILE"
done

echo "Done! You can now copy the content of $OUTPUT_FILE."
