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


def prepare_input_views(tools, paths):
    """Normalize subject-local links for containers, including host-absolute links.

    A private read-only input view contains only requested files and completion
    metadata. Regular files use hard links where possible; source bytes/modes
    are never changed. Absolute host link targets never become container grants.
    """
    import hashlib,json,os,shutil
    roots=list(tools.input_roots);observations={}
    for index,root in enumerate(tools.input_roots):
        selected=[p for p in paths if p.startswith(f'/inputs/{index}/')]
        entries=[];has_link=False
        for mapped in selected:
            original=root/mapped.split('/',3)[3]
            target=resolve_input(original,root)
            linked=any(p.is_symlink() for p in (original,*original.parents) if p.is_relative_to(root))
            has_link |= linked
            entries.append((original,target))
            if linked:
                observations[mapped]={'original':mapped,'target':str(original.readlink()) if original.is_symlink() else 'internal directory link',
                    'resolved':f'/inputs/{index}/'+target.relative_to(root).as_posix(),
                    'policy':'Resolved inside the same registered subject; sandbox link normalized to a relative target'}
        if not has_link:continue
        for name in ('recon-all.done','recon-all.log','recon-surf.done','recon-surf.log'):
            original=root/'scripts'/name
            if original.is_file():entries.append((original,resolve_input(original,root)))
        fingerprint=hashlib.sha256(json.dumps([(str(a.relative_to(root)),str(b.relative_to(root)),b.stat().st_size,b.stat().st_mtime_ns) for a,b in entries]).encode()).hexdigest()
        view=tools.control_store.root/'input_views'/str(index)/fingerprint
        if not view.exists():
            view.mkdir(parents=True)
            for original,target in entries:
                actual=view/target.relative_to(root);actual.parent.mkdir(parents=True,exist_ok=True)
                if not actual.exists():
                    from .analysis_agent import _parent_fd, _read_regular
                    try:
                        with _parent_fd(target, root) as descriptor:
                            os.link(target.name if descriptor is not None else target, actual,
                                    **({"src_dir_fd": descriptor} if descriptor is not None else {}),
                                    follow_symlinks=False)
                    except OSError:
                        limit = 512 * 1024 * 1024
                        raw = _read_regular(target, root, limit + 1)
                        if len(raw) > limit:
                            raise ValueError("Cross-filesystem input view file exceeds 512 MiB")
                        actual.write_bytes(raw)
                alias=view/original.relative_to(root)
                alias.parent.mkdir(parents=True,exist_ok=True)
                if alias!=actual and not alias.exists():alias.symlink_to(os.path.relpath(actual,alias.parent))
        roots[index]=view
    if hasattr(tools.executor,'input_roots'):tools.executor.input_roots=roots
    return observations
