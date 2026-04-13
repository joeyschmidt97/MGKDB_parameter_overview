"""
Query MGKDB for physical parameters defined in MGKDB_parameter_lookup.yaml.
Extracts only the gyrokineticsIMAS fields (no file downloads).
Outputs a CSV where each row is one simulation and each column is a parameter.
"""

import os
import sys
import yaml
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config.config_helper import Config

from mgkdb.support.mgk_login import f_login_dbase


LOOKUP_FILE = os.path.join(os.path.dirname(__file__), 'MGKDB_parameter_lookup.yaml')
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), '..', 'analysis', 'parameter_scan.csv')
COLLECTIONS  = ['LinearRuns', 'NonlinRuns']


def load_lookup(path):
    with open(path) as f:
        entries = yaml.safe_load(f)
    # Keep only entries that have a real db_field
    return [e for e in entries if e.get('db_field') and '/' not in str(e['db_field'])]


def resolve_field(doc, dotpath):
    """Walk a dot-separated path into a nested dict, handling array indices like species[0]."""
    import re
    parts = re.split(r'\.', dotpath)
    node = doc
    for part in parts:
        if node is None:
            return None
        # handle array notation e.g. species[0] or wavevector[0]
        m = re.match(r'^(\w+)\[(\d+)\]$', part)
        if m:
            key, idx = m.group(1), int(m.group(2))
            node = node.get(key) if isinstance(node, dict) else None
            node = node[idx] if isinstance(node, list) and len(node) > idx else None
        else:
            node = node.get(part) if isinstance(node, dict) else None
    return node


def resolve_species_field(doc, dotpath):
    """
    Resolve fields like gyrokinetics.species[e].temperature_log_gradient_norm
    by finding the species with the matching role (e=electron charge=-1, i=main ion, z=impurity).
    """
    import re
    m = re.match(r'^(gyrokinetics(?:IMAS)?\.species)\[([eiz])\]\.(.+)$', dotpath)
    if not m:
        return resolve_field(doc, dotpath)

    base, role, subfield = m.group(1), m.group(2), m.group(3)
    species_list = resolve_field(doc, base.replace('gyrokineticsIMAS.', '').replace('gyrokinetics.', ''))
    if not isinstance(species_list, list):
        return None

    for sp in species_list:
        charge = sp.get('charge_norm', sp.get('charge', None))
        if role == 'e' and charge == -1:
            return sp.get(subfield)
        elif role == 'i' and charge is not None and charge > 0 and sp.get('mass_norm', 999) < 5:
            return sp.get(subfield)
        elif role == 'z' and charge is not None and charge > 1:
            return sp.get(subfield)
    return None


def resolve_collisionality(doc, dotpath):
    """
    Resolve gyrokinetics.collisions.collisionality_norm[e][e] or [i][i].
    Finds the diagonal element for the matching species.
    """
    import re
    m = re.match(r'^gyrokinetics(?:IMAS)?\.collisions\.collisionality_norm\[([ei])\]\[([ei])\]$', dotpath)
    if not m:
        return None

    role = m.group(1)
    gk = doc.get('gyrokineticsIMAS', doc.get('gyrokinetics', {}))
    species_list = gk.get('species', [])
    coll_matrix = gk.get('collisions', {}).get('collisionality_norm', [])

    idx = None
    for i, sp in enumerate(species_list):
        charge = sp.get('charge_norm', sp.get('charge', None))
        if role == 'e' and charge == -1:
            idx = i
            break
        elif role == 'i' and charge is not None and charge > 0 and sp.get('mass_norm', 999) < 5:
            idx = i
            break

    if idx is None or not coll_matrix:
        return None
    try:
        return coll_matrix[idx][idx]
    except (IndexError, TypeError):
        return None


def extract_params(record, lookup):
    row = {'_id': str(record['_id'])}
    gk = record.get('gyrokineticsIMAS', record.get('gyrokinetics', {}))

    for entry in lookup:
        name = entry['parameter_name']
        field = entry['db_field']

        if 'collisionality_norm' in field:
            row[name] = resolve_collisionality(record, field)
        elif 'species[' in field:
            # remap to gyrokineticsIMAS sub-doc
            inner_field = field.replace('gyrokinetics.', '').replace('gyrokineticsIMAS.', '')
            row[name] = resolve_species_field(gk, 'gyrokinetics.' + inner_field)
        else:
            inner_field = field.replace('gyrokineticsIMAS.', '').replace('gyrokinetics.', '')
            row[name] = resolve_field(gk, inner_field)

    return row


def main():
    config = Config()
    auth = config.get_path('MGKBD_AUTH')
    lookup = load_lookup(LOOKUP_FILE)

    login = f_login_dbase(auth)
    database = login.connect()

    # Only pull the gyrokineticsIMAS field — no files
    projection = {'gyrokineticsIMAS': 1, 'gyrokinetics': 1, 'Metadata.CodeTag': 1}

    rows = []
    for col_name in COLLECTIONS:
        collection = getattr(database, col_name)
        total = collection.count_documents({})
        print(f'{col_name}: {total} records')
        for record in collection.find({}, projection):
            row = extract_params(record, lookup)
            row['collection'] = col_name
            rows.append(row)

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)
    print(f'Saved {len(df)} rows to {OUTPUT_FILE}')
    print(f'Coverage:\n{df.notna().mean().sort_values().to_string()}')


if __name__ == '__main__':
    main()
