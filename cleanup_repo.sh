#!/bin/bash

# Safe Repository Cleanup Script
# This script helps you safely delete files from your git repository

set -e  # Exit on any error

echo "=== Git Repository Cleanup Helper ==="
echo ""

# Show current status
echo "Current repository status:"
git status --short
echo ""

# Show current files
echo "Current tracked files (first 20):"
git ls-files | head -20
echo ""

# Safety check
read -p "Do you want to proceed with file deletion? (y/N): " confirm
if [[ $confirm != [yY] ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "Choose deletion option:"
echo "1. Delete ALL files (complete wipe)"
echo "2. Delete specific directories"
echo "3. Delete specific files"
echo "4. Show me what would be deleted (dry run)"
echo ""

read -p "Enter your choice (1-4): " choice

case $choice in
    1)
        echo "WARNING: This will delete ALL tracked files!"
        read -p "Are you absolutely sure? Type 'DELETE ALL' to confirm: " final_confirm
        if [[ $final_confirm == "DELETE ALL" ]]; then
            echo "Removing all tracked files..."
            git rm -r --cached .
            find . -not -path './.git*' -not -name 'HOW_TO_DELETE_FILES.md' -not -name 'cleanup_repo.sh' -type f -delete
            echo "All files removed. Don't forget to commit: git add -A && git commit -m 'Remove all files'"
        else
            echo "Cancelled for safety."
        fi
        ;;
    2)
        echo "Available directories to delete:"
        find . -type d -not -path './.git*' | grep -v '^\.$' | head -10
        echo ""
        read -p "Enter directory names to delete (space-separated): " dirs
        for dir in $dirs; do
            if [[ -d "$dir" ]]; then
                echo "Removing directory: $dir"
                git rm -r "$dir" 2>/dev/null || rm -rf "$dir"
            fi
        done
        echo "Directories removed. Commit with: git add -A && git commit -m 'Remove selected directories'"
        ;;
    3)
        echo "Current files:"
        ls -la | grep '^-' | head -10
        echo ""
        read -p "Enter filenames to delete (space-separated): " files
        for file in $files; do
            if [[ -f "$file" ]]; then
                echo "Removing file: $file"
                git rm "$file" 2>/dev/null || rm "$file"
            fi
        done
        echo "Files removed. Commit with: git add -A && git commit -m 'Remove selected files'"
        ;;
    4)
        echo "=== DRY RUN - What would be deleted ==="
        echo ""
        echo "All tracked files that would be removed:"
        git ls-files
        echo ""
        echo "Total tracked files: $(git ls-files | wc -l)"
        echo "Total directories: $(find . -type d -not -path './.git*' | wc -l)"
        echo ""
        echo "This was a dry run - no files were actually deleted."
        ;;
    *)
        echo "Invalid choice. Exiting."
        exit 1
        ;;
esac

echo ""
echo "=== Cleanup Complete ==="
echo "Next steps:"
echo "1. Review changes: git status"
echo "2. Commit deletions: git add -A && git commit -m 'Your commit message'"
echo "3. Add your stable version files"
echo "4. Commit new files: git add . && git commit -m 'Add stable version'"
echo "5. Push changes: git push origin your-branch"