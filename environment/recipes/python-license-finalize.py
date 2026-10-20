from pathlib import Path
from importlib import metadata as m
root=Path('/data/xuancheng/structural_env')
licenses=root/'licenses/python-distributions'
licenses.mkdir(exist_ok=True)
for dist in m.distributions():
    folder=licenses/(dist.metadata['Name']+'-'+dist.version)
    folder.mkdir(exist_ok=True)
    (folder/'METADATA.txt').write_text(dist.read_text('METADATA') or '',encoding='utf-8')
    for file in dist.files or []:
        name=str(file).lower()
        if '.dist-info/' in name and ('license' in name or 'copying' in name or 'notice' in name):
            source=Path(dist.locate_file(file))
            if source.is_file():
                destination=folder/str(file).split('.dist-info/',1)[1]
                destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes(source.read_bytes())
print('PYTHON_LICENSE_RECORDS_COMPLETE')
