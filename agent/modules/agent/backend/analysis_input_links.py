"""Subject-local read-only links; workspace writes retain strict no-link rules."""
from pathlib import Path


def resolve_input(path, root):
    path, root = Path(path), Path(root)
    if root.is_symlink() or not path.is_relative_to(root):
        raise ValueError("Input must be inside its registered subject root")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root.resolve(strict=True)):
        raise ValueError("Input symlink points outside its registered subject root")
    return resolved
