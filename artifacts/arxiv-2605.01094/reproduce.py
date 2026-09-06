"""Reproduce the reported study without modifying its saved observations."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(REPO), str(HERE / 'scripts'), str(HERE / 'inputs')]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    manifest = json.loads((HERE / 'MANIFEST.json').read_text())
    checked = 0
    for base, entries in ((HERE, manifest['artifact_files']),
                          (REPO, manifest['repository_files'])):
        for name, expected in entries.items():
            path = (base / name).resolve()
            if not path.is_relative_to(base) or not path.is_file():
                raise ValueError(f'Missing or invalid manifest member: {name}')
            if sha(path) != expected:
                raise ValueError(f'Content hash mismatch: {name}')
            checked += 1
    data = json.loads((HERE / 'results/workflows.json').read_text())
    counts = {k: len(data[k]) for k in ('grid', 'ccr', 'multidag')}
    if counts != {'grid': 108, 'ccr': 42, 'multidag': 10}:
        raise ValueError(f'Unexpected study counts: {counts}')
    if any(row['status'] != 'completed' for k in counts for row in data[k]):
        raise ValueError('A reported workflow observation is incomplete')
    print(f'Verified {checked} files; workflow observations: {counts}')
    return manifest


def configure_plots(output):
    import plot_study as plots
    plots.INPUT = HERE / 'inputs'
    plots.OUT = HERE / 'results'
    plots.FIG = output / 'figures'
    plots.GEN = output / 'generated'
    plots.FIG.mkdir(parents=True, exist_ok=True)
    plots.GEN.mkdir(parents=True, exist_ok=True)
    return plots


def hidden(output):
    import hidden_check
    report = hidden_check.validate(HERE)
    (output / 'hidden.json').write_text(json.dumps(report, indent=2))
    if not report['acceptance']['passed']:
        raise ValueError('Fixed-capture benchmark acceptance failed')
    print('Fixed-capture benchmark:', report['acceptance'])
    return report


def figures(output):
    from packet_analysis import analyze, dynamic
    import hidden_check
    plots = configure_plots(output)
    for folder in ('figures', 'generated'):
        shutil.copytree(HERE / 'manuscript' / folder, output / folder, dirs_exist_ok=True)
    summary = {'bianchi': plots.bianchi(), 'internal': plots.internal(),
               'evaluation': plots.evaluation()}
    report = hidden(output)
    hidden_check.figure(report, plots)
    summary['packet'] = analyze(HERE, plots.GEN)
    summary['dynamic'] = dynamic(HERE, plots.GEN, plots.FIG)
    (output / 'analysis.json').write_text(json.dumps(summary, indent=2, allow_nan=False))
    # Every included numerical table must reproduce its submitted values.
    for path in (HERE / 'manuscript/generated').glob('*.tex'):
        if (plots.GEN / path.name).read_bytes() != path.read_bytes():
            raise ValueError(f'Regenerated table differs: {path.name}')
    print('Figures and tables generated; submitted numerical tables match.')


def workflows(output, smoke=False):
    import study_workflows
    if importlib.metadata.version('anrg-saga') != '2.0.3':
        raise RuntimeError('Workflow replay requires the recorded anrg-saga==2.0.3 environment')
    data = study_workflows.run(HERE, smoke=smoke)
    reference = json.loads((HERE / 'results/workflows.json').read_text())
    # Timing/provenance records belong to the new replay; compare scientific values.
    compared = 0
    for category in ('grid', 'ccr'):
        key = lambda r: (r['case_id'], r['scheduler'], r['wireless_mode_canonical'])
        expected = {key(r): r for r in reference[category]}
        for row in data[category]:
            old = expected[key(row)]
            for field in ('status', 'makespan_s', 'placement', 'remote_payload_bytes', 'byte_hops'):
                if row[field] != old[field]:
                    raise ValueError(f'Replay differs: {key(row)}, {field}')
            compared += 1
    for row in data['multidag']:
        old = next(r for r in reference['multidag'] if (r['count'], r['mode']) == (row['count'], row['mode']))
        if row != old:
            raise ValueError(f'Concurrent-workflow replay differs: {row["count"]}, {row["mode"]}')
        compared += 1
    (output / 'workflows.json').write_text(json.dumps(data, indent=2, allow_nan=False))
    print(f'{compared} workflow executions match the saved scientific observations.')


def paper(output):
    source = output / 'manuscript'
    shutil.copytree(HERE / 'manuscript', source, dirs_exist_ok=True)
    # Expand row fragments before TeX's alignment scanner, as in the study builder.
    for path in source.rglob('*.tex'):
        text = path.read_text(encoding='utf-8')
        text = re.sub(r'\\input\{(generated/[^}]+_rows\.tex)\}',
                      lambda m: (source / m.group(1)).read_text().rstrip(), text)
        path.write_text(text, encoding='utf-8')
    tex = shutil.which('pdflatex')
    if not tex:
        raise RuntimeError('Install a LaTeX distribution with pdflatex and IEEEtran to compile the paper')
    for _ in range(3):
        result = subprocess.run([tex, '-interaction=nonstopmode', '-halt-on-error',
                                 'ncsim_paper.tex'], cwd=source, capture_output=True, text=True)
        if result.returncode:
            print(result.stdout[-6000:])
            raise RuntimeError('LaTeX compilation failed; inspect ncsim_paper.log')
    log = (source / 'ncsim_paper.log').read_text(errors='replace')
    problems = [line for line in log.splitlines() if 'Overfull' in line or
                'undefined' in line.lower() or 'Label(s) may have changed' in line]
    if problems:
        raise ValueError('Unresolved LaTeX references/layout: ' + '\n'.join(problems))
    final = output / 'ncsim_arxiv.pdf'
    shutil.copy2(source / 'ncsim_paper.pdf', final)
    with zipfile.ZipFile(output / 'ncsim_arxiv_source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((HERE / 'manuscript').rglob('*')):
            if path.is_file():
                relative = path.relative_to(HERE / 'manuscript')
                archive.write(source / relative, relative.as_posix())
    print(f'Built {final}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('verify', 'figures', 'workflows', 'hidden', 'paper'))
    parser.add_argument('--output', type=Path, default=REPO / 'output/arxiv-artifact')
    parser.add_argument('--smoke', action='store_true', help='Run a small subset of the reported workflows')
    args = parser.parse_args()
    if args.smoke and args.command != 'workflows':
        parser.error('--smoke applies only to workflows')
    if args.command == 'workflows' and os.environ.get('PYTHONHASHSEED') != '0':
        return subprocess.call([sys.executable, '-B', str(Path(__file__)), *sys.argv[1:]],
                               env=dict(os.environ, PYTHONHASHSEED='0'))
    verify()
    if args.command == 'verify':
        return 0
    output = args.output.resolve()
    protected = [HERE, REPO / 'ncsim', REPO / 'paper', REPO / 'arxiv-old', REPO / 'experiments', REPO / 'tests', REPO / '.git']
    if output == REPO or any(output.is_relative_to(p) or p.is_relative_to(output) for p in protected):
        parser.error('--output must be separate from source, saved data, and the repository root')
    output.mkdir(parents=True, exist_ok=True)
    logging.disable(logging.WARNING)
    if args.command == 'workflows':
        workflows(output, args.smoke)
    else:
        globals()[args.command](output)
    verify()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
