import math
import csv
from pathlib import Path
def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    point = (len(values)-1)*q
    low, high = math.floor(point), math.ceil(point)
    return values[low] + (point-low)*(values[high]-values[low])
def number(value, digits=1):
    return 'n/a' if value is None else f'{value:.{digits}f}'


def table(path, header, rows, alignment):
    lines = [r'\begin{tabular}{' + alignment + '}', r'\toprule',
             ' & '.join(header) + r' \\', r'\midrule']
    lines.extend(' & '.join(map(str, row)) + r' \\' for row in rows)
    lines.extend([r'\bottomrule', r'\end{tabular}'])
    path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
def read_dynamic(path, separation, seed):
    with path.open(newline='') as f:
        rows=list(csv.DictReader(f))
    keys=[(int(r['link_index']), round(float(r['start_s']),1)) for r in rows]
    expected={(link,round(.5+.1*b,1)) for link in [0,1] for b in range(50)}
    if len(keys)!=len(expected) or set(keys)!=expected:
        raise ValueError(f'Missing or duplicate interval: {path}')
    for r in rows:
        if int(r['seed'])!=seed or float(r['separation'])!=separation:
            raise ValueError(f'Wrong configuration: {path}')
        if not math.isclose(float(r['end_s'])-float(r['start_s']),.1,abs_tol=1e-8):
            raise ValueError(f'Invalid interval duration: {path}')
        if int(r['payload_bytes'])<0 or int(r['payload_bytes'])%1472:
            raise ValueError(f'Invalid application payload accounting: {path}')
        if int(r['link_index'])==1 and float(r['start_s'])>=4.5 and int(r['payload_bytes'])!=0:
            raise ValueError(f'Competitor has not drained before the recovery window: {path}')
    return rows
