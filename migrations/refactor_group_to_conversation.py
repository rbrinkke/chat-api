#!/usr/bin/env python3
"""
Automated refactoring script: group → conversation
Renames all occurrences throughout the Chat API codebase.

Usage:
    python migrations/refactor_group_to_conversation.py --dry-run  # Preview changes
    python migrations/refactor_group_to_conversation.py --execute  # Apply changes
"""

import os
import re
import shutil
from pathlib import Path
from typing import List, Tuple, Dict
import argparse


class RefactorEngine:
    """Automated refactoring engine for group → conversation rename."""

    def __init__(self, root_dir: Path, dry_run: bool = True):
        self.root_dir = root_dir
        self.dry_run = dry_run
        self.changes: List[Tuple[Path, str, str]] = []
        self.file_renames: List[Tuple[Path, Path]] = []

    # ======================================================================
    # PHASE 1: Text Replacements (In-File Content)
    # ======================================================================

    REPLACEMENTS = [
        # Classes & Types
        (r'\bGroupService\b', 'ConversationService'),
        (r'\bGroupDetails\b', 'ConversationDetails'),

        # Functions & Methods
        (r'\bget_group_service\b', 'get_conversation_service'),
        (r'\bget_group_details\b', 'get_conversation_details'),
        (r'\binvalidate_group_cache\b', 'invalidate_conversation_cache'),

        # Variables & Parameters (common patterns)
        (r'\bgroup_service:', 'conversation_service:'),
        (r'\bgroup_service\s*=', 'conversation_service ='),
        (r'\bself\.group_service\b', 'self.conversation_service'),
        (r'\bgroup_id:', 'conversation_id:'),
        (r'\bgroup_id\s*=', 'conversation_id ='),
        (r'\bgroup_name:', 'conversation_name:'),
        (r'\bgroup_name\s*=', 'conversation_name ='),

        # Path parameters in routes
        (r'/groups/\{group_id\}', '/conversations/{conversation_id}'),
        (r'@router\.(get|post|put|delete|websocket)\("(/[^"]*)/groups/', r'@router.\1("\2/conversations/'),

        # Cache keys
        (r'org:\{[^}]+\}:group:', 'org:{org_id}:conversation:'),
        (r'"org:[^:]+:group:', '"org:{org_id}:conversation:'),

        # Log messages & strings (case-sensitive)
        (r'group_cache_hit', 'conversation_cache_hit'),
        (r'group_cache_miss', 'conversation_cache_miss'),
        (r'group_fetched', 'conversation_fetched'),
        (r'group_not_found', 'conversation_not_found'),
        (r'group_service', 'conversation_service'),
        (r'api_create_message.*group_id=', 'api_create_message, conversation_id='),

        # Dictionary keys in connection manager
        (r'active_connections\[group_id\]', 'active_connections[conversation_id]'),

        # Comments & docstrings (keep "group" in Auth API context)
        (r'Group UUID from Auth-API', 'Conversation UUID (maps to Auth-API group for RBAC)'),
        (r'group data from Auth-API', 'conversation data from Auth-API'),
        (r'Fetch group details', 'Fetch conversation details'),
    ]

    # MongoDB field renames (handled separately in migration script)
    MONGODB_FIELDS = {
        'group_id': 'conversation_id',
        'group_name': 'conversation_name'
    }

    # Files to exclude from text replacement
    EXCLUDE_PATTERNS = [
        '*.pyc',
        '__pycache__',
        '.git',
        'venv',
        '.env',
        '*.md',  # We'll handle docs separately
        'migrations/refactor_group_to_conversation.py',  # Don't modify self!
    ]

    def should_process_file(self, file_path: Path) -> bool:
        """Check if file should be processed."""
        # Check exclusions
        for pattern in self.EXCLUDE_PATTERNS:
            if file_path.match(pattern):
                return False

        # Only process Python files for now
        return file_path.suffix == '.py'

    def apply_replacements(self, content: str, file_path: Path) -> Tuple[str, int]:
        """Apply all text replacements to content."""
        modified_content = content
        changes_count = 0

        for pattern, replacement in self.REPLACEMENTS:
            new_content, count = re.subn(pattern, replacement, modified_content)
            if count > 0:
                changes_count += count
                modified_content = new_content
                print(f"  ✓ {pattern} → {replacement} ({count} occurrences)")

        return modified_content, changes_count

    def process_file(self, file_path: Path):
        """Process a single file for refactoring."""
        if not self.should_process_file(file_path):
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                original_content = f.read()

            modified_content, changes_count = self.apply_replacements(original_content, file_path)

            if changes_count > 0:
                self.changes.append((file_path, original_content, modified_content))
                print(f"\n📝 {file_path.relative_to(self.root_dir)}: {changes_count} changes")

                if not self.dry_run:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(modified_content)

        except Exception as e:
            print(f"❌ Error processing {file_path}: {e}")

    # ======================================================================
    # PHASE 2: File Renames
    # ======================================================================

    FILE_RENAMES = {
        'app/services/group_service.py': 'app/services/conversation_service.py',
        'tests/test_groups.py': None,  # DELETE (obsolete)
    }

    def rename_files(self):
        """Rename or delete files."""
        for old_path_str, new_path_str in self.FILE_RENAMES.items():
            old_path = self.root_dir / old_path_str

            if not old_path.exists():
                print(f"⚠️  {old_path_str} not found, skipping")
                continue

            if new_path_str is None:
                # DELETE file
                print(f"\n🗑️  DELETE: {old_path_str}")
                if not self.dry_run:
                    old_path.unlink()
            else:
                # RENAME file
                new_path = self.root_dir / new_path_str
                print(f"\n📦 RENAME: {old_path_str} → {new_path_str}")
                self.file_renames.append((old_path, new_path))

                if not self.dry_run:
                    shutil.move(str(old_path), str(new_path))

    # ======================================================================
    # PHASE 3: Import Statement Updates
    # ======================================================================

    def fix_imports(self):
        """Fix import statements after file renames."""
        import_replacements = [
            (r'from app\.services\.group_service import', 'from app.services.conversation_service import'),
        ]

        print("\n🔧 Fixing import statements...")

        for py_file in self.root_dir.rglob('*.py'):
            if not self.should_process_file(py_file):
                continue

            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                modified = content
                for pattern, replacement in import_replacements:
                    modified = re.sub(pattern, replacement, modified)

                if modified != content:
                    print(f"  ✓ Fixed imports in {py_file.relative_to(self.root_dir)}")
                    if not self.dry_run:
                        with open(py_file, 'w', encoding='utf-8') as f:
                            f.write(modified)

            except Exception as e:
                print(f"  ❌ Error fixing imports in {py_file}: {e}")

    # ======================================================================
    # Main Execution
    # ======================================================================

    def run(self):
        """Run the complete refactoring process."""
        print("=" * 70)
        print("🔄 Chat API Refactoring: group → conversation")
        print("=" * 70)
        print(f"Mode: {'DRY RUN (preview only)' if self.dry_run else 'EXECUTE (applying changes)'}")
        print(f"Root: {self.root_dir}")
        print()

        # Phase 1: Text replacements in all Python files
        print("\n📋 PHASE 1: Text Replacements")
        print("-" * 70)

        python_files = list(self.root_dir.rglob('*.py'))
        print(f"Processing {len(python_files)} Python files...")

        for py_file in python_files:
            self.process_file(py_file)

        # Phase 2: File renames
        print("\n\n📋 PHASE 2: File Renames")
        print("-" * 70)
        self.rename_files()

        # Phase 3: Fix imports after renames
        print("\n\n📋 PHASE 3: Import Fixes")
        print("-" * 70)
        self.fix_imports()

        # Summary
        print("\n\n" + "=" * 70)
        print("📊 SUMMARY")
        print("=" * 70)
        print(f"Files modified: {len(self.changes)}")
        print(f"Files renamed: {len(self.file_renames)}")
        print(f"Total changes: {sum(len(c[2]) - len(c[1]) for c in self.changes)} characters")

        if self.dry_run:
            print("\n⚠️  DRY RUN MODE - No changes were applied")
            print("Run with --execute to apply changes")
        else:
            print("\n✅ Changes applied successfully!")
            print("\nNext steps:")
            print("1. Run MongoDB migration: python migrations/migrate_mongodb_fields.py")
            print("2. Update test_rbac.sh with new /conversations/ endpoints")
            print("3. Run tests: pytest")
            print("4. Rebuild Docker: docker compose build --no-cache")


def main():
    parser = argparse.ArgumentParser(
        description="Refactor Chat API: group → conversation"
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Apply changes (default is dry-run preview)'
    )
    parser.add_argument(
        '--root',
        type=Path,
        default=Path(__file__).parent.parent,
        help='Root directory of Chat API project'
    )

    args = parser.parse_args()

    engine = RefactorEngine(
        root_dir=args.root,
        dry_run=not args.execute
    )

    engine.run()


if __name__ == '__main__':
    main()
