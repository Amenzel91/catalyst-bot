# How to Delete Files from Git Repository

You want to wipe the repository to push your stable version. Here are the different ways to delete files:

## Option 1: Delete All Files (Complete Wipe)

To delete ALL tracked files and start fresh:

```bash
# Remove all tracked files from git (but keep .git directory)
git rm -r --cached .

# Delete all files from working directory (except .git)
find . -not -path './.git*' -delete

# Or more safely, delete specific directories/files you want to remove:
rm -rf src/ tests/ scripts/ jobs/ patches/
rm -f *.py *.md *.txt *.js requirements.txt pyproject.toml

# Add and commit the deletions
git add -A
git commit -m "Remove all files to prepare for stable version"
```

## Option 2: Delete Specific Files/Directories

To delete specific files or directories:

```bash
# Delete specific files
git rm file1.txt file2.py
git rm hello.txt main.py

# Delete entire directories
git rm -r src/
git rm -r tests/
git rm -r scripts/

# Commit the deletions
git commit -m "Remove unwanted files"
```

## Option 3: Interactive Deletion

To see what you're deleting before you do it:

```bash
# List all tracked files
git ls-files

# Remove files one by one with confirmation
git rm -i *.txt
git rm -r -i tests/

# Commit when done
git commit -m "Cleaned up repository"
```

## Option 4: Keep Only Specific Files

If you want to keep only certain files (like .gitignore, README):

```bash
# Remove everything except specific files
git ls-files | grep -v -E '\.gitignore|README\.md|LICENSE' | xargs git rm

# Commit the changes
git commit -m "Keep only essential files"
```

## After Deletion

Once you've deleted the files you want to remove:

1. **Add your stable version files:**
   ```bash
   # Copy your stable files to the repository directory
   cp -r /path/to/your/stable/version/* .
   
   # Add the new files
   git add .
   
   # Commit your stable version
   git commit -m "Add stable version"
   ```

2. **Push the changes:**
   ```bash
   git push origin your-branch-name
   ```

## Safety Tips

- **Always backup your stable version** before making changes
- **Work on a branch** rather than directly on main:
  ```bash
  git checkout -b cleanup-for-stable
  ```
- **Review changes** before committing:
  ```bash
  git status
  git diff --cached
  ```

## Current Repository Status

Your repository currently contains:
- Python source code in `src/`
- Tests in `tests/`
- Scripts in `scripts/`
- Job files in `jobs/`
- Patches in `patches/`
- Configuration files (`.env.staging`, `pyproject.toml`, etc.)
- Documentation files (multiple `.md` files)
- Data files (`hello.txt`, `out.txt`, etc.)

Choose the deletion method that best fits your needs!