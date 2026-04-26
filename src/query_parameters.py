"""
Query MGKDB for physical parameters defined in MGKDB_parameter_lookup.yaml.
Extracts only the gyrokineticsIMAS fields (no file downloads).
Outputs a CSV where each row is one simulation and each column is a parameter.
"""

import os
import yaml
import pandas as pd
import re


from MGKDB_parameter_overview.config.config_helper import Config
from mgkdb.support.mgk_login import f_login_dbase


LOOKUP_FILE = os.path.join(os.path.dirname(__file__), 'MGKDB_parameter_lookup.yaml')
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), '..', 'analysis', 'parameter_scan.csv')
COLLECTIONS = ['LinearRuns']


def load_lookup(path):
    with open(path) as f:
        entries = yaml.safe_load(f)
    return [e for e in entries if e.get('db_field')]




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

def resolve_field(obj, path):
    """Resolve a dot-notation path, supporting [0], [e], [i] indexing."""
    parts = re.split(r'\.(?![^\[]*\])', path)  # split on dots outside brackets
    
    for part in parts:
        if obj is None:
            return None
        
        match = re.match(r'^(\w+)\[(\w+)\]$', part)
        if match:
            key, idx = match.group(1), match.group(2)
            obj = obj.get(key) if isinstance(obj, dict) else None
            if obj is None:
                return None
            
            if isinstance(obj, list):
                if idx.lstrip('-').isdigit():
                    # Numeric index
                    try:
                        obj = obj[int(idx)]
                    except IndexError:
                        return None
                elif idx == 'e':
                    # Find electron species by name
                    obj = next((s for s in obj if 'electron' in str(s.get('name', '')).lower()), None)
                elif idx == 'i':
                    # Find ion species by name (exclude electrons)
                    obj = next((s for s in obj if 'ion' in str(s.get('name', '')).lower() and 'electron' not in str(s.get('name', '')).lower()), None)
                else:
                    return None
            else:
                return None
        else:
            obj = obj.get(part) if isinstance(obj, dict) else None
    
    return obj


def extract_params(record, lookup, nan_debug=None):
    row = {'_id': str(record['_id'])}
    gk = record.get('gyrokineticsIMAS', record.get('gyrokinetics', {}))

    for entry in lookup:
        name = entry['parameter_name']
        field = entry['db_field']
        derived = entry.get('derived')

        if derived and isinstance(field, list):
            fields = []
            for f in field:
                inner = f.replace('gyrokineticsIMAS.', '').replace('gyrokinetics.', '')
                val = resolve_species_field(gk, 'gyrokinetics.' + inner)
                fields.append(val)
            if all(v is not None for v in fields):
                try:
                    row[name] = eval(derived, {"fields": fields})
                except Exception:
                    row[name] = None
            else:
                # Track which sub-fields were None
                if nan_debug is not None:
                    for f, v in zip(field, fields):
                        if v is None:
                            key = (name, f)
                            nan_debug[key] = nan_debug.get(key, 0) + 1
                row[name] = None
            continue

        fields = field if isinstance(field, list) else [field]

        value = None
        for f in fields:
            if 'collisionality_norm' in f:
                value = resolve_collisionality(record, f)
            elif 'species[' in f:
                inner = f.replace('gyrokinetics.', '').replace('gyrokineticsIMAS.', '')
                value = resolve_species_field(gk, 'gyrokinetics.' + inner)
            else:
                inner = f.replace('gyrokineticsIMAS.', '').replace('gyrokinetics.', '')
                value = resolve_field(gk, inner)

            if value is None and nan_debug is not None:
                key = (name, f)
                nan_debug[key] = nan_debug.get(key, 0) + 1

            if value is not None:
                break

        row[name] = value
    return row


def main():
    config = Config()
    auth = config.get_path('MGKDB_AUTH_PKL')
    lookup = load_lookup(LOOKUP_FILE)

    login = f_login_dbase(auth)
    client, database = login.connect()

    projection = {'gyrokineticsIMAS': 1, 'gyrokinetics': 1, 'Metadata.CodeTag': 1}

    rows = []
    ky_debug = {}  # path → count of NaN hits
    for col_name in COLLECTIONS:
        collection = database[col_name]
        total = collection.count_documents({})
        print(f'{col_name}: {total} records')
        for record in collection.find({}, projection):
            row = extract_params(record, lookup, ky_debug=ky_debug)
            row['collection'] = col_name
            rows.append(row)

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)
    print(f'Saved {len(df)} rows to {OUTPUT_FILE}')
    print(f'Coverage:\n{df.notna().mean().sort_values().to_string()}')

    # ky NaN summary
    if ky_debug:
        total_nan = sum(ky_debug.values())
        print(f'\n[ky NaN summary] {total_nan} records returned NaN after trying all paths:')
        for path, count in sorted(ky_debug.items(), key=lambda x: -x[1]):
            print(f'  {count:>5} NaNs tried path: {path}')
    else:
        print('\n[ky] No NaNs — all records resolved successfully.')

if __name__ == '__main__':
    main()