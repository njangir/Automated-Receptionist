
"""Clean Python cache files before bundling with PyInstaller."""
import os
import shutil
from pathlib import Path

def clean_pycache(root_dir: Path):
    """Remove all __pycache__ directories and .pyc files."""
    removed_count = 0
    removed_size = 0

    for root, dirs, files in os.walk(root_dir):

        if '__pycache__' in dirs:
            cache_dir = Path(root) / '__pycache__'
            try:

                for file in cache_dir.rglob('*'):
                    if file.is_file():
                        removed_size += file.stat().st_size

                shutil.rmtree(cache_dir)
                removed_count += 1
                print(f"Removed: {cache_dir}")
            except Exception as e:
                print(f"Error removing {cache_dir}: {e}")

        for file in files:
            if file.endswith(('.pyc', '.pyo')):
                file_path = Path(root) / file
                try:
                    removed_size += file_path.stat().st_size
                    file_path.unlink()
                    removed_count += 1
                    print(f"Removed: {file_path}")
                except Exception as e:
                    print(f"Error removing {file_path}: {e}")

    print(f"\nCleaned {removed_count} cache directories/files")
    print(f"Freed {removed_size / 1024:.2f} KB")
    return removed_count, removed_size

if __name__ == "__main__":
    project_root = Path(__file__).parent
    print(f"Cleaning Python cache files in: {project_root}")
    print("-" * 60)
    clean_pycache(project_root)
    print("-" * 60)
    print("Cache cleanup complete. Ready for PyInstaller bundling.")
