import marimo

__generated_with = "0.23.1"
app = marimo.App()


@app.cell
def _():
    import marimo as mo
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
    import src.query_parameters as qp

    return mo, qp


@app.cell
def _(mo):
    mo.md("""
    ## MGKDB Parameter Sparsity Scan
    """)
    return


@app.cell
def _(qp):
    lookup = qp.load_lookup(qp.LOOKUP_FILE)
    print(f"Loaded {len(lookup)} queryable parameters:")
    for e in lookup:
        print(f"  {e['parameter_name']:30s}  {e['db_field']}")
    return (lookup,)


@app.cell
def _():
    from TPED.config.config_helper import Config
    from mgkdb.support.mgk_login import f_login_dbase

    config = Config()
    auth = config.get_path('MGKDB_AUTH_PKL')
    login = f_login_dbase(auth)
    client, database = login.connect()
    print("Connected to DB:", database.name)
    return (database,)


@app.cell
def _(database, lookup, qp):
    import pandas as pd

    projection = {'gyrokineticsIMAS': 1, 'gyrokinetics': 1, 'Metadata.CodeTag': 1}
    rows = []
    for col_name in qp.COLLECTIONS:
        collection = database[col_name]
        print(f"{col_name}: {collection.count_documents({})} records")
        for record in collection.find({}, projection):
            row = qp.extract_params(record, lookup)
            row['collection'] = col_name
            rows.append(row)

    df = pd.DataFrame(rows)
    print(f"\nTotal records: {len(df)}")
    df
    return (df,)


@app.cell
def _(df, mo):
    coverage = df.notna().mean().sort_values() * 100
    mo.md(f"""
    ## Parameter Coverage (% of records with value present)

    {coverage.to_frame('coverage_%').to_markdown()}
    """)
    return


@app.cell
def _(df):
    import matplotlib.pyplot as plt
    import numpy as np

    param_cols = [c for c in df.columns if c not in ('_id', 'collection')]
    present, null, wrong_type = [], [], []
    for col in param_cols:
        s = df[col]
        present.append(s.notna().sum())
        null.append(s.isna().sum())
        wrong_type.append(s.dropna().apply(lambda x: not isinstance(x, (int, float))).sum())

    order = np.argsort(present)
    param_cols = [param_cols[i] for i in order]
    present    = [present[i]    for i in order]
    null       = [null[i]       for i in order]
    wrong_type = [wrong_type[i] for i in order]

    y = np.arange(len(param_cols))
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.barh(y, present,    color='steelblue', label='Present (numeric)')
    ax.barh(y, wrong_type, left=present, color='orange', label='Present (wrong type)')
    ax.barh(y, null, left=[p + w for p, w in zip(present, wrong_type)], color='lightcoral', label='Null / missing')
    ax.set_yticks(y)
    ax.set_yticklabels(param_cols)
    ax.set_xlabel('Number of records')
    ax.set_title('Parameter Coverage')
    ax.legend(loc='lower right')
    plt.tight_layout()
    fig
    return


if __name__ == "__main__":
    app.run()
